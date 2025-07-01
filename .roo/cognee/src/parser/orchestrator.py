import asyncio
import inspect
import importlib
import pkgutil
from pathlib import Path
from typing import AsyncGenerator, Dict, Type, List, Optional, Tuple

from .entities import (
    FileProcessingRequest, FileProcessingAction,
    Repository, SourceFile, TextChunk, CodeEntity, Relationship,
    CallSiteReference, ParserOutput, OrchestratorOutput
)
from .parsers.base_parser import BaseParser
from .chunking import generate_text_chunks_from_slice_lines
from .utils import logger, read_file_content, parse_temp_code_entity_id
from .graph_utils import delete_all_versions_of_file, get_latest_local_save_count, save_graph_data

from cognee.infrastructure.databases.graph import get_graph_engine

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
        except Exception as e: logger.error(f"Failed to load parser module '{name}': {e}", exc_info=True)
    return extension_map, fallback_parser

EXTENSION_PARSER_MAP, FALLBACK_PARSER = _load_parsers_and_build_map()

def _get_parser_for_file(file_path: Path) -> Optional[BaseParser]:
    parser = EXTENSION_PARSER_MAP.get(file_path.name) or EXTENSION_PARSER_MAP.get(file_path.suffix)
    return parser or FALLBACK_PARSER

async def _orchestrate_single_file_upsert(request: FileProcessingRequest, version_id: str) -> List[OrchestratorOutput]:
    """Handles the parsing and graph element creation for a single file upsert."""
    repo_id_with_branch = f"{request.repo_id}@{request.branch}"
    relative_path = str(Path(request.absolute_path).relative_to(request.repo_path))
    source_file_id = f"{repo_id_with_branch}|{relative_path}|{version_id}"

    output_entities: List[OrchestratorOutput] = [
        Repository(id=repo_id_with_branch, path=request.repo_path),
        SourceFile(id=source_file_id)
    ]

    content = await read_file_content(request.absolute_path)
    if not content: return []

    parser = _get_parser_for_file(Path(request.absolute_path))
    if not parser: return []

    parser_yields = [item async for item in parser.parse(source_file_id, content)]

    slice_lines = next((item for item in parser_yields if isinstance(item, list)), [0])
    temp_code_entities = {item.id: item for item in parser_yields if isinstance(item, CodeEntity)}

    final_text_chunks = generate_text_chunks_from_slice_lines(source_file_id, content, slice_lines)
    for chunk in final_text_chunks:
        output_entities.append(chunk)
        output_entities.append(Relationship(source_id=source_file_id, target_id=chunk.id, type="CONTAINS_CHUNK"))

    for temp_ce in temp_code_entities.values():
        parsed_id = parse_temp_code_entity_id(temp_ce.id)
        if not parsed_id: continue
        fqn_part, start_line_0 = parsed_id
        parent_chunk = next((c for c in final_text_chunks if c.start_line <= (start_line_0 + 1) <= c.end_line), None)

        if not parent_chunk:
            logger.critical(f"ORCHESTRATOR: Could not find parent chunk for entity '{temp_ce.id}'. Halting.")
            continue

        final_ce_id = f"{parent_chunk.id}|{fqn_part}"
        output_entities.append(CodeEntity(id=final_ce_id, type=temp_ce.type, snippet_content=temp_ce.snippet_content))
        output_entities.append(Relationship(source_id=parent_chunk.id, target_id=final_ce_id, type="DEFINES_CODE_ENTITY"))

    return output_entities


async def process_single_file(request: FileProcessingRequest):
    """Main library entry point. Manages the atomic transaction for a single file request."""
    graph_engine = await get_graph_engine()
    session = graph_engine.session

    try:
        with session.begin_transaction() as tx:
            repo_id_with_branch = f"{request.repo_id}@{request.branch}"
            relative_path = str(Path(request.absolute_path).relative_to(request.repo_path))

            await delete_all_versions_of_file(tx, repo_id_with_branch, relative_path)

            if request.is_delete:
                logger.info(f"ORCHESTRATOR: Completed DELETE action for '{relative_path}'.")
            else:
                if not request.commit_index:
                    raise ValueError("'commit_index' is required for UPSERT action.")

                content = await read_file_content(request.absolute_path)
                if not content or not content.strip():
                    logger.info(f"ORCHESTRATOR: File '{relative_path}' is empty. Deletion complete, no data to add.")
                else:
                    latest_save_count = await get_latest_local_save_count(tx, repo_id_with_branch, relative_path, request.commit_index)
                    version_id = f"{request.commit_index}-{str(latest_save_count + 1).zfill(3)}"

                    parser_entities = await _orchestrate_single_file_upsert(request, version_id)

                    nodes_to_add, edges_to_add = adapt_parser_entities_to_graph_elements(parser_entities)

                    await save_graph_data(tx, nodes_to_add, edges_to_add)

            tx.commit()
            logger.info(f"ORCHESTRATOR: Successfully committed transaction for file '{relative_path}'.")

    except Exception as e:
        logger.error(f"ORCHESTRATOR: Transaction failed for file '{request.absolute_path}'. Rolling back. Error: {e}", exc_info=True)
