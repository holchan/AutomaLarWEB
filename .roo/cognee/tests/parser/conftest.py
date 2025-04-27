# FILE: tests/parser/conftest.py (NEW FILE)
import pytest
import json
import hashlib
from pathlib import Path
from typing import List, TYPE_CHECKING
from uuid import UUID # Import UUID

# Avoid runtime import errors if BaseParser isn't directly used
if TYPE_CHECKING:
    # Make sure these paths are correct relative to the project root if needed
    # Or rely on Python's path resolution if src is added to PYTHONPATH
    try:
        from src.parser.parsers.base_parser import BaseParser
        from src.parser.entities import DataPoint
    except ImportError:
        # Define dummy types if imports fail during static analysis
        BaseParser = type('BaseParser', (object,), {})
        DataPoint = type('DataPoint', (object,), {})


# --- Helper Function as Fixture ---
# Scope="function" means this fixture is created once per test session
@pytest.fixture(scope="function") # Change scope to function for better isolation if needed
def run_parser_and_save_output():
    """
    Fixture providing a helper function to run a parser, save results,
    and return DataPoint objects.
    """
    # Define the actual helper function that the fixture will return
    async def _run_parser(
        parser: 'BaseParser',
        test_file_path: Path,
        output_dir: Path # Typically tmp_path provided by pytest fixture
    ) -> List['DataPoint']:
        """
        Runs the parser on a given file path, saves the model dump results to a JSON
        file in output_dir, and returns the list of original DataPoint objects.
        """
        if not test_file_path.is_file():
            pytest.fail(f"Test input file not found: {test_file_path}")

        # Generate a consistent file_id for the test run based on the absolute path
        file_id_base = str(test_file_path.absolute())
        # Using SHA1 for a shorter, manageable hash for test purposes
        file_id = f"test_file_id_{hashlib.sha1(file_id_base.encode()).hexdigest()[:10]}"

        results_objects: List[DataPoint] = []

        try:
            # Collect DataPoint objects from the parser
            async for dp in parser.parse(file_path=str(test_file_path), file_id=file_id):
                results_objects.append(dp)
        except Exception as e:
            print(f"\nERROR during parser execution for {test_file_path.name}: {e}")
            pytest.fail(f"Parser execution failed for {test_file_path.name}: {e}", pytrace=True)

        # Define output filename based on the test file stem
        output_filename = output_dir / f"parsed_{test_file_path.stem}_output.json"
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            # Generate JSON-compatible dicts using model_dump(mode='json') just before saving
            # mode='json' handles types like UUID, datetime etc. automatically
            payloads_to_save = [dp.model_dump(mode='json') for dp in results_objects]
            with open(output_filename, "w", encoding="utf-8") as f:
                # Dump the list of payloads to the JSON file
                # default=str can be a fallback if mode='json' misses something, but usually not needed
                json.dump(payloads_to_save, f, indent=2, ensure_ascii=False, sort_keys=True, default=str)
            print(f"\n[Test Output] Saved parser results for '{test_file_path.name}' to: {output_filename}")
        except AttributeError:
             # Handle cases where model_dump might not exist on an object in the list
             print(f"\n[Test Output] WARNING: model_dump() not found on one or more objects for {test_file_path.name}. Cannot save JSON.")
        except Exception as e:
            # Log a warning if saving the output fails, but don't fail the test
            print(f"\n[Test Output] WARNING: Failed to save test output for {test_file_path.name}: {e}")

        # Return the original list of DataPoint objects for assertions in the test
        return results_objects
    # The fixture returns the inner function, which tests can then call
    return _run_parser
