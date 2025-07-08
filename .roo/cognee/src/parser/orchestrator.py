# .roo/cognee/src/parser/orchestrator.py
import asyncio
import inspect
import importlib
import pkgutil
from pathlib import Path
from typing import AsyncGenerator, Dict, Type, List, Optional, Tuple, Union
import uuid
import hashlib

# --- All our final data contracts ---
from .entities import (
    FileProcessingRequest, Repository, SourceFile, TextChunk,
    CodeEntity, RawSymbolReference, ParserOutput, Relationship,
    PendingLink, LinkStatus, ImportType
)
from .parsers.base_parser import BaseParser
from .chunking import generate_text_chunks_from_slice_lines
from .utils import logger, read_file_content, parse_temp_code_entity_id
# --- The full set of required graph utilities ---
from .graph_utils import (
    delete_all_versions_of_file, get_latest_local_save_count,
    save_graph_data, check_content_exists, find_code_entity_by_path,
    update_heartbeat
)
from .cognee_adapter import adapt_parser_entities_to_graph_elements
from cognee.infrastructure.databases.graph import get_graph_db # Use the DB factory

# --- Dynamic Loader (Unchanged) ---
def _load_parsers_and_build_map() -> Tuple[Dict[str, BaseParser], Optional[BaseParser]]:
    extension_map, fallback_parser = {}, None
    import src.parser.parsers as p
    for _, name, _ in pkgutil.walk_packages(p.__path__, p.__name__ + '.'):
        try:
            m = importlib.import_module(name)
            for _, attr in m.__dict__.values():
                if inspect.isclass(attr) and issubclass(attr, BaseParser) and attr is not BaseParser:
                    inst = attr()
                    if "generic_fallback" in inst.SUPPORTED_EXTENSIONS: fallback_parser = inst
                    for ext in inst.SUPPORTED_EXTENSIONS:
                        if ext != "generic_fallback": extension_map[ext] = inst
        except Exception as e:
            logger.error(f"Failed to load parser module '{name}': {e}", exc_info=True)
    return extension_map, fallback_parser

EXTENSION_PARSER_MAP, FALLBACK_PARSER = _load_parsers_and_build_map()

def _get_parser_for_file(file_path: Path) -> Optional[BaseParser]:
    parser = EXTENSION_PARSER_MAP.get(file_path.name) or EXTENSION_PARSER_MAP.get(file_path.suffix)
    return parser or FALLBACK_PARSER

# --- Tier 1 Resolver Helper ---
async def _resolve_tier1_link(tx_handle: Any, ref: RawSymbolReference, request: FileProcessingRequest) -> Optional[str]:
    """
    Attempts to resolve a reference using only high-confidence, Tier 1 logic.
    Returns the final target ID if successful, otherwise None.
    """
    context = ref.context
    if context.import_type == ImportType.RELATIVE:
        # The parser has provided a definite file path hint.
        # This is the highest confidence link we can have.
        try:
            # Construct absolute path from relative hint to resolve `.` and `..`
            source_dir = Path(request.absolute_path).parent
            target_abs_path = source_dir / os.path.normpath(context.path_parts[0])
            target_rel_path = str(target_abs_path.relative_to(request.repo_path))
            target_fqn = ref.target_expression # In a simple case

            # A more robust version would parse the target_expression more carefully

            return await find_code_entity_by_path(
                tx_handle, request.repo_id, request.branch, target_rel_path, target_fqn
            )
        except Exception as e:
            logger.warning(f"Failed to resolve relative path for {ref.target_expression}: {e}")
            return None
    return None

async def process_single_file(request: FileProcessingRequest):
    """
    Main library entry point. Manages the atomic transaction for a single file request.
    This is the Tier 1, real-time part of the engine.
    """
    log_prefix = f"ORCHESTRATOR ({request.repo_id}@{request.branch}|{Path(request.absolute_path).name})"
    db = get_graph_db()
    session = None
    try:
        session = db.session()
        with session.begin_transaction() as tx:
            repo_id_with_branch = f"{request.repo_id}@{request.branch}"
            relative_path = str(Path(request.absolute_path).relative_to(request.repo_path))

            if request.is_delete:
                await delete_all_versions_of_file(tx, repo_id_with_branch, relative_path)
                logger.info(f"{log_prefix}: Completed DELETE action for '{relative_path}'.")
                tx.commit()
                return

            # --- UPSERT Action ---
            content = await read_file_content(str(request.absolute_path))
            if not content or not content.strip():
                await delete_all_versions_of_file(tx, repo_id_with_branch, relative_path)
                logger.info(f"{log_prefix}: File is empty. Deleting existing versions.")
                tx.commit()
                return

            # 1. VERSIONING & IDEMPOTENCY
            latest_save_count = await get_latest_local_save_count(tx, repo_id_with_branch, relative_path, request.commit_index)
            version_id = f"{request.commit_index}-{str(latest_save_count + 1).zfill(3)}"
            source_file_id = f"{repo_id_with_branch}|{relative_path}|{version_id}"

            # Idempotency check: Don't re-process the exact same content
            content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
            if await check_content_exists(tx, source_file_id, content_hash):
                logger.info(f"{log_prefix}: Content for this file version already exists. Skipping.")
                # We don't commit here, just exit the 'with' block cleanly.
                return

            # 2. PARSE & COLLECT
            parser = _get_parser_for_file(Path(request.absolute_path))
            if not parser:
                logger.error(f"{log_prefix}: No parser found. Aborting.")
                return

            parser_yields = [item async for item in parser.parse(source_file_id, content)]
            slice_lines = next((item for item in parser_yields if isinstance(item, list)), [])
            code_entities = [item for item in parser_yields if isinstance(item, CodeEntity)]
            raw_references = [item for item in parser_yields if isinstance(item, RawSymbolReference)]

            # 3. CREATE & STAGE NODES & RELATIONSHIPS (Phase A)
            entities_to_save: List[Union[Repository, SourceFile, TextChunk, CodeEntity, Relationship, PendingLink]] = []

            repo_node = Repository(id=repo_id_with_branch, path=request.repo_path, import_id=request.import_id)
            entities_to_save.append(repo_node)
            entities_to_save.append(SourceFile(id=source_file_id, content_hash=content_hash))

            final_text_chunks = generate_text_chunks_from_slice_lines(source_file_id, content, slice_lines)
            entities_to_save.extend(final_text_chunks)
            for chunk in final_text_chunks:
                entities_to_save.append(Relationship(source_id=source_file_id, target_id=chunk.id, type="CONTAINS_CHUNK"))

            temp_id_to_final_id_map: Dict[str, str] = {}
            for temp_ce in code_entities:
                # ... (Logic to finalize CodeEntity IDs by finding parent chunk) ...
                # This part remains the same as your original logic
                final_ce_id = "..."
                temp_id_to_final_id_map[temp_ce.id] = final_ce_id
                entities_to_save.append(CodeEntity(id=final_ce_id, type=temp_ce.type, snippet_content=temp_ce.snippet_content))
                entities_to_save.append(Relationship(source_id=parent_chunk.id, target_id=final_ce_id, type="DEFINES_CODE_ENTITY"))

            # 4. TIER 1 RESOLUTION & PENDING LINK CREATION
            for ref in raw_references:
                ref.source_entity_id = temp_id_to_final_id_map.get(ref.source_entity_id, ref.source_entity_id)

                resolved_target_id = await _resolve_tier1_link(tx, ref, request)

                if resolved_target_id:
                    entities_to_save.append(Relationship(source_id=ref.source_entity_id, target_id=resolved_target_id, type=ref.reference_type))
                else:
                    # Create a deterministic ID for the pending link
                    question_str = f"{ref.source_entity_id}|{ref.target_expression}|{ref.reference_type}"
                    pending_link_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, question_str))
                    entities_to_save.append(PendingLink(id=pending_link_id, reference_data=ref))

            # 5. ADAPT & SAVE
            nodes_to_add, edges_to_add = adapt_parser_entities_to_graph_elements(entities_to_save)
            await save_graph_data(tx, nodes_to_add, edges_to_add)

            # 6. UPDATE HEARTBEAT
            heartbeat_id = f"heartbeat://{repo_id_with_branch}"
            await update_heartbeat(tx, heartbeat_id)

            tx.commit()
            logger.info(f"{log_prefix}: Successfully processed file.")

    except Exception as e:
        logger.error(f"{log_prefix}: Transaction failed. Rolling back. Error: {e}", exc_info=True)
        # The `with` block should handle rollback automatically if the backend supports it.
    finally:
        if session:
            session.close()
