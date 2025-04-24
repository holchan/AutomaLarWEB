# src/parser/parsers/base_parser.py
from abc import ABC, abstractmethod
from typing import AsyncGenerator
from ..entities import DataPoint
from ..utils import logger # Import shared logger

class BaseParser(ABC):
    """
    Abstract base class for all file parsers.

    Each specific parser (e.g., PythonParser, MarkdownParser) should inherit
    from this class and implement the `parse` method.
    """

    def __init__(self):
        """Initializes the base parser."""
        # Common initialization for all parsers can go here if needed
        self.parser_type = self.__class__.__name__ # e.g., "PythonParser"
        logger.debug(f"Initialized parser: {self.parser_type}")

    @abstractmethod
    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[DataPoint, None]:
        """
        Parses the content of the given file path asynchronously and yields
        DataPoint objects representing extracted information (e.g., TextChunks,
        CodeEntity, Dependency).

        Args:
            file_path: The absolute path to the file to be parsed.
            file_id: The unique ID assigned to the SourceFile DataPoint representing this file.

        Yields:
            DataPoint objects extracted from the file.
        """
        # This is an abstract method, the implementation must be provided by subclasses.
        # The 'yield' keyword here ensures Python recognizes this as an async generator method signature.
        raise NotImplementedError(f"{self.parser_type} must implement the 'parse' method.")
        yield # pragma: no cover
