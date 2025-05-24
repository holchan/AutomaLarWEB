from typing import List, Dict, Any, AsyncGenerator, Optional, Type
from pydantic import BaseModel as ParserBaseModel
import uuid

from .utils import logger
from .utils import parse_text_chunk_id, parse_code_entity_id

from .entities import (
    Repository as ParserRepository,
    SourceFile as ParserSourceFile,
    TextChunk as ParserTextChunk,
    CodeEntity as ParserCodeEntity,
    Relationship as ParserRelationship,
)

from ..custom_cognee_datapoints import (
    DataPoint,
    AdaptedRepositoryDP,
    AdaptedSourceFileDP,
    AdaptedTextChunkDP,
    AdaptedCodeEntityDP,
    AdaptedFunctionEntityDP,
    AdaptedClassEntityDP,
)

PARSER_ENTITY_TYPE_TO_ADAPTED_DP_CLASS: Dict[str, Type[AdaptedCodeEntityDP]] = {
    "FunctionDefinition": AdaptedFunctionEntityDP,
    "ClassDefinition": AdaptedClassEntityDP,
    "CFunction": AdaptedFunctionEntityDP,
    "CStruct": AdaptedCodeEntityDP,
    "JsFunction": AdaptedFunctionEntityDP,
}


async def adapt_parser_to_datapoints(
    parser_entity_stream: AsyncGenerator[ParserBaseModel, None]
) -> List[DataPoint]:
    """
    Consumes the stream of custom Pydantic entities from the parser/orchestrator
    and converts them into a list of interlinked Cognee DataPoint instances
    ready for ingestion by cognee.add_data_points().
    """
    logger.info("Starting adaptation of parser output to Cognee DataPoints...")

    p_repositories: Dict[str, ParserRepository] = {}
    p_source_files: Dict[str, ParserSourceFile] = {}
    p_text_chunks: Dict[str, ParserTextChunk] = {}
    p_code_entities: Dict[str, ParserCodeEntity] = {}
    p_relationships: List[ParserRelationship] = []

    async for p_entity in parser_entity_stream:
        if isinstance(p_entity, ParserRepository):
            p_repositories[p_entity.id] = p_entity
        elif isinstance(p_entity, ParserSourceFile):
            p_source_files[p_entity.id] = p_entity
        elif isinstance(p_entity, ParserTextChunk):
            p_text_chunks[p_entity.id] = p_entity
        elif isinstance(p_entity, ParserCodeEntity):
            p_code_entities[p_entity.id] = p_entity
        elif isinstance(p_entity, ParserRelationship):
            p_relationships.append(p_entity)
        else:
            logger.warning(f"Adapter: Unknown Pydantic entity type received: {type(p_entity)}")

    logger.debug(
        f"Adapter: Collected {len(p_repositories)} Repositories, {len(p_source_files)} SourceFiles, "
        f"{len(p_text_chunks)} TextChunks, {len(p_code_entities)} CodeEntities, "
        f"and {len(p_relationships)} Relationships from parser stream."
    )

    adapted_dps_map: Dict[str, DataPoint] = {}

    for p_repo_id, p_repo in p_repositories.items():
        adapted_repo = AdaptedRepositoryDP(
            id=uuid.uuid4(),
            path=p_repo.path
        )
        adapted_dps_map[p_repo_id] = adapted_repo

    for p_sf_id, p_sf in p_source_files.items():
        adapted_sf = AdaptedSourceFileDP(
            id=uuid.uuid4(),
            file_path=p_sf.file_path,
            relative_path=getattr(p_sf, 'relative_path', p_sf.file_path),
            language_key=getattr(p_sf, 'language_key', 'unknown'),
            timestamp=p_sf.timestamp
        )
        adapted_dps_map[p_sf_id] = adapted_sf

    for p_tc_id, p_tc in p_text_chunks.items():
        parsed_id_info = parse_text_chunk_id(p_tc.id)
        original_sf_id = parsed_id_info[0] if parsed_id_info else "unknown_source_file"

        adapted_tc = AdaptedTextChunkDP(
            id=uuid.uuid4(),
            original_parser_source_file_id=original_sf_id,
            original_parser_chunk_id=p_tc.id,
            chunk_index=parsed_id_info[1] if parsed_id_info else -1,
            start_line=p_tc.start_line,
            end_line=p_tc.end_line,
            chunk_content=p_tc.chunk_content
        )
        adapted_dps_map[p_tc_id] = adapted_tc

    for p_ce_id, p_ce in p_code_entities.items():
        parsed_ce_id_info = parse_code_entity_id(p_ce.id)
        original_tc_id = parsed_ce_id_info[0] if parsed_ce_id_info else "unknown_text_chunk"

        original_sf_id_from_tc = "unknown_source_file"
        if original_tc_id != "unknown_text_chunk":
            parsed_tc_id_info_for_sf = parse_text_chunk_id(original_tc_id)
            if parsed_tc_id_info_for_sf:
                original_sf_id_from_tc = parsed_tc_id_info_for_sf[0]

        AdaptedClass = PARSER_ENTITY_TYPE_TO_ADAPTED_DP_CLASS.get(p_ce.type, AdaptedCodeEntityDP)

        lang_key_for_ce = "unknown"
        if original_sf_id_from_tc in p_source_files:
            lang_key_for_ce = getattr(p_source_files[original_sf_id_from_tc], 'language_key', 'unknown')

        adapted_ce = AdaptedClass(
            id=uuid.uuid4(),
            original_parser_code_entity_id=p_ce.id,
            original_parser_source_file_id=original_sf_id_from_tc,
            original_parser_text_chunk_id=original_tc_id,
            entity_parser_type=p_ce.type,
            name=getattr(p_ce, 'name', None),
            start_line=getattr(p_ce, 'start_line', -1),
            end_line=getattr(p_ce, 'end_line', -1),
            snippet_content=p_ce.snippet_content,
            language_key=lang_key_for_ce
        )
        adapted_dps_map[p_ce_id] = adapted_ce

    logger.debug(f"Adapter: Created {len(adapted_dps_map)} initial Adapted DataPoint instances.")

    for p_rel in p_relationships:
        source_dp: Optional[DataPoint] = adapted_dps_map.get(p_rel.source_id)
        target_dp: Optional[DataPoint] = adapted_dps_map.get(p_rel.target_id)

        if not source_dp:
            logger.warning(f"Adapter: Source DataPoint not found for original ID '{p_rel.source_id}' in Pydantic Relationship: {p_rel.type}")
            continue

        rel_type_lc = p_rel.type.lower()

        if rel_type_lc == "contains_file" and isinstance(source_dp, AdaptedRepositoryDP) and target_dp and isinstance(target_dp, AdaptedSourceFileDP):
            source_dp.contains_files.append(target_dp)
            target_dp.part_of_repository = source_dp

        elif rel_type_lc == "contains_chunk" and isinstance(source_dp, AdaptedSourceFileDP) and target_dp and isinstance(target_dp, AdaptedTextChunkDP):
            source_dp.contains_chunks.append(target_dp)
            target_dp.chunk_of_file = source_dp

        elif rel_type_lc == "contains_entity":
            if isinstance(source_dp, AdaptedTextChunkDP) and target_dp and isinstance(target_dp, AdaptedCodeEntityDP):
                source_dp.defines_code_entities.append(target_dp)
                target_dp.defined_in_chunk = source_dp
            elif isinstance(source_dp, AdaptedSourceFileDP) and target_dp and isinstance(target_dp, AdaptedCodeEntityDP):
                source_dp.defines_code_entities.append(target_dp)
                target_dp.part_of_file = source_dp

        elif rel_type_lc == "calls" and isinstance(source_dp, AdaptedFunctionEntityDP) and target_dp and isinstance(target_dp, AdaptedCodeEntityDP): # Target could be any callable
            source_dp.calls.append(target_dp)

        elif rel_type_lc == "extends" and isinstance(source_dp, AdaptedClassEntityDP) and target_dp and isinstance(target_dp, AdaptedClassEntityDP):
            source_dp.inherits_from.append(target_dp)

        elif rel_type_lc == "defines_method" and isinstance(source_dp, AdaptedClassEntityDP) and target_dp and isinstance(target_dp, AdaptedFunctionEntityDP):
            source_dp.defines_methods.append(target_dp)

        elif rel_type_lc == "imports":
            if isinstance(source_dp, AdaptedSourceFileDP):
                source_dp.imports_names.append(p_rel.target_id)
            else:
                logger.warning(f"Adapter: IMPORTS target '{p_rel.target_id}' is a string, but source DP type {type(source_dp).__name__} "
                               f"(original ID: {p_rel.source_id}) does not have an 'imports_names' field configured for it.")
        else:
            if target_dp:
                logger.warning(f"Adapter: Unhandled Pydantic Relationship type '{p_rel.type}' "
                               f"between DataPoints: {type(source_dp).__name__} (ID: {source_dp.id}) "
                               f"-> {type(target_dp).__name__} (ID: {target_dp.id})")
            elif p_rel.target_id not in adapted_dps_map:
                 logger.warning(f"Adapter: Target for Pydantic Relationship '{p_rel.type}' with target_id '{p_rel.target_id}' "
                               f"was not found as an adapted DataPoint and is not a handled literal type.")


    final_list_of_datapoints = list(adapted_dps_map.values())
    logger.info(f"Adapter: Finished. Produced {len(final_list_of_datapoints)} interlinked Cognee DataPoint instances.")
    return final_list_of_datapoints
