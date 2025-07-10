from typing import AsyncGenerator, List, Set, ClassVar
from .base_parser import BaseParser
from ..entities import ParserOutput
from ..utils import logger

GENERIC_CHUNK_SIZE = 1000
GENERIC_CHUNK_OVERLAP = 100

class GenericParser(BaseParser):
    """
    A generic parser for file types that don't have a specialized AST-based parser.
    It chunks content based on character count and yields slice_lines.
    """
    SUPPORTED_EXTENSIONS: ClassVar[List[str]] = [
        "generic_fallback",
        ".txt", ".md", ".json", ".yaml", ".yml", ".xml", ".html", ".css", ".sh"
    ]

    def __init__(self):
        super().__init__()
        self.log_prefix = "GenericParser"

    async def parse(self, source_file_id: str, file_content: str) -> AsyncGenerator[ParserOutput, None]:
        log_prefix = f"{self.log_prefix} ({source_file_id})"
        logger.debug(f"{log_prefix}: Starting generic parsing.")

        if not file_content.strip():
            logger.debug(f"{log_prefix}: Content is empty, yielding empty slice_lines.")
            yield []
            return

        slice_lines_set: Set[int] = {0}
        text_len = len(file_content)

        if text_len <= GENERIC_CHUNK_SIZE:
            yield [0]
            return

        start_char_idx = 0
        while start_char_idx < text_len:
            if start_char_idx > 0:
                line_number_0_indexed = file_content.count('\n', 0, start_char_idx)
                slice_lines_set.add(line_number_0_indexed)

            step = GENERIC_CHUNK_SIZE - GENERIC_CHUNK_OVERLAP
            if step <= 0:
                logger.error(f"{log_prefix}: Chunk step is non-positive ({step}). Aborting.")
                break
            start_char_idx += step

        final_slice_lines = sorted(list(slice_lines_set))
        logger.debug(f"{log_prefix}: Yielding calculated slice_lines: {final_slice_lines}")
        yield final_slice_lines
