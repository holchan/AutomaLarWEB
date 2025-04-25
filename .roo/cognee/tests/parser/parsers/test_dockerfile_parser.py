import pytest
import asyncio
import os
import json
import hashlib
from pathlib import Path
from typing import List, TYPE_CHECKING

# Use pytest-asyncio for async tests
pytestmark = pytest.mark.asyncio

# Import the parser and entity types
try:
    from src.parser.parsers.dockerfile_parser import DockerfileParser
    # Expecting only TextChunk for now
    from src.parser.entities import DataPoint, TextChunk
except ImportError as e:
    pytest.skip(f"Skipping Dockerfile parser tests: Failed to import dependencies - {e}", allow_module_level=True)


# Avoid runtime import errors if BaseParser isn't directly used
if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser

# --- Test Configuration ---
# <<< CHANGE: Define TEST_DATA_DIR for Dockerfile >>>
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "dockerfile"
if not TEST_DATA_DIR.is_dir():
     pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

# --- Helper Function (Copied from previous step) ---
# <<< Helper function `run_parser_and_save_output` remains the same >>>
async def run_parser_and_save_output(
    parser: 'BaseParser',
    test_file_path: Path,
    output_dir: Path
) -> List['DataPoint']:
    # ... (helper code as before) ...
    if not test_file_path.is_file():
        pytest.fail(f"Test input file not found: {test_file_path}")

    file_id_base = str(test_file_path.absolute())
    file_id = f"test_file_id_{hashlib.sha1(file_id_base.encode()).hexdigest()[:10]}"

    results_objects: List[DataPoint] = []
    results_payloads: List[dict] = []

    try:
        async for dp in parser.parse(file_path=str(test_file_path), file_id=file_id):
            results_objects.append(dp)
            if hasattr(dp, 'model_dump'):
                payload = dp.model_dump()
            elif hasattr(dp, 'payload'):
                payload = dp.payload
            else:
                payload = {"id": getattr(dp, 'id', 'unknown'), "type": "UnknownPayloadStructure"}
            results_payloads.append(payload)
    except Exception as e:
        print(f"\nERROR during parser execution for {test_file_path.name}: {e}")
        pytest.fail(f"Parser execution failed for {test_file_path.name}: {e}", pytrace=True)

    output_filename = output_dir / f"parsed_{test_file_path.stem}_output.json"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(results_payloads, f, indent=2, ensure_ascii=False, sort_keys=True)
        print(f"\n[Test Output] Saved parser results for '{test_file_path.name}' to: {output_filename}")
    except Exception as e:
        print(f"\n[Test Output] WARNING: Failed to save test output for {test_file_path.name}: {e}")

    return results_objects


# --- Parser Fixture ---
@pytest.fixture(scope="module")
def parser() -> DockerfileParser:
    """Provides a DockerfileParser instance."""
    return DockerfileParser()

# --- Test Cases ---

async def test_parse_empty_dockerfile(parser: DockerfileParser, tmp_path: Path):
    """Test parsing an empty Dockerfile (named Dockerfile)."""
    empty_file = tmp_path / "Dockerfile" # Exact name match
    empty_file.touch()
    results = await run_parser_and_save_output(parser, empty_file, tmp_path)
    assert len(results) == 0, "Empty Dockerfile should yield no DataPoints"

# <<< CHANGE: Test now uses the file from test_data >>>
async def test_parse_dockerfile_from_test_data(parser: DockerfileParser, tmp_path: Path):
    """Test parsing the Dockerfile from the test_data directory."""
    test_file = TEST_DATA_DIR / "Dockerfile" # Use the actual file
    if not test_file.is_file():
        pytest.skip(f"Dockerfile not found in test data: {test_file}")

    results = await run_parser_and_save_output(parser, test_file, tmp_path)

    # Expect only TextChunk results currently
    assert len(results) > 0, "Expected DataPoints from Dockerfile"
    payloads = [dp.payload for dp in results]
    assert all(p.get("type") == "TextChunk" for p in payloads), "Only TextChunks expected"

    # Check basic content integrity based on the *actual* content of test_data/dockerfile/Dockerfile
    # Read the file content to verify against chunks
    original_content = test_file.read_text(encoding="utf-8")
    full_text = "".join(p.get("text","") for p in payloads)

    # Add assertions based on the content of your test Dockerfile
    # Example assertions (replace with actual content checks):
    assert "# Add your Dockerfile content checks here" in original_content # Placeholder check
    assert "FROM" in full_text, "FROM instruction missing"
    assert "RUN" in full_text, "RUN instruction missing (if applicable)"
    assert "COPY" in full_text, "COPY instruction missing (if applicable)"
    # ... add more specific checks based on the actual Dockerfile ...


# <<< REMOVE: Remove tests that created temporary content, use the test_data file instead >>>
# async def test_parse_simple_dockerfile(parser: DockerfileParser, tmp_path: Path):
#    ... (removed) ...
# async def test_parse_multiline_dockerfile(parser: DockerfileParser, tmp_path: Path):
#    ... (removed) ...
