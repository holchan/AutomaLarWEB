# src/parser/parsers/typescript_parser.py
from pydantic import BaseModel # Import BaseModel for type hinting
from typing import AsyncGenerator, Optional
from .base_parser import BaseParser
from pydantic import BaseModel # Import BaseModel for type hinting
from ..entities import TextChunk, CodeEntity, Dependency # Removed DataPoint import
from ..chunking import basic_chunker
from ..utils import read_file_content, get_node_text, logger, TSNODE_TYPE
from .treesitter_setup import get_parser, get_language

# Define Tree-sitter queries for TypeScript/TSX
# Often similar to JS, but includes types and interfaces.
TYPESCRIPT_QUERIES = {
    "imports": """
        [
            (import_statement source: (string) @import_from) @import_statement ;; import ... from '...'
            (import_statement (import_clause (identifier) @default_import)) source: (string) @import_from @import_statement ;; import defaultExport from '...'
            (import_statement (import_clause (namespace_import (identifier) @namespace_import)) source: (string) @import_from) @import_statement ;; import * as name from '...'
            (import_statement (import_clause (named_imports (import_specifier name: [(identifier) (type_identifier)] @named_import))) source: (string) @import_from) @import_statement ;; import { name } from '...'
            (import_statement (import_clause (named_imports (import_specifier property: [(identifier) (type_identifier)] @property_import name: [(identifier) (type_identifier)] @named_import))) source: (string) @import_from) @import_statement ;; import { name as alias } from '...'
            ;; Basic require - less common in TS but possible
            (lexical_declaration
              (variable_declarator
                name: [(identifier) @require_target (object_pattern (shorthand_property_identifier_pattern) @require_target)]
                value: (call_expression function: (identifier) @_req arguments: (arguments (string) @import_from)))
              (#match? @_req "^require$")) @import_statement
        ]
        """,
    "functions": """
        [
            (function_declaration name: (identifier) @name parameters: (formal_parameters)? @params) @definition ;; function foo() {}
            (function_signature name: (identifier) @name parameters: (formal_parameters)? @params) @definition ;; declare function foo(); (often in .d.ts)
            (lexical_declaration
              (variable_declarator
                name: (identifier) @name
                value: [(arrow_function parameters: (formal_parameters)? @params) (function parameters: (formal_parameters)? @params)])) @definition ;; const foo = () => {}; const foo = function() {};
            (method_definition name: (property_identifier) @name parameters: (formal_parameters)? @params) @definition ;; class { foo() {} }
            (method_signature name: (property_identifier) @name parameters: (formal_parameters)? @params) @definition ;; interface { foo(): void; }
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
    """
    Parses TypeScript and TSX files (.ts, .tsx) using Tree-sitter to extract
    code entities and dependencies.

    This parser identifies functions, classes, interfaces, types, enums, and
    import statements within TypeScript/TSX source code. It also utilizes the
    `basic_chunker` to break down the file content into text segments.

    Inherits from BaseParser.
    """

    def __init__(self):
        """Initializes the TypescriptParser and loads the Tree-sitter language and queries."""
        super().__init__()
        self.language = get_language("typescript") # Note: Tree-sitter uses 'typescript' for both TS and TSX
        self.parser = get_parser("typescript")
        self.queries = {}
        if self.language:
            try:
                self.queries = {
                    name: self.language.query(query_str)
                    for name, query_str in TYPESCRIPT_QUERIES.items()
                }
            except Exception as e:
                 logger.error(f"Failed to compile TypeScript queries: {e}", exc_info=True)
        else:
            logger.error("TypeScript tree-sitter language not loaded. TS/TSX parsing will be limited.")

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[BaseModel, None]: # Use BaseModel hint
        """
        Parses a TypeScript or TSX file, yielding TextChunks, CodeEntities
        (functions, classes, interfaces, types, enums), and Dependencies (imports).

        Reads the file content, uses Tree-sitter to build an AST, and queries the
        AST to extract relevant code structures and dependencies. It also generates
        text chunks from the file content. Handles both standard TS and TSX syntax.

        Args:
            file_path: The absolute path to the TS/TSX file to be parsed.
            file_id: The unique ID of the SourceFile entity corresponding to this file.

        Yields:
            BaseModel objects: TextChunk, CodeEntity (FunctionDefinition, ClassDefinition,
            InterfaceDefinition, TypeDefinition, EnumDefinition), and Dependency entities
            extracted from the file.
        """
        if not self.parser or not self.language or not self.queries:
            logger.error(f"TypeScript parser not available or queries failed compilation, skipping parsing for {file_path}")
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
                            params_node: Optional[TSNODE_TYPE] = None
                            for child_capture in query.captures(node):
                                if child_capture[1] == "name":
                                    name_node = child_capture[0]
                                elif child_capture[1] == "params":
                                    params_node = child_capture[0]

                            if name_node:
                                name = get_node_text(name_node, content_bytes)
                                entity_text = get_node_text(node, content_bytes)
                                start_line = node.start_point[0] + 1
                                end_line = node.end_point[0] + 1
                                parameters = get_node_text(params_node, content_bytes) if params_node else ""

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
                        alias_node: Optional[TSNODE_TYPE] = None
                        default_import_node: Optional[TSNODE_TYPE] = None
                        namespace_import_node: Optional[TSNODE_TYPE] = None

                        for child_capture in import_query.captures(node):
                            if child_capture[1] == "import_from":
                                import_from_node = child_capture[0]
                            elif child_capture[1] == "named_import":
                                import_target_node = child_capture[0]
                            elif child_capture[1] == "default_import":
                                import_target_node = child_capture[0]
                            elif child_capture[1] == "namespace_import":
                                import_target_node = child_capture[0]
                            elif child_capture[1] == "alias":
                                alias_node = child_capture[0]

                        if import_from_node:
                            target = get_node_text(import_from_node, content_bytes)
                            if target and target.startswith(('"', "'")):
                                target = target[1:-1]
                        elif import_target_node:
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
