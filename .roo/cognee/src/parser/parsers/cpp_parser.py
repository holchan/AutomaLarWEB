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
(function_definition declarator: (function_declarator . (identifier) @name) ) @definition ;; More general name capture
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
            logger.info("Attempting to compile C++ queries one by one...") # Changed log
            # --- MODIFIED: Compile one by one for better error reporting ---
            failed_queries = []
            for name, query_str in CPP_QUERIES.items():
                print(f"DEBUG: Compiling C++ query: {name}") # FORCE PRINT
                try:
                    self.queries[name] = self.language.query(query_str)
                    logger.debug(f"Successfully compiled C++ query: {name}")
                    print(f"DEBUG: Successfully compiled C++ query: {name}") # FORCE PRINT
                except Exception as e:
                    logger.error(f"Failed to compile C++ query '{name}': {e}", exc_info=True)
                    print(f"DEBUG: FAILED to compile C++ query '{name}': {e}") # FORCE PRINT
                    failed_queries.append(name)

            if not failed_queries:
                logger.info("Successfully compiled ALL C++ queries.")
            else:
                logger.error(f"Failed to compile the following C++ queries: {', '.join(failed_queries)}. C++ parsing will be limited.")
                self.queries = {} # Clear queries if ANY failed to ensure parse() skips detail
            # --- END MODIFICATION ---
        else:
            logger.error("C++ tree-sitter language not loaded. C++ parsing will be limited.")

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
