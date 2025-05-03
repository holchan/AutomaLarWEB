# .roo/cognee/tests/parser/parsers/test_dockerfile_parser.py
import pytest
import asyncio
import os
import json
import hashlib
from pathlib import Path
from typing import List, TYPE_CHECKING

pytestmark = pytest.mark.asyncio

try:
    from src.parser.parsers.dockerfile_parser import DockerfileParser
    from src.parser.entities import DataPoint, TextChunk
except ImportError as e:
    pytest.skip(f"Skipping Dockerfile parser tests: Failed to import dependencies - {e}", allow_module_level=True)

if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser

TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "dockerfile"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

@pytest.fixture(scope="module")
def parser() -> DockerfileParser:
    """Provides a DockerfileParser instance."""
    return DockerfileParser()

async def test_parse_empty_dockerfile(parser: DockerfileParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing an empty Dockerfile (named Dockerfile)."""
    empty_file = tmp_path / "Dockerfile"
    empty_file.touch()
    results = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0, "Empty Dockerfile should yield no DataPoints"

async def test_parse_dockerfile_from_test_data(parser: DockerfileParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing the Dockerfile from the test_data directory."""
    test_file = TEST_DATA_DIR / "Dockerfile"
    if not test_file.is_file():
        pytest.skip(f"Dockerfile not found in test data: {test_file}")

    results = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0, "Expected DataPoints from Dockerfile"
    payloads = [dp.model_dump(mode='json') for dp in results]
    assert all(p.get("type") == "TextChunk" for p in payloads), "Only TextChunks expected"

    original_content = test_file.read_text(encoding="utf-8")
    full_text = "".join(p.get("text_content","") for p in payloads)

    assert "FROM" in full_text, "FROM instruction missing"
    assert "RUN" in full_text, "RUN instruction missing (if applicable)"
    assert "COPY" in full_text, "COPY instruction missing (if applicable)"
