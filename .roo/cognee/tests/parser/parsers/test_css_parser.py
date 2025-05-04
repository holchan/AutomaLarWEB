# .roo/cognee/tests/parser/parsers/test_css_parser.py
import pytest
import asyncio
import os
from pathlib import Path
from typing import List, TYPE_CHECKING

pytestmark = pytest.mark.asyncio

try:
    from src.parser.entities import TextChunk, Relationship, ParserOutput
    from src.parser.parsers.css_parser import CssParser
except ImportError as e:
    pytest.skip(f"Skipping CSS parser tests: Failed to import dependencies - {e}", allow_module_level=True)

if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser
    from pydantic import

TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "css"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

@pytest.fixture(scope="module")
def parser() -> CssParser:
    """Provides a CssParser instance."""
    return CssParser()

from ..conftest import run_parser_and_save_output

async def test_parse_empty_css_file(parser: CssParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing an empty CSS file."""
    empty_file = tmp_path / "empty.css"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0, "Empty .css file should yield no DataPoints"

async def test_parse_style_css_file(parser: CssParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing style.css from test_data."""
    test_file = TEST_DATA_DIR / "style.css"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0, "Expected DataPoints from style.css"

    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(chunks) > 0, "Expected TextChunk(s)"
    assert len(rels) == len(chunks), "Expected one CONTAINS_CHUNK per TextChunk"
    assert all(isinstance(dp, (TextChunk, Relationship)) for dp in results), "Only TextChunk/Relationship expected"
    assert all(r.type == "CONTAINS_CHUNK" for r in rels), "Expected only CONTAINS_CHUNK relationships"

    first_chunk = chunks[0]
    assert isinstance(first_chunk.id, str) and first_chunk.id.endswith(":0"), "Chunk ID format/index error"
    assert "/* Basic CSS styles */" in first_chunk.chunk_content, "Comment missing in first chunk"
    assert "body {" in first_chunk.chunk_content, "body selector missing in first chunk"
    assert first_chunk.start_line is not None and first_chunk.end_line is not None

    file_id = rels[0].source_id # Get file_id from the first relationship's source
    assert file_id.startswith("test_file_id_"), "Relationship source ID (file_id) error"
    assert all(r.source_id == file_id for r in rels), "All relationships should link FROM the same file"
    chunk_ids_set = {c.id for c in chunks}
    rel_target_ids_set = {r.target_id for r in rels}
    assert chunk_ids_set == rel_target_ids_set, "Mismatch between chunk IDs and relationship target IDs"

    full_text = "".join(c.chunk_content for c in chunks)
    assert "body {" in full_text
    assert "font-family: sans-serif;" in full_text
    assert "background-color: #f4f4f4;" in full_text
    assert "/* Light grey background */" in full_text
    assert "h1," in full_text
    assert "h2 {" in full_text
    assert ".container {" in full_text
    assert "box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);" in full_text
    assert ".container > p:first-child {" in full_text
    assert "font-weight: bold;" in full_text
    assert "@import url(\"another.css\");" in full_text

async def test_parse_css_with_media_query(parser: CssParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing CSS containing a media query and pseudo-elements."""
    content = """
/* Comment */
body { color: black; font-size: 1rem; }

@media screen and (min-width: 900px) {
    article {
        padding: 1rem 3rem; /* Indented rule */
        border: 1px solid #ccc;
    }
    body::before {
        content: "Large screen";
        display: block; /* Another property */
        position: absolute;
    }
}

p { font-size: 16px; }
/* Another comment */
"""
    test_file = tmp_path / "media.css"
    test_file.write_text(content, encoding="utf-8")
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0, "Expected DataPoints from media query CSS file"

    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(chunks) > 0
    assert len(rels) == len(chunks)
    assert all(isinstance(dp, (TextChunk, Relationship)) for dp in results)
    assert all(r.type == "CONTAINS_CHUNK" for r in rels)

    full_text = "".join(c.chunk_content for c in chunks)
    assert "/* Comment */" in full_text
    assert "body { color: black; font-size: 1rem; }" in full_text
    assert "@media screen and (min-width: 900px)" in full_text
    assert "article {" in full_text
    assert "padding: 1rem 3rem;" in full_text
    assert "border: 1px solid #ccc;" in full_text
    assert "body::before {" in full_text
    assert 'content: "Large screen";' in full_text
    assert "display: block;" in full_text
    assert "position: absolute;" in full_text
    assert "p { font-size: 16px; }" in full_text
    assert "/* Another comment */" in full_text
