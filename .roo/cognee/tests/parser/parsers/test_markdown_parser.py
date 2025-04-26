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
    from src.parser.parsers.markdown_parser import MarkdownParser
    # Expecting only TextChunk for now
    from src.parser.entities import DataPoint, TextChunk
except ImportError as e:
    pytest.skip(f"Skipping Markdown parser tests: Failed to import dependencies - {e}", allow_module_level=True)

# Avoid runtime import errors if BaseParser isn't directly used
if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser

# --- Test Configuration ---
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "markdown"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

# Helper function `run_parser_and_save_output` is now expected to be in conftest.py
# --- Parser Fixture ---
@pytest.fixture(scope="module")
def parser() -> MarkdownParser:
    """Provides a MarkdownParser instance."""
    # No specific tree-sitter language needed, but check mistune presence if needed later
    return MarkdownParser()

# --- Test Cases ---

async def test_parse_empty_md_file(parser: MarkdownParser, tmp_path: Path):
    """Test parsing an empty Markdown file."""
    empty_file = tmp_path / "empty.md"
    empty_file.touch()
    results = await run_parser_and_save_output(parser, empty_file, tmp_path)
    assert len(results) == 0, "Empty .md file should yield no DataPoints"

async def test_parse_empty_mdx_file(parser: MarkdownParser, tmp_path: Path):
    """Test parsing an empty MDX file."""
    empty_file = tmp_path / "empty.mdx"
    empty_file.touch()
    results = await run_parser_and_save_output(parser, empty_file, tmp_path)
    assert len(results) == 0, "Empty .mdx file should yield no DataPoints"

async def test_parse_standard_markdown_document(parser: MarkdownParser, tmp_path: Path):
    """Test parsing document.md from test_data."""
    test_file = TEST_DATA_DIR / "document.md"
    results = await run_parser_and_save_output(parser, test_file, tmp_path)

    # Expect only TextChunk results from basic chunker
    assert len(results) > 0, "Expected DataPoints from document.md"
    payloads = [dp.model_dump(mode='json') for dp in results]
    assert all(p.get("type") == "TextChunk" for p in payloads), "Only TextChunks expected"

    # Check basic content integrity
    first_chunk = payloads[0]
    first_chunk_meta = first_chunk.get("metadata", {})
    assert first_chunk_meta.get("chunk_index") == 0, "First chunk index mismatch"
    assert "# Main Document Title" in first_chunk.get("text_content",""), "Title missing in first chunk"
    assert first_chunk_meta.get("chunk_of", "").startswith("test_file_id_"), "Chunk parent ID missing or invalid"

    # Reconstruct text roughly and check presence of key elements
    full_text = "".join(p.get("text_content","") for p in payloads) # Use text_content
    original_content = test_file.read_text(encoding="utf-8")

    # Verify key markdown elements are present in the combined chunk text
    assert "# Main Document Title" in full_text, "Missing H1 Title"
    assert "## Section 1: Setup" in full_text, "Missing H2 Setup"
    assert "```python" in full_text, "Missing Python code block start"
    assert "def check_path(p):" in full_text, "Missing Python code content"
    assert "```" in full_text.split("```python")[1], "Missing code block end" # Rough check
    assert "## Section 2: Usage" in full_text, "Missing H2 Usage"
    assert "```bash" in full_text, "Missing Bash code block start"
    assert "python main_script.py" in full_text, "Missing Bash code content"
    assert "### Subsection 2.1: Advanced Options" in full_text, "Missing H3 Subsection"

async def test_parse_mdx_document(parser: MarkdownParser, tmp_path: Path):
    """Test parsing component_doc.mdx (contains imports and JSX) from test_data."""
    test_file = TEST_DATA_DIR / "component_doc.mdx"
    results = await run_parser_and_save_output(parser, test_file, tmp_path)

    # Expect only TextChunk results, no special handling of imports/JSX yet
    assert len(results) > 0, "Expected DataPoints from component_doc.mdx"
    payloads = [dp.model_dump(mode='json') for dp in results]
    assert all(p.get("type") == "TextChunk" for p in payloads), "Only TextChunks expected for MDX"

    # Check basic content integrity including imports/JSX as text
    first_chunk = payloads[0]
    first_chunk_meta = first_chunk.get("metadata", {})
    assert first_chunk_meta.get("chunk_index") == 0
    assert 'import { MyComponent } from "./MyComponent";' in first_chunk.get("text_content",""), "Import statement missing"
    assert 'import { Chart } from "react-chartjs-2";' in first_chunk.get("text_content",""), "Import statement missing"
    assert '# Documentation for MyComponent' in first_chunk.get("text_content",""), "Title missing"

    # Reconstruct text and check for JSX elements included as text
    full_text = "".join(p.get("text_content","") for p in payloads) # Use text_content
    assert "```jsx" in full_text, "JSX code block marker missing"
    assert "<MyComponent data={sampleData}" in full_text, "JSX example missing"
    assert "<MyComponent data={[5, 10, 15]}" in full_text, "Live demo JSX missing"
    assert "label=\"Live Demo Data\" />" in full_text, "JSX attribute missing"

async def test_parse_markdown_with_frontmatter(parser: MarkdownParser, tmp_path: Path):
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
    results = await run_parser_and_save_output(parser, test_file, tmp_path)

    # Expect only TextChunks, frontmatter should be included in the text
    assert len(results) > 0, "Expected DataPoints from frontmatter file"
    payloads = [dp.model_dump(mode='json') for dp in results]
    assert all(p.get("type") == "TextChunk" for p in payloads), "Only TextChunks expected with frontmatter"

    # Check that frontmatter and content are part of the chunked text
    full_text = "".join(p.get("text_content","") for p in payloads) # Use text_content
    assert "---" in full_text, "Frontmatter delimiter missing"
    assert "title: Test Document" in full_text, "Frontmatter title missing"
    assert "tags: [test, markdown, frontmatter]" in full_text, "Frontmatter tags missing"
    assert "date: 2023-10-27" in full_text, "Frontmatter date missing"
    assert "# Document Content" in full_text, "Content after frontmatter missing"
    assert "More text here." in full_text, "Later content missing"
