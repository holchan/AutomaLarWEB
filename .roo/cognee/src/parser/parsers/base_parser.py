from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, ClassVar
from ..entities import ParserOutput
from ..utils import logger

class BaseParser(ABC):
    """
    Defines the interface that language-specific and generic parsers must implement.
    """
    SUPPORTED_EXTENSIONS: ClassVar[List[str]] = []

    def __init__(self):
        self.parser_type = self.__class__.__name__
        logger.debug(f"Initialized parser: {self.parser_type}")

    @abstractmethod
    async def parse(self, source_file_id: str, file_content: str) -> AsyncGenerator[ParserOutput, None]:
        """
        Parses the content of a file.

        Args:
            source_file_id: The final, version-aware ID for the SourceFile node.
            file_content: The full string content of the file to be parsed.

        Yields:
            A stream of ParserOutput union types, starting with a single List[int]
            for slice_lines, followed by any CodeEntity, Relationship, or
            CallSiteReference objects discovered.
        """
        raise NotImplementedError(f"{self.parser_type} must implement the 'parse' method.")
        yield
