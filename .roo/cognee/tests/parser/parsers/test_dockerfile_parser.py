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
# Helper function `run_parser_and_save_output` is now expected to be in conftest.py
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
    payloads = [dp.model_dump(mode='json') for dp in results]
    assert all(p.get("type") == "TextChunk" for p in payloads), "Only TextChunks expected"

    # Check basic content integrity based on the *actual* content of test_data/dockerfile/Dockerfile
    # Read the file content to verify against chunks
    original_content = test_file.read_text(encoding="utf-8")
    full_text = "".join(p.get("text_content","") for p in payloads) # Use text_content

    # Add assertions based on the content of your test Dockerfile
    # Example assertions (replace with actual content checks):
    # assert "# Add your Dockerfile content checks here" in original_content # Placeholder check
    assert "FROM" in full_text, "FROM instruction missing"
    assert "RUN" in full_text, "RUN instruction missing (if applicable)"
    assert "COPY" in full_text, "COPY instruction missing (if applicable)"
    # ... add more specific checks based on the actual Dockerfile ...


# <<< REMOVE: Remove tests that created temporary content, use the test_data file instead >>>
# async def test_parse_simple_dockerfile(parser: DockerfileParser, tmp_path: Path):
#    ... (removed) ...
# async def test_parse_multiline_dockerfile(parser: DockerfileParser, tmp_path: Path):
#    ... (removed) ...
