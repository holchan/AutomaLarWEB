# src/parser/parsers/css_parser.py
from typing import AsyncGenerator
from .base_parser import BaseParser
from ..entities import DataPoint, TextChunk
from ..chunking import basic_chunker
from ..utils import read_file_content, logger

# Note: While tree-sitter grammars exist for CSS, full parsing
# (selectors, rules, properties) is complex. For now, we focus on chunking.

class CssParser(BaseParser):
    """
    Parses CSS files (.css) and yields TextChunk entities.

    This parser currently uses the `basic_chunker` to break down CSS
    content into manageable text segments. While Tree-sitter grammars
    exist for CSS, full parsing of selectors, rules, and properties is
    complex and not implemented in this basic version.

    Inherits from BaseParser.
    """

    def __init__(self):
        """Initializes the CssParser."""
        super().__init__()
        # No specific setup needed for basic chunking

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[DataPoint, None]:
        """
        Parses a CSS file, yielding TextChunk entities.

        Reads the file content, chunks it using `basic_chunker`, and yields
        a `TextChunk` DataPoint for each non-empty chunk.

        Args:
            file_path: The absolute path to the CSS file to be parsed.
            file_id: The unique ID of the SourceFile entity corresponding to this file.

        Yields:
            TextChunk objects representing segments of the CSS content.
            May yield other DataPoint types in the future if advanced parsing is enabled.
        """
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
