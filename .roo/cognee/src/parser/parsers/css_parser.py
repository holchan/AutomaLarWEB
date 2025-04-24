# src/parser/parsers/css_parser.py
from typing import AsyncGenerator
from .base_parser import BaseParser
from ..entities import DataPoint, TextChunk
from ..chunking import basic_chunker
from ..utils import read_file_content, logger

# Note: While tree-sitter grammars exist for CSS, full parsing
# (selectors, rules, properties) is complex. For now, we focus on chunking.

class CssParser(BaseParser):
    """Parses CSS files, yielding text chunks."""

    def __init__(self):
        super().__init__()
        # No specific setup needed for basic chunking

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[DataPoint, None]:
        """Parses a CSS file, yielding text chunks."""
        logger.debug(f"Parsing CSS file: {file_path}")
        content = await read_file_content(file_path)
        if content is None:
            logger.error(f"Could not read content from {file_path}")
            return

        try:
            # Yield Chunks using the basic chunker
            chunks = basic_chunker(content)
            for i, chunk_text in enumerate(chunks):
                if not chunk_text.strip(): continue
                chunk_id_str = f"{file_id}:chunk:{i}"
                yield TextChunk(chunk_id_str=chunk_id_str, parent_id=file_id, text=chunk_text, chunk_index=i)

            # Optional: Could add regex parsing for comments or @import rules later if needed.

        except Exception as e:
            logger.error(f"Failed to parse CSS file {file_path}: {e}", exc_info=True)
