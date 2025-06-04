# .roo/cognee/tests/conftest.py
import pytest
import json
import hashlib
from pathlib import Path
from typing import List, Union, TYPE_CHECKING # Add TYPE_CHECKING if not already there

from pydantic import BaseModel

# Conditional import for type hinting BaseParser and ParserOutputUnion
if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser
    from src.parser.entities import Repository, SourceFile, TextChunk, CodeEntity, Relationship # Ensure all are imported
    ParserOutputUnion = Union[Repository, SourceFile, TextChunk, CodeEntity, Relationship]


@pytest.fixture(scope="function") # Keep scope as function if parsers are not stateless or have internal state per file
# The fixture itself IS NOT ASYNC, it RETURNS an async function.
def run_parser_and_save_output():
    # This inner function is what the tests will await
    async def _run_parser(
        parser: 'BaseParser', # Use forward reference string for BaseParser
        test_file_path: Path,
        output_dir: Path,
        file_id_override: str = None # Optional override for file_id
    ) -> List[BaseModel]: # Return type hint
        if not test_file_path.is_file():
            pytest.fail(f"Test input file not found: {test_file_path}")

        if file_id_override:
            file_id_for_parser = file_id_override
        else:
            # Create a consistent but test-specific file_id
            file_id_base = str(test_file_path.absolute()) # Use absolute path for consistency
            # Use a simple hash to keep it somewhat readable but unique enough for tests
            file_id_for_parser = f"test_parser_file_id_{hashlib.sha1(file_id_base.encode()).hexdigest()[:10]}"

        results_pydantic_objects: List[BaseModel] = []
        try:
            async for item in parser.parse(file_path=str(test_file_path), file_id=file_id_for_parser):
                results_pydantic_objects.append(item)
        except Exception as e:
            # Print error immediately for easier debugging in CI/logs
            print(f"\nERROR during parser execution for {test_file_path.name}: {type(e).__name__} - {e}")
            pytest.fail(f"Parser execution failed for {test_file_path.name}: {e}", pytrace=True)

        # --- Output saving logic (optional but useful for debugging) ---
        output_filename = output_dir / f"parsed_{parser.parser_type}_{test_file_path.stem}_output.json"
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            # Convert Pydantic models to dicts for JSON serialization
            payloads_to_save = [dp.model_dump(mode='json') for dp in results_pydantic_objects]
            with open(output_filename, "w", encoding="utf-8") as f:
                json.dump(payloads_to_save, f, indent=2, ensure_ascii=False, sort_keys=True, default=str) # Added default=str for complex types
            # Use print for test output, it's captured by pytest with -s
            print(f"\n[Test Output] Saved parser results for '{test_file_path.name}' to: {output_filename}")
        except AttributeError: # If some item doesn't have model_dump (should not happen with Pydantic)
             print(f"\n[Test Output] WARNING: model_dump() not found for an item from {test_file_path.name}.")
        except Exception as e_save:
            print(f"\n[Test Output] WARNING: Failed to save test output for {test_file_path.name}: {e_save}")
        return results_pydantic_objects
    return _run_parser # The fixture returns the async helper function
