# .roo/cognee/src/parser/orchestrator.py
import asyncio
import inspect
import importlib
import pkgutil
from pathlib import Path
from typing import Dict, Type, List, Optional, Tuple, Union
import uuid
import hashlib
import os
import time
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception, before_sleep_log

from .entities import (
    FileProcessingRequest, Repository, SourceFile, TextChunk, CodeEntity,
    RawSymbolReference, ParserOutput, Relationship, PendingLink, LinkStatus,
    ImportType, ReferenceContext, AdaptableNode
)
from .parsers.base_parser import BaseParser
from .parsers.generic_parser import GenericParser
from .chunking import generate_intelligent_chunks
from .utils import logger, read_file_content, parse_temp_code_entity_id, resolve_import_path
from .graph_utils import (
    delete_nodes_with_filter, atomic_get_and_increment_local_save,
    save_graph_data, check_content_exists, find_code_entity_by_path,
    is_transient_error # <-- IMPORT THE ROBUST ERROR CHECKER
)
from .cognee_adapter import adapt_parser_entities_to_graph_elements
from .dispatcher import get_dispatcher
from cognee.infrastructure.databases.graph import get_graph_db

# --- Dynamic Loader with Robust Error Handling ---
def _load_parsers_and_build_map() -> Tuple[Dict[str, Type[BaseParser]], Optional[Type[BaseParser]]]:
    extension_map: Dict[str, Type[BaseParser]] = {}
    fallback_parser: Optional[Type[BaseParser]] = None
    critical_parsers = {'CppParser', 'GenericParser'}
    loaded_parsers = set()

    import src.parser.parsers as p
    for _, name, _ in pkgutil.walk_packages(p.__path__, p.__name__ + '.'):
        try:
            m = importlib.import_module(name)
            for _, attr_value in m.__dict__.items():
                if inspect.isclass(attr_value) and issubclass(attr_value, BaseParser) and attr_value is not BaseParser:
                    loaded_parsers.add(attr_value.__name__)
                    if "generic_fallback" in attr_value.SUPPORTED_EXTENSIONS:
                        fallback_parser = attr_value
                    for ext in attr_value.SUPPORTED_EXTENSIONS:
                        if ext != "generic_fallback":
                            extension_map[ext] = attr_value
        except Exception as e:
            logger.error(f"ORCHESTRATOR(LOADER): Failed to load parser module '{name}': {e}", exc_info=True)

    missing_critical = critical_parsers - loaded_parsers
    if missing_critical:
        error_message = f"Critical parsers failed to load: {missing_critical}"
        logger.critical(f"ORCHESTRATOR(LOADER): {error_message}")
        raise RuntimeError(error_message)

    if not fallback_parser:
        logger.warning("ORCHESTRATOR(LOADER): No fallback parser loaded; unsupported file types will be skipped.")

    return extension_map, fallback_parser

EXTENSION_PARSER_MAP, FALLBACK_PARSER = _load_parsers_and_build_map()

def _get_parser_for_file(file_path: Path) -> Optional[BaseParser]:
    """Finds and instantiates a suitable parser, handling case-insensitivity and alternate extensions."""
    ext = file_path.suffix.lower()
    ext_alternates = {'.cxx': '.cpp', '.c++': '.cpp', '.hh': '.hpp'}
    normalized_ext = ext_alternates.get(ext, ext)

    ParserClass = EXTENSION_PARSER_MAP.get(normalized_ext) or FALLBACK_PARSER
    return ParserClass() if ParserClass else None

# --- Main Processing Function with Retry Logic ---

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception(is_transient_error), # <-- USE THE IMPORTED, ROBUST CHECKER
    before_sleep=before_sleep_log(logger, "WARNING")
)
async def _execute_transaction_with_retry(request: FileProcessingRequest, log_prefix: str) -> Tuple[bool, str, List[CodeEntity]]:
    """Wraps the entire database transaction in a retry block for transient errors."""
    db = get_graph_db()
    session = None
    repo_id_with_branch = f"{request.repo_id}@{request.branch}"
    final_code_entities: List[CodeEntity] = []
    has_activity = False

    try:
        session = await db.get_session()
        async with session.begin() as tx:
            relative_path = str(Path(request.absolute_path).relative_to(request.repo_path))

            # Step 1: Handle DELETE request
            if request.is_delete:
                logger.info(f"{log_prefix}: Request is DELETE. Clearing data for this path.")
                delete_filter = {"repo_id_str": repo_id_with_branch, "relative_path_str": relative_path}
                await delete_nodes_with_filter(tx, delete_filter)
                return False, repo_id_with_branch, []

            # Step 2: Handle empty content
            content = await read_file_content(str(request.absolute_path))
            if not content or not content.strip():
                logger.info(f"{log_prefix}: File is empty. Ensuring SourceFile node exists and stopping.")
                await delete_nodes_with_filter(tx, {"repo_id_str": repo_id_with_branch, "relative_path_str": relative_path})
                version_id = f"{request.commit_index}-1"
                source_file_id = f"{repo_id_with_branch}|{relative_path}@{version_id}"
                empty_file_node = SourceFile(id=source_file_id, relative_path=relative_path, commit_index=request.commit_index, local_save=1, content_hash=hashlib.sha256(b'').hexdigest())
                nodes, _ = adapt_parser_entities_to_graph_elements([empty_file_node])
                await save_graph_data(tx, nodes, [])
                return False, repo_id_with_branch, []

            # Step 3: IDEMPOTENCY & VERSIONING
            content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
            if await check_content_exists(tx, content_hash):
                return False, repo_id_with_branch, []

            await delete_nodes_with_filter(tx, {"repo_id_str": repo_id_with_branch, "relative_path_str": relative_path})

            local_save_count = await atomic_get_and_increment_local_save(tx, repo_id_with_branch, relative_path, request.commit_index)
            version_id = f"{request.commit_index}-{local_save_count}"
            source_file_id = f"{repo_id_with_branch}|{relative_path}@{version_id}"

            # Step 4: PARSE & COLLECT
            parser = _get_parser_for_file(Path(request.absolute_path))
            if not parser:
                logger.error(f"{log_prefix}: No suitable parser found. Aborting transaction.")
                return False, repo_id_with_branch, []

            slice_lines, code_entities, raw_references = [], [], []
            async for item in parser.parse(source_file_id, content):
                if isinstance(item, list): slice_lines = item
                elif isinstance(item, CodeEntity): code_entities.append(item)
                elif isinstance(item, RawSymbolReference): raw_references.append(item)

            if not slice_lines and content.strip():
                logger.info(f"{log_prefix}: Parser {parser.__class__.__name__} found no slicing points. Falling back to generic chunking.")
                generic_parser = GenericParser()
                slice_lines = await anext(generic_parser.parse(source_file_id, content), [])

            # Step 5: ASSEMBLE FILE'S "ISLAND"
            final_text_chunks = generate_intelligent_chunks(source_file_id, content, slice_lines)

            if not final_text_chunks and (code_entities or raw_references):
                logger.warning(f"{log_prefix}: Parser yielded entities/references but no chunks were generated. This is inconsistent.")
                # Decide if this should be a hard failure or just a warning. For now, we stop.
                return False, repo_id_with_branch, []

            if not final_text_chunks:
                # This path is now only for files that are parsed but result in no chunks (e.g. only preprocessor directives)
                logger.info(f"{log_prefix}: No chunks were generated. Ending processing for this file.")
                has_activity = True # Still counts as activity to create the SourceFile node
            else:
                has_activity = True

            entities_to_save: List[Union[AdaptableNode, Relationship]] = []
            temp_id_to_final_id_map: Dict[str, str] = {}

            entities_to_save.append(Repository(id=repo_id_with_branch, path=request.repo_path, repo_id=request.repo_id, branch=request.branch, import_id=request.import_id))
            entities_to_save.append(SourceFile(id=source_file_id, relative_path=relative_path, commit_index=request.commit_index, local_save=local_save_count, content_hash=content_hash))
            entities_to_save.extend(final_text_chunks)

            for chunk in final_text_chunks:
                entities_to_save.append(Relationship(source_id=source_file_id, target_id=chunk.id, type="CONTAINS_CHUNK"))

            for temp_ce in code_entities:
                parsed_id = parse_temp_code_entity_id(temp_ce.id)
                if not parsed_id: continue
                fqn_part, start_line_1 = parsed_id
                parent_chunk = next((c for c in final_text_chunks if c.start_line <= start_line_1 <= c.end_line), None)
                if not parent_chunk: continue
                final_ce_id = f"{parent_chunk.id}|{fqn_part}@{start_line_1}-{temp_ce.end_line}"
                temp_id_to_final_id_map[temp_ce.id] = final_ce_id
                final_entity = CodeEntity(id=final_ce_id, type=temp_ce.type, snippet_content=temp_ce.snippet_content, start_line=start_line_1, end_line=temp_ce.end_line, canonical_fqn=temp_ce.canonical_fqn, metadata=temp_ce.metadata)
                entities_to_save.append(final_entity)
                entities_to_save.append(Relationship(source_id=parent_chunk.id, target_id=final_ce_id, type="DEFINES_CODE_ENTITY"))
                final_code_entities.append(final_entity)

            # Step 6: TIER 1 RESOLUTION & PENDING LINK CREATION
            for ref in raw_references:
                final_source_id = temp_id_to_final_id_map.get(ref.source_entity_id, ref.source_entity_id)
                resolved_target_id = None
                if ref.context.import_type == ImportType.RELATIVE:
                    target_rel_path = resolve_import_path(relative_path, "/".join(ref.context.path_parts))
                    if target_rel_path: resolved_target_id = await find_code_entity_by_path(tx, repo_id_with_branch, target_rel_path, ref.target_expression)
                elif ref.context.import_type == ImportType.ABSOLUTE:
                    target_fqn = "::".join(ref.context.path_parts) if ref.context.path_parts else ref.target_expression
                    resolved_target_id = await find_code_entity_by_path(tx, repo_id_with_branch, None, target_fqn)
                if resolved_target_id:
                    entities_to_save.append(Relationship(source_id=final_source_id, target_id=resolved_target_id, type=ref.reference_type, properties=ref.metadata))
                else:
                    question_str = f"{final_source_id}|{ref.target_expression}|{ref.reference_type}"
                    pending_link_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, question_str))
                    ref.source_entity_id = final_source_id
                    entities_to_save.append(PendingLink(id=pending_link_id, reference_data=ref))

            # Step 7: ADAPT & SAVE
            nodes_to_add, edges_to_add = adapt_parser_entities_to_graph_elements(entities_to_save)
            await save_graph_data(tx, nodes_to_add, edges_to_add)

    finally:
        if session:
            await session.close()

    return has_activity, repo_id_with_branch, final_code_entities

async def process_single_file(request: FileProcessingRequest):
    start_time = time.time()
    log_prefix = f"ORCHESTRATOR ({Path(request.absolute_path).name})"
    logger.info(f"{log_prefix}: Starting processing for {request.repo_id}@{request.branch}|{request.absolute_path}")

    if not all([request.repo_id, request.branch]):
        logger.error(f"{log_prefix}: Invalid request: repo_id or branch missing. Aborting."); return
    if not os.path.isfile(request.absolute_path):
        logger.error(f"{log_prefix}: File does not exist: {request.absolute_path}. Aborting."); return

    has_meaningful_activity = False
    repo_id_with_branch = ""
    final_code_entities_for_dispatcher = []

    try:
        has_meaningful_activity, repo_id_with_branch, final_code_entities_for_dispatcher = await _execute_transaction_with_retry(request, log_prefix)
    except Exception as e:
        logger.critical(f"{log_prefix}: Transaction failed after all retries. Error: {e}", exc_info=True)

    total_time = time.time() - start_time
    logger.info(f"{log_prefix}: Finished processing in {total_time:.2f} seconds.")

    if has_meaningful_activity:
        dispatcher = get_dispatcher()
        await dispatcher.notify_ingestion_activity(repo_id_with_branch, final_code_entities_for_dispatcher)
        logger.info(f"{log_prefix}: Notified dispatcher of activity for repo '{repo_id_with_branch}'.")
