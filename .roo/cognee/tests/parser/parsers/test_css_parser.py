# .roo/cognee/tests/parser/parsers/test_css_parser.py
import pytest
import asyncio
import os
import json
import hashlib
from pathlib import Path
from typing import List, TYPE_CHECKING
from pathlib import Path

TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "css"

if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

pytestmark = pytest.mark.asyncio

try:
    from src.parser.parsers.css_parser import CssParser
    from src.parser.entities import DataPoint, TextChunk
except ImportError as e:
    pytest.skip(f"Skipping CSS parser tests: Failed to import dependencies - {e}", allow_module_level=True)

if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser

@pytest.fixture(scope="module")
def parser() -> CssParser:
    """Provides a CssParser instance."""
    return CssParser()

async def test_parse_empty_css_file(parser: CssParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing an empty CSS file."""
    empty_file = tmp_path / "empty.css"
    empty_file.touch()
    results = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0, "Empty .css file should yield no DataPoints"

async def test_parse_style_css_file(parser: CssParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing style.css from test_data."""
    test_file = TEST_DATA_DIR / "style.css"
    results = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0, "Expected DataPoints from style.css"
    payloads = [dp.model_dump(mode='json') for dp in results]
    assert all(p.get("type") == "TextChunk" for p in payloads), "Only TextChunks expected"

    first_chunk = payloads[0]
    first_chunk_meta = first_chunk.get("metadata", {})
    assert first_chunk_meta.get("chunk_index") == 0, "First chunk index mismatch"
    assert "/* Basic CSS styles */" in first_chunk.get("text_content",""), "Comment missing"
    assert "body {" in first_chunk.get("text_content",""), "body selector missing"
    assert first_chunk_meta.get("chunk_of", "").startswith("test_file_id_"), "Chunk parent ID invalid"

    full_text = "".join(p.get("text_content","") for p in payloads)
    original_content = test_file.read_text(encoding="utf-8")

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
    results = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0, "Expected DataPoints from media query CSS file"
    payloads = [dp.model_dump(mode='json') for dp in results]
    assert all(p.get("type") == "TextChunk" for p in payloads), "Only TextChunks expected"

    full_text = "".join(p.get("text_content","") for p in payloads)
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
