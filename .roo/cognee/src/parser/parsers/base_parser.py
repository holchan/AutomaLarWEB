from abc import ABC, abstractmethod
from typing import AsyncGenerator
from pydantic import BaseModel
from ..utils import logger

class BaseParser(ABC):
    """
    Abstract base class for all file parsers.

    Defines the interface that language-specific parsers must implement.
    """

    def __init__(self):
        """Initializes the base parser."""
        self.parser_type = self.__class__.__name__
        logger.debug(f"Initialized parser: {self.parser_type}")

    @abstractmethod
    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[BaseModel, None]:
        """
        Parses the content of the given file path asynchronously.

        Args:
            file_path: The absolute path to the file to be parsed.
            file_id: The unique ID assigned to the SourceFile entity representing this file.

        Yields:
            Pydantic BaseModel objects (TextChunk, CodeEntity, Relationship)
            extracted from the file according to the defined entities.py.
        """

        raise NotImplementedError(f"{self.parser_type} must implement the 'parse' method.")
        yield
