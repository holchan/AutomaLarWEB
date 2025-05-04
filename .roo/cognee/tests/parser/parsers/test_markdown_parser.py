# .roo/cognee/tests/parser/parsers/test_markdown_parser.py
import pytest
import asyncio
import os
from pathlib import Path
from typing import List, TYPE_CHECKING

pytestmark = pytest.mark.asyncio

try:
    from src.parser.entities import TextChunk, Relationship, ParserOutput
    from src.parser.parsers.markdown_parser import MarkdownParser
except ImportError as e:
    pytest.skip(f"Skipping Markdown parser tests: Failed to import dependencies - {e}", allow_module_level=True)

if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser
    from pydantic import BaseModel

TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "markdown"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

@pytest.fixture(scope="module")
def parser() -> MarkdownParser:
    """Provides a MarkdownParser instance."""
    return MarkdownParser()

from ..conftest import run_parser_and_save_output

async def test_parse_empty_md_file(parser: MarkdownParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing an empty Markdown file."""
    empty_file = tmp_path / "empty.md"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0, "Empty .md file should yield no DataPoints"

async def test_parse_empty_mdx_file(parser: MarkdownParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing an empty MDX file."""
    empty_file = tmp_path / "empty.mdx"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0, "Empty .mdx file should yield no DataPoints"

async def test_parse_standard_markdown_document(parser: MarkdownParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing document.md from test_data."""
    test_file = TEST_DATA_DIR / "document.md"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0, "Expected DataPoints from document.md"

    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(chunks) > 0, "Expected TextChunk(s)"
    assert len(rels) == len(chunks), "Expected one CONTAINS_CHUNK per TextChunk"
    assert all(isinstance(dp, (TextChunk, Relationship)) for dp in results), "Only TextChunk/Relationship expected"
    assert all(r.type == "CONTAINS_CHUNK" for r in rels), "Expected only CONTAINS_CHUNK relationships"

    first_chunk = chunks[0]
    assert isinstance(first_chunk.id, str) and first_chunk.id.endswith(":0")
    assert "# Main Document Title" in first_chunk.chunk_content

    file_id = rels[0].source_id
    assert file_id.startswith("test_file_id_")
    assert all(r.source_id == file_id for r in rels)
    chunk_ids = {c.id for c in chunks}
    rel_target_ids = {r.target_id for r in rels}
    assert chunk_ids == rel_target_ids

    full_text = "".join(c.chunk_content for c in chunks)
    assert "# Main Document Title" in full_text
    assert "## Section 1: Setup" in full_text
    assert "```python" in full_text
    assert "## Section 2: Usage" in full_text
    assert "```bash" in full_text

async def test_parse_mdx_document(parser: MarkdownParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing component_doc.mdx (contains imports and JSX) from test_data."""
    test_file = TEST_DATA_DIR / "component_doc.mdx"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(chunks) > 0
    assert len(rels) == len(chunks)
    assert all(isinstance(dp, (TextChunk, Relationship)) for dp in results)
    assert all(r.type == "CONTAINS_CHUNK" for r in rels)

    first_chunk = chunks[0]
    assert 'import { MyComponent } from "./MyComponent";' in first_chunk.chunk_content
    assert '# Documentation for MyComponent' in first_chunk.chunk_content

    full_text = "".join(c.chunk_content for c in chunks)
    assert "```jsx" in full_text
    assert "<MyComponent data={sampleData}" in full_text
    assert "<MyComponent data={[5, 10, 15]}" in full_text


async def test_parse_markdown_with_frontmatter(parser: MarkdownParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing markdown with YAML frontmatter."""
    content = """---
title: Test Document
author: AI Assistant
tags: [test, markdown, frontmatter]
date: 2023-10-27
---

# Document Content

This content is below the frontmatter.

More text here.
"""
    test_file = tmp_path / "frontmatter.md"
    test_file.write_text(content, encoding="utf-8")
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(chunks) > 0
    assert len(rels) == len(chunks)
    assert all(isinstance(dp, (TextChunk, Relationship)) for dp in results)

    full_text = "".join(c.chunk_content for c in chunks)
    assert "---" in full_text
    assert "title: Test Document" in full_text
    assert "# Document Content" in full_text
