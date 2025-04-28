# src/parser/parsers/cpp_parser.py
from pydantic import BaseModel # Import BaseModel for type hinting
from typing import AsyncGenerator, Optional
from .base_parser import BaseParser
from pydantic import BaseModel # Import BaseModel for type hinting
from ..entities import TextChunk, CodeEntity, Dependency # Removed DataPoint import
from ..chunking import basic_chunker
from ..utils import read_file_content, get_node_text, logger, TSNODE_TYPE
from .treesitter_setup import get_parser, get_language

# Define Tree-sitter queries for C++
CPP_QUERIES = {
    "includes": """
        (preproc_include [(string_literal) (system_lib_string)] @include) @include_statement
        """,
    "functions": """
(function_definition declarator: (function_declarator declarator: (identifier) @name) ) @definition ;; Basic function def
        """,
      "classes": """
      (class_specifier name: [(type_identifier) (identifier)] @name) @definition
      """,
    "classes": """
    (class_specifier name: [(type_identifier) (identifier)] @name) @definition
        """,
    "structs": """
        (struct_specifier name: [(type_identifier) (identifier)] @name) @definition
        """,
    "namespaces": """
        (namespace_definition name: [(identifier) (nested_namespace_specifier)] @name) @definition
        """,
    "enums": """
        [(enum_specifier name: (type_identifier) @name) @definition
         (enum_specifier class name: (type_identifier) @name) @definition
        ]
        """,
    "typedefs": """
        (type_definition type: (_) declarator: (type_identifier) @name) @definition
        """,
    "using": """
        (using_declaration) @using_statement
        """
}

class CppParser(BaseParser):
    def __init__(self):
        super().__init__()
        self.language = get_language("cpp")
        self.parser = get_parser("cpp")
        self.queries = {}
        if self.language:
            try:
                self.queries = {
                    name: self.language.query(query_str)
                    for name, query_str in CPP_QUERIES.items()
                }
            except Exception as e:
                logger.error(f"Failed to compile C++ queries: {e}", exc_info=True)
                self.queries = {} # Ensure queries dict is empty on failure

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[BaseModel, None]: # Use BaseModel hint
        if not self.parser or not self.language or not self.queries:
            logger.error("C++ parser not available")
            return

        try:
            content = await read_file_content(file_path)
            if not content:
                return

            tree = self.parser.parse(bytes(content, "utf8"))
            root_node = tree.root_node

            # Yield chunks
            for i, chunk in enumerate(basic_chunker(content)):
                if chunk.strip():
                    yield TextChunk(
                        chunk_id_str=f"{file_id}:chunk:{i}",
                        parent_id=file_id,
                        text=chunk,
                        chunk_index=i
                    )

            # Yield entities and dependencies would follow here
            # (implementation omitted for brevity)

        except Exception as e:
            logger.error(f"Failed to parse C++ file {file_path}: {e}", exc_info=True)
