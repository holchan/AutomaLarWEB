# .roo/cognee/tests/parser/parsers/test_dockerfile_parser.py
import pytest
import asyncio
import os
from pathlib import Path
from typing import List, TYPE_CHECKING

pytestmark = pytest.mark.asyncio

try:
    from src.parser.entities import TextChunk, Relationship, ParserOutput
    from src.parser.parsers.dockerfile_parser import DockerfileParser
except ImportError as e:
    pytest.skip(f"Skipping Dockerfile parser tests: Failed to import dependencies - {e}", allow_module_level=True)

if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser
    from pydantic import BaseModel

TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "dockerfile"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

@pytest.fixture(scope="module")
def parser() -> DockerfileParser:
    """Provides a DockerfileParser instance."""
    return DockerfileParser()

from ..conftest import run_parser_and_save_output

async def test_parse_empty_dockerfile(parser: DockerfileParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing an empty Dockerfile (named Dockerfile)."""
    empty_file = tmp_path / "Dockerfile"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0, "Empty Dockerfile should yield no DataPoints"

async def test_parse_dockerfile_from_test_data(parser: DockerfileParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing the Dockerfile from the test_data directory."""
    test_file = TEST_DATA_DIR / "Dockerfile"
    if not test_file.is_file():
        pytest.skip(f"Dockerfile not found in test data: {test_file}")

    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0, "Expected DataPoints from Dockerfile"

    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(chunks) > 0, "Expected TextChunk(s)"
    assert len(rels) == len(chunks), "Expected one CONTAINS_CHUNK per TextChunk"
    assert all(isinstance(dp, (TextChunk, Relationship)) for dp in results), "Only TextChunk/Relationship expected"
    assert all(r.type == "CONTAINS_CHUNK" for r in rels), "Expected only CONTAINS_CHUNK relationships"

    first_chunk = chunks[0]
    assert isinstance(first_chunk.id, str) and first_chunk.id.endswith(":0"), "Chunk ID format/index error"
    assert "# Use an official Python runtime as a parent image" in first_chunk.chunk_content
    assert "FROM python:3.9-slim" in first_chunk.chunk_content
    assert first_chunk.start_line is not None and first_chunk.end_line is not None

    file_id = rels[0].source_id
    assert file_id.startswith("test_file_id_"), "Relationship source ID (file_id) error"
    assert all(r.source_id == file_id for r in rels), "All relationships should link FROM the same file"
    chunk_ids_set = {c.id for c in chunks}
    rel_target_ids_set = {r.target_id for r in rels}
    assert chunk_ids_set == rel_target_ids_set, "Mismatch between chunk IDs and relationship target IDs"

    full_text = "".join(c.chunk_content for c in chunks)
    assert "FROM python:3.9-slim" in full_text, "FROM instruction missing"
    assert "WORKDIR /app" in full_text, "WORKDIR instruction missing"
    assert "COPY requirements.txt ." in full_text, "COPY instruction missing"
    assert "RUN pip install --no-cache-dir -r requirements.txt" in full_text, "RUN instruction missing"
    assert "COPY . ." in full_text, "Second COPY instruction missing"
    assert "EXPOSE 8000" in full_text, "EXPOSE instruction missing"
    assert 'CMD ["python", "main.py"]' in full_text, "CMD instruction missing"
    assert "# Comments should be preserved" in full_text
