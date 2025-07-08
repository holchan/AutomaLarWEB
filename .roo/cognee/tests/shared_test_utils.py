from pathlib import Path
from typing import List, Optional

from src.parser.utils import logger
from src.parser.utils import read_file_content
from src.parser.entities import CodeEntity, RawSymbolReference

async def load_test_file_content(file_path: Path) -> str:
    """Reads content from a test file faithfully."""
    if not file_path.is_file():
        logger.warning(f"Test data file not found: {file_path}.")
        return ""
    return await read_file_content(str(file_path)) or ""

def find_code_entity_by_exact_temp_id(entities: List[CodeEntity], temp_id: str) -> Optional[CodeEntity]:
    """Finds a single CodeEntity by its exact temporary ID (FQN@line)."""
    found = [e for e in entities if e.id == temp_id]
    if not found: return None
    if len(found) > 1:
        logger.warning(f"Found multiple CEs for temp_id '{temp_id}': {[e.id for e in found]}")
    return found[0]

def find_raw_symbol_references(
    references: List[RawSymbolReference],
    *,
    source_entity_id_prefix: Optional[str] = None,
    target_expression: Optional[str] = None,
    reference_type: Optional[str] = None
) -> List[RawSymbolReference]:
    """Finds raw symbol references matching specific criteria."""
    found = []
    for ref in references:
        match = True
        if source_entity_id_prefix is not None and not ref.source_entity_id.startswith(source_entity_id_prefix):
            # Use startswith for temp IDs like 'FQN@line' to make tests less brittle
            match = False
        if target_expression is not None and ref.target_expression != target_expression:
            match = False
        if reference_type is not None and ref.reference_type != reference_type:
            match = False
        if match:
            found.append(ref)
    return found
