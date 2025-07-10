from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, ClassVar
from ..entities import ParserOutput
from ..utils import logger

class BaseParser(ABC):
    """
    Defines the interface that all language-specific and generic
    parsers must implement.
    """
    SUPPORTED_EXTENSIONS: ClassVar[List[str]] = []

    def __init__(self):
        self.parser_type = self.__class__.__name__
        logger.debug(f"Initialized parser: {self.parser_type}")

    @abstractmethod
    async def parse(self, source_file_id: str, file_content: str) -> AsyncGenerator[ParserOutput, None]:
        """
        Parses the content of a file and yields factual data.

        Args:
            source_file_id: A unique identifier for the file being parsed.
            file_content: The full string content of the file.

        Yields:
            A stream of ParserOutput union types:
            1. A single List[int] containing the line numbers for slicing.
            2. Zero or more CodeEntity objects for each definition found.
            3. Zero or more RawSymbolReference objects for each reference found.
        """
        raise NotImplementedError(f"{self.parser_type} must implement the 'parse' method.")
        if False:
            yield
