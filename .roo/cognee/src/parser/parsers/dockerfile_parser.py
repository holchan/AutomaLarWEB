# src/parser/parsers/dockerfile_parser.py
from typing import AsyncGenerator
import re # For potential future instruction parsing
from .base_parser import BaseParser
from ..entities import DataPoint, TextChunk # Potentially DockerfileInstruction later
from ..chunking import basic_chunker
from ..utils import read_file_content, logger

# Optional: Regex to identify common Dockerfile instructions
# INSTRUCTION_REGEX = re.compile(r"^\s*([A-Z]+)\s+", re.IGNORECASE)

class DockerfileParser(BaseParser):
    """Parses Dockerfile files, yielding text chunks."""

    def __init__(self):
        super().__init__()
        # No specific setup needed for basic chunking

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[DataPoint, None]:
        """Parses a Dockerfile, yielding text chunks."""
        logger.debug(f"Parsing Dockerfile: {file_path}")
        content = await read_file_content(file_path)
        if content is None:
            logger.error(f"Could not read content from {file_path}")
            return

        try:
            # 1. Yield Chunks using the basic chunker
            chunks = basic_chunker(content)
            for i, chunk_text in enumerate(chunks):
                if not chunk_text.strip(): continue
                chunk_id_str = f"{file_id}:chunk:{i}"
                yield TextChunk(chunk_id_str=chunk_id_str, parent_id=file_id, text=chunk_text, chunk_index=i)

            # 2. Optional: Parse specific instructions
            # This section can be expanded later if needed.
            # lines = content.splitlines()
            # for line_num, line in enumerate(lines):
            #     stripped_line = line.strip()
            #     if stripped_line and not stripped_line.startswith('#'):
            #         match = INSTRUCTION_REGEX.match(stripped_line)
            #         if match:
            #             instruction = match.group(1).upper()
            #             arguments = stripped_line[match.end():].strip()
            #             # Could yield a DockerfileInstruction entity here:
            #             # instruction_id = f"{file_id}:instr:{instruction}:{line_num+1}"
            #             # yield DockerfileInstruction(id=instruction_id, file_id=file_id, ...)
            #             logger.debug(f"Dockerfile instruction '{instruction}' found at line {line_num+1}")

        except Exception as e:
            logger.error(f"Failed to parse Dockerfile {file_path}: {e}", exc_info=True)
