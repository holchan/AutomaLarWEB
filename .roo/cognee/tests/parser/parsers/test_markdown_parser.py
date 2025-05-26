import pytest
import asyncio
from pathlib import Path
from typing import List, Union, TYPE_CHECKING

from pydantic import BaseModel

pytestmark = pytest.mark.asyncio

try:
    from src.parser.entities import TextChunk, Relationship
    ParserOutput = Union[TextChunk, Relationship]
    from src.parser.parsers.markdown_parser import MarkdownParser
except ImportError as e:
    pytest.skip(f"Skipping Markdown parser tests: Failed to import dependencies - {e}", allow_module_level=True)

if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser

TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "markdown"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

@pytest.fixture(scope="module")
def parser() -> MarkdownParser:
    return MarkdownParser()

from ..conftest import run_parser_and_save_output

async def test_parse_empty_md_file(parser: MarkdownParser, tmp_path: Path, run_parser_and_save_output):
    empty_file = tmp_path / "empty.md"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0

async def test_parse_empty_mdx_file(parser: MarkdownParser, tmp_path: Path, run_parser_and_save_output):
    empty_file = tmp_path / "empty.mdx"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0

async def test_parse_standard_markdown_document(parser: MarkdownParser, tmp_path: Path, run_parser_and_save_output):
    test_file = TEST_DATA_DIR / "document.md"
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
    assert "# Main Document Title" in first_chunk.chunk_content
    assert isinstance(first_chunk.start_line, int)
    assert isinstance(first_chunk.end_line, int)


    file_id_from_rel = rels[0].source_id
    assert file_id_from_rel.startswith("test_parser_file_id_")
    assert all(r.source_id == file_id_from_rel for r in rels)
    chunk_ids_set = {c.id for c in chunks}
    rel_target_ids_set = {r.target_id for r in rels}
    assert chunk_ids_set == rel_target_ids_set

    full_text = "".join(c.chunk_content for c in chunks)
    assert "## Section 1: Setup" in full_text
    assert "```python" in full_text

async def test_parse_mdx_document(parser: MarkdownParser, tmp_path: Path, run_parser_and_save_output):
    test_file = TEST_DATA_DIR / "component_doc.mdx"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(chunks) > 0
    assert len(rels) == len(chunks)

    first_chunk = chunks[0]
    assert 'import { MyComponent } from "./MyComponent";' in first_chunk.chunk_content
    assert '# Documentation for MyComponent' in first_chunk.chunk_content

    full_text = "".join(c.chunk_content for c in chunks)
    assert "```jsx" in full_text
    assert "<MyComponent data={sampleData}" in full_text

async def test_parse_markdown_with_frontmatter(parser: MarkdownParser, tmp_path: Path, run_parser_and_save_output):
    content = """---
title: Test Document
author: AI Assistant
---

# Document Content
This content is below the frontmatter.
"""
    test_file = tmp_path / "frontmatter.md"
    test_file.write_text(content, encoding="utf-8")
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0
    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    assert len(chunks) > 0

    full_text = "".join(c.chunk_content for c in chunks)
    assert "title: Test Document" in full_text
    assert "# Document Content" in full_text
