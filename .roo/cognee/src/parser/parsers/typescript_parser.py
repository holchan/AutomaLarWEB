# src/parser/parsers/typescript_parser.py
from typing import AsyncGenerator, Optional
from .base_parser import BaseParser
from ..entities import DataPoint, TextChunk, CodeEntity, Dependency
from ..chunking import basic_chunker
from ..utils import read_file_content, get_node_text, logger, TSNODE_TYPE
from .treesitter_setup import get_parser, get_language

# Define Tree-sitter queries for TypeScript/TSX
# Often similar to JS, but includes types and interfaces.
TYPESCRIPT_QUERIES = {
    "imports": """
        [
            (import_statement source: (string) @import_from) @import_statement ;; import ... from '...'
            (import_statement (import_clause (identifier) @import) source: (string) @import_from) @import_statement ;; import defaultExport from '...'
            (import_statement (import_clause (namespace_import (identifier) @import)) source: (string) @import_from) @import_statement ;; import * as name from '...'
            (import_statement (import_clause (named_imports (import_specifier name: [(identifier) (type_identifier)] @import))) source: (string) @import_from) @import_statement ;; import { name } from '...'
            (import_statement (import_clause (named_imports (import_specifier property: [(identifier) (type_identifier)] @import name: [(identifier) (type_identifier)]))) source: (string) @import_from) @import_statement ;; import { name as alias } from '...'
            ;; Basic require - less common in TS but possible
            (lexical_declaration
              (variable_declarator
                name: [(identifier) @import (object_pattern (shorthand_property_identifier_pattern) @import)]
                value: (call_expression function: (identifier) @_req arguments: (arguments (string) @import_from)))
              (#match? @_req "^require$")) @import_statement
        ]
        """,
    "functions": """
        [
            (function_declaration name: (identifier) @name) @definition ;; function foo() {}
            (function_signature name: (identifier) @name) @definition ;; declare function foo(); (often in .d.ts)
            (lexical_declaration
              (variable_declarator
                name: (identifier) @name
                value: [(arrow_function) (function)])) @definition ;; const foo = () => {}; const foo = function() {};
            (method_definition name: (property_identifier) @name) @definition ;; class { foo() {} }
            (method_signature name: (property_identifier) @name) @definition ;; interface { foo(): void; }
        ]
        """,
    "classes": """
        (class_declaration name: [(identifier) (type_identifier)] @name) @definition ;; class Foo {}
        """,
    "interfaces": """
        (interface_declaration name: (type_identifier) @name) @definition ;; interface IFoo {}
        """,
    "types": """
        (type_alias_declaration name: (type_identifier) @name) @definition ;; type MyType = ...;
        """,
    "enums": """
        (enum_declaration name: (identifier) @name) @definition ;; enum MyEnum { ... }
        """,
    # Could add queries for exports, modules, namespaces etc.
}


class TypescriptParser(BaseParser):
    """Parses TypeScript and TSX files using Tree-sitter."""

    def __init__(self):
        super().__init__()
        self.language = get_language("typescript")
        self.parser = get_parser("typescript")
        if self.language:
            self.queries = {
                name: self.language.query(query_str)
                for name, query_str in TYPESCRIPT_QUERIES.items()
            }
        else:
            self.queries = {}
            logger.error("TypeScript tree-sitter language not loaded. TS/TSX parsing will be limited.")

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[DataPoint, None]:
        """Parses a TS/TSX file, yielding chunks, functions, classes, interfaces, types, enums, and imports."""
        if not self.parser or not self.language:
            logger.error(f"TypeScript parser not available, skipping parsing for {file_path}")
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

            # 2. Yield Code Entities (Functions, Classes, Interfaces, Types, Enums)
            entity_configs = [
                ("functions", "FunctionDefinition"),
                ("classes", "ClassDefinition"),
                ("interfaces", "InterfaceDefinition"),
                ("types", "TypeDefinition"),
                ("enums", "EnumDefinition"),
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
                                     logger.warning(f"Could not extract name or text for TS {entity_class_name} at {file_path}:{start_line}")

            # 3. Yield Dependencies (Imports/Requires)
            if "imports" in self.queries:
                import_query = self.queries["imports"]
                processed_imports = set()
                for capture in import_query.captures(root_node):
                    node_type = capture[1]
                    node = capture[0]

                    if node_type == "import_statement":
                        target = "unknown_import"
                        import_target_node = None
                        import_from_node = None

                        for child_capture in import_query.captures(node):
                            if child_capture[1] == "import":
                                import_target_node = child_capture[0]
                            elif child_capture[1] == "import_from":
                                import_from_node = child_capture[0]

                        if import_from_node:
                            target = get_node_text(import_from_node, content_bytes)
                            if target and target.startswith(('"', "'")):
                                target = target[1:-1]
                        elif import_target_node: # Handle require('...') case
                             target = get_node_text(import_target_node, content_bytes)
                             if target and target.startswith(('"', "'")):
                                 target = target[1:-1]

                        snippet = get_node_text(node, content_bytes)
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1

                        import_key = (target, start_line)
                        if target and snippet and import_key not in processed_imports:
                            dep_id_str = f"{file_id}:dep:{target}:{start_line}"
                            yield Dependency(dep_id_str, file_id, target, snippet, start_line, end_line)
                            processed_imports.add(import_key)
                        elif not target:
                             logger.warning(f"Could not determine TS import target at {file_path}:{start_line}")


        except Exception as e:
            logger.error(f"Failed to parse TypeScript file {file_path}: {e}", exc_info=True)
