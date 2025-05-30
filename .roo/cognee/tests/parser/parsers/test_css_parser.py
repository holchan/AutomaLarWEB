import pytest
import asyncio
from pathlib import Path
from typing import List, Union, TYPE_CHECKING

from pydantic import BaseModel

pytestmark = pytest.mark.asyncio

try:
    from src.parser.entities import TextChunk, Relationship, ParserOutput
    from src.parser.parsers.css_parser import CssParser
except ImportError as e:
    pytest.skip(f"Skipping CSS parser tests: Failed to import dependencies - {e}", allow_module_level=True)

if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser


TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "css"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

@pytest.fixture(scope="module")
def parser() -> CssParser:
    return CssParser()

from ..conftest import run_parser_and_save_output

async def test_parse_empty_css_file(parser: CssParser, tmp_path: Path, run_parser_and_save_output):
    empty_file = tmp_path / "empty.css"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0

async def test_parse_style_css_file(parser: CssParser, tmp_path: Path, run_parser_and_save_output):
    test_file = TEST_DATA_DIR / "style.css"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)
    assert len(results) > 0
    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]
    assert len(chunks) > 0 and len(rels) == len(chunks)
    assert all(isinstance(dp, (TextChunk, Relationship)) for dp in results)
    assert all(r.type == "CONTAINS_CHUNK" for r in rels)
    first_chunk = chunks[0]
    assert isinstance(first_chunk.id, str) and first_chunk.id.endswith(":0")
    assert "/* Basic CSS styles */" in first_chunk.chunk_content
    file_id_from_rel = rels[0].source_id
    assert file_id_from_rel.startswith("test_parser_file_id_")
    assert all(r.source_id == file_id_from_rel for r in rels)
    assert {c.id for c in chunks} == {r.target_id for r in rels}
    full_text = "".join(c.chunk_content for c in chunks)
    assert "@import url(\"another.css\");" in full_text

async def test_parse_css_with_media_query(parser: CssParser, tmp_path: Path, run_parser_and_save_output):
    content = "body { color: black; }\n@media screen { article { padding: 1rem; } }"
    test_file = tmp_path / "media.css"
    test_file.write_text(content, encoding="utf-8")
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)
    assert len(results) > 0
    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]
    assert len(chunks) > 0 and len(rels) == len(chunks)
    full_text = "".join(c.chunk_content for c in chunks)
    assert "body { color: black; }" in full_text and "@media screen" in full_text
