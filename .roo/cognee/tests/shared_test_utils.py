from pathlib import Path
from typing import List, Optional

from src.parser.utils import logger
from src.parser.utils import read_file_content
from src.parser.entities import CodeEntity, Relationship, CallSiteReference

async def load_test_file_content(file_path: Path) -> str:
    """
    Reads content from a test file faithfully.
    Returns empty string if file not found or content is None.
    """
    if not file_path.is_file():
        logger.warning(f"Test data file not found: {file_path}. Returning empty content.")
        return ""
    raw_content = await read_file_content(str(file_path))
    if raw_content is None:
        logger.warning(f"Failed to read content from {file_path}. Returning empty content.")
        return ""
    return raw_content

def find_code_entity_by_id_prefix(entities: List[CodeEntity], id_prefix: str) -> List[CodeEntity]:
    """Finds CodeEntities where the FQN part of the temp ID starts with id_prefix."""
    return [e for e in entities if e.id.split('@')[0].startswith(id_prefix)]

def find_code_entity_by_exact_temp_id(entities: List[CodeEntity], temp_id: str) -> Optional[CodeEntity]:
    """Finds a single CodeEntity by its exact temporary ID (FQN@line)."""
    found = [e for e in entities if e.id == temp_id]
    if not found: return None
    if len(found) > 1:
        logger.warning(f"Found multiple CEs for temp_id '{temp_id}': {[e.id for e in found]}")
    return found[0]

def find_relationships(
    relationships: List[Relationship],
    source_id: Optional[str] = None,
    target_id: Optional[str] = None,
    rel_type: Optional[str] = None
) -> List[Relationship]:
    """Filters relationships based on provided source_id, target_id, and rel_type."""
    found = relationships
    if source_id is not None: found = [r for r in found if r.source_id == source_id]
    if target_id is not None: found = [r for r in found if r.target_id == target_id]
    if rel_type is not None: found = [r for r in found if r.type == rel_type]
    return found

def find_call_sites(
    call_sites: List[CallSiteReference],
    calling_entity_temp_id: Optional[str] = None,
    called_name_expr: Optional[str] = None,
    at_line_0: Optional[int] = None,
    arg_count: Optional[int] = None,
) -> List[CallSiteReference]:
    """Filters call sites based on provided criteria."""
    found = call_sites
    if calling_entity_temp_id is not None:
        found = [cs for cs in found if cs.calling_entity_temp_id == calling_entity_temp_id]
    if called_name_expr is not None:
        found = [cs for cs in found if cs.called_name_expr == called_name_expr]
    if at_line_0 is not None:
        found = [cs for cs in found if cs.line_of_call_0_indexed == at_line_0]
    if arg_count is not None:
        found = [cs for cs in found if cs.argument_count == arg_count]
    return found
