import pytest
import asyncio
from pathlib import Path
from typing import List, Union, TYPE_CHECKING

from pydantic import BaseModel

pytestmark = pytest.mark.asyncio

try:
    from src.parser.entities import TextChunk, Relationship
    ParserOutput = Union[TextChunk, Relationship]
    from src.parser.parsers.dockerfile_parser import DockerfileParser
except ImportError as e:
    pytest.skip(f"Skipping Dockerfile parser tests: Failed to import dependencies - {e}", allow_module_level=True)

if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser

TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "dockerfile"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

@pytest.fixture(scope="module")
def parser() -> DockerfileParser:
    return DockerfileParser()

from ..conftest import run_parser_and_save_output

async def test_parse_empty_dockerfile(parser: DockerfileParser, tmp_path: Path, run_parser_and_save_output):
    empty_file = tmp_path / "Dockerfile"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0

async def test_parse_dockerfile_from_test_data(parser: DockerfileParser, tmp_path: Path, run_parser_and_save_output):
    test_file = TEST_DATA_DIR / "Dockerfile"
    if not test_file.is_file():
        pytest.skip(f"Dockerfile not found in test data: {test_file}")

    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(chunks) > 0
    assert len(rels) == len(chunks)
    assert all(isinstance(dp, (TextChunk, Relationship)) for dp in results)
    assert all(r.type == "CONTAINS_CHUNK" for r in rels)

    first_chunk = chunks[0]
    assert isinstance(first_chunk.id, str) and first_chunk.id.endswith(":0")
    assert "# Use an official Python runtime as a parent image" in first_chunk.chunk_content
    assert "FROM python:3.9-slim" in first_chunk.chunk_content
    assert isinstance(first_chunk.start_line, int)
    assert isinstance(first_chunk.end_line, int)

    file_id_from_rel = rels[0].source_id
    assert file_id_from_rel.startswith("test_parser_file_id_")
    assert all(r.source_id == file_id_from_rel for r in rels)
    chunk_ids_set = {c.id for c in chunks}
    rel_target_ids_set = {r.target_id for r in rels}
    assert chunk_ids_set == rel_target_ids_set

    full_text = "".join(c.chunk_content for c in chunks)
    assert "FROM python:3.9-slim" in full_text
    assert "WORKDIR /app" in full_text
    assert "COPY . /app" in full_text
    assert "RUN pip install --no-cache-dir -r requirements.txt" in full_text
    assert 'CMD ["python", "app.py"]' in full_text
