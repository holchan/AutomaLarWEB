from pydantic import BaseModel
from typing import AsyncGenerator, List
import os

from .base_parser import BaseParser
from ..entities import TextChunk, CodeEntity, Relationship, ParserOutput
from ..chunking import basic_chunker
from ..utils import read_file_content, logger

class CssParser(BaseParser):
    """
    Parses CSS files (.css), yielding TextChunk nodes and CONTAINS_CHUNK relationships.
    Does not perform detailed AST parsing.
    """

    def __init__(self):
        """Initializes the CssParser."""
        super().__init__()

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[ParserOutput, None]:
        """Parses a CSS file into TextChunks."""
        logger.debug(f"Parsing CSS file: {file_path}")
        content = await read_file_content(file_path)
        if content is None:
            logger.error(f"Could not read content from {file_path}")
            return

        try:
            chunks_data = basic_chunker(content)
            current_line = 1
            chunk_count = 0
            for i, chunk_text in enumerate(chunks_data):
                if not chunk_text.strip():
                    num_newlines = chunk_text.count('\n')
                    current_line += num_newlines
                    continue

                chunk_start_line = current_line
                num_newlines = chunk_text.count('\n')
                chunk_end_line = chunk_start_line + num_newlines

                chunk_id = f"{file_id}:{i}"
                chunk_node = TextChunk(
                    id=chunk_id,
                    start_line=chunk_start_line,
                    end_line=chunk_end_line,
                    chunk_content=chunk_text
                )
                yield chunk_node
                chunk_count += 1

                yield Relationship(source_id=file_id, target_id=chunk_id, type="CONTAINS_CHUNK")

                current_line = chunk_end_line + 1

            logger.debug(f"[{file_path}] Yielded {chunk_count} TextChunk nodes.")

        except Exception as e:
            logger.error(f"Failed to parse CSS file {file_path}: {e}", exc_info=True)
