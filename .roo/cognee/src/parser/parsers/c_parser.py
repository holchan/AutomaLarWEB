# src/parser/parsers/c_parser.py
from typing import AsyncGenerator, Optional
from .base_parser import BaseParser
from ..entities import DataPoint, TextChunk, CodeEntity, Dependency
from ..chunking import basic_chunker
from ..utils import read_file_content, get_node_text, logger, TSNODE_TYPE
from .treesitter_setup import get_parser, get_language

# Define Tree-sitter queries for C
C_QUERIES = {
    "includes": """
        (preproc_include path: [(string_literal) (system_lib_string)] @include) @include_statement
        """,
    "functions": """
        (function_definition
            declarator: (function_declarator declarator: (identifier) @name)) @definition
        """,
    "structs": """
        (struct_specifier name: (type_identifier) @name) @definition
        """,
    "unions": """
        (union_specifier name: (type_identifier) @name) @definition
        """,
    "enums": """
        (enum_specifier name: (type_identifier) @name) @definition
        """,
    "typedefs": """
        (type_definition type: (_) declarator: (type_identifier) @name) @definition
        """,
    # Could add macros, global variables etc.
}

class CParser(BaseParser):
    """Parses C files using Tree-sitter."""

    def __init__(self):
        super().__init__()
        self.language = get_language("c")
        self.parser = get_parser("c")
        if self.language:
            self.queries = {
                name: self.language.query(query_str)
                for name, query_str in C_QUERIES.items()
            }
        else:
            self.queries = {}
            logger.error("C tree-sitter language not loaded. C parsing will be limited.")

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[DataPoint, None]:
        """Parses a C file, yielding chunks, functions, structs, enums, typedefs, and includes."""
        if not self.parser or not self.language:
            logger.error(f"C parser not available, skipping parsing for {file_path}")
            return

        content = await read_file_content(file_path)
        if content is None:
            logger.error(f"Could not read content from {file_path}")
            return

        try:
            content_bytes = bytes(content, "utf8")
            tree = self.parser.parse(content_bytes)
            root_node = tree.root_node

            # 1. Yield Chunks
            chunks = basic_chunker(content)
            for i, chunk_text in enumerate(chunks):
                if not chunk_text.strip(): continue
                chunk_id_str = f"{file_id}:chunk:{i}"
                yield TextChunk(chunk_id_str=chunk_id_str, parent_id=file_id, text=chunk_text, chunk_index=i)

            # 2. Yield Code Entities (Functions, Structs, Unions, Enums, Typedefs)
            entity_configs = [
                ("functions", "FunctionDefinition"),
                ("structs", "StructDefinition"),
                ("unions", "UnionDefinition"),
                ("enums", "EnumDefinition"),
                ("typedefs", "TypeDefinition"),
            ]

            for query_name, entity_class_name in entity_configs:
                if query_name in self.queries:
                    query = self.queries[query_name]
                    for capture in query.captures(root_node):
                        node_type = capture[1]
                        node = capture[0]

                        if node_type == "definition":
                            name_node: Optional[TSNODE_TYPE] = None
                            for child_capture in query.captures(node):
                                if child_capture[1] == "name":
                                    name_node = child_capture[0]
                                    break

                            if name_node:
                                name = get_node_text(name_node, content_bytes)
                                entity_text = get_node_text(node, content_bytes)
                                start_line = node.start_point[0] + 1
                                end_line = node.end_point[0] + 1

                                if name and entity_text:
                                    entity_id_str = f"{file_id}:{name}:{start_line}"
                                    yield CodeEntity(entity_id_str, entity_class_name, name, file_id, entity_text, start_line, end_line)
                                else:
                                     logger.warning(f"Could not extract name or text for C {entity_class_name} at {file_path}:{start_line}")

            # 3. Yield Dependencies (Includes)
            if "includes" in self.queries:
                include_query = self.queries["includes"]
                processed_includes = set()
                for capture in include_query.captures(root_node):
                    node_type = capture[1]
                    node = capture[0] # The preproc_include node

                    if node_type == "include_statement":
                        target_node: Optional[TSNODE_TYPE] = None
                        for child_capture in include_query.captures(node):
                             if child_capture[1] == "include":
                                 target_node = child_capture[0]
                                 break

                        if target_node:
                            target = get_node_text(target_node, content_bytes)
                            # Clean quotes or angle brackets
                            if target and target.startswith(('"', '<')):
                                target = target[1:-1]

                            snippet = get_node_text(node, content_bytes)
                            start_line = node.start_point[0] + 1
                            end_line = node.end_point[0] + 1

                            include_key = (target, start_line)
                            if target and snippet and include_key not in processed_includes:
                                dep_id_str = f"{file_id}:dep:{target}:{start_line}"
                                yield Dependency(dep_id_str, file_id, target, snippet, start_line, end_line)
                                processed_includes.add(include_key)
                            elif not target:
                                 logger.warning(f"Could not determine C include target at {file_path}:{start_line}")


        except Exception as e:
            logger.error(f"Failed to parse C file {file_path}: {e}", exc_info=True)
