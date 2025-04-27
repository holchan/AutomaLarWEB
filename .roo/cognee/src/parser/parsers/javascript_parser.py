# src/parser/parsers/javascript_parser.py
from typing import AsyncGenerator, Optional
from .base_parser import BaseParser
from ..entities import DataPoint, TextChunk, CodeEntity, Dependency
from ..chunking import basic_chunker
from ..utils import read_file_content, get_node_text, logger, TSNODE_TYPE
from .treesitter_setup import get_parser, get_language

# Define Tree-sitter queries for JavaScript/JSX
# Note: These might need refinement, especially for complex frameworks or syntax variations.
# Capturing various function/class/import patterns.
JAVASCRIPT_QUERIES = {
    "imports": """
        [
            (import_statement source: (string) @import_from) @import_statement ;; import ... from '...'
            (import_statement (import_clause (identifier) @default_import)) source: (string) @import_from @import_statement ;; import defaultExport from '...'
            (import_statement (import_clause (namespace_import (identifier) @namespace_import)) source: (string) @import_from) @import_statement ;; import * as name from '...'
            (import_statement (import_clause (named_imports (import_specifier name: (identifier) @named_import))) source: (string) @import_from) @import_statement ;; import { name } from '...'
            (import_statement (import_clause (named_imports (import_specifier property: (identifier) @property_import name: (identifier) @named_import))) source: (string) @import_from) @import_statement ;; import { name as alias } from '...'

            (lexical_declaration
              (variable_declarator
                name: (_) @variable_name ;; Capture the variable name (identifier or pattern)
                value: (call_expression
                         function: (identifier) @require_function ;; Capture the 'require' identifier
                         arguments: (arguments (string) @import_from)))) @import_statement ;; Basic require('...') pattern
            (#match? @require_function "^require$") ;; Apply predicate to the function identifier

            (call_expression
              # function: (identifier) @_dynamic_import (#match? @_dynamic_import "^import$")) # Temporarily remove predicate
              function: (identifier) @_dynamic_import
              arguments: (arguments (string) @import_from)) @import_statement ;; dynamic import("module")
        ]
        """,
    "functions": """
        [
            (function_declaration name: (identifier) @name parameters: (formal_parameters)? @params) @definition ;; function foo() {}
            (lexical_declaration
              (variable_declarator
                name: (identifier) @name
                value: [(arrow_function parameters: (formal_parameters)? @params) (function parameters: (formal_parameters)? @params)])) @definition ;; const foo = () => {}; const foo = function() {};
            (expression_statement (assignment_expression left: [(identifier) (member_expression)] @name right: [(arrow_function parameters: (formal_parameters)? @params) (function parameters: (formal_parameters)? @params)])) @definition ;; foo = () => {}; module.exports = function() {};
            (method_definition name: (property_identifier) @name parameters: (formal_parameters)? @params) @definition ;; class { foo() {} }
            (pair key: (property_identifier) @name value: [(arrow_function parameters: (formal_parameters)? @params) (function parameters: (formal_parameters)? @params)]) @definition ;; const obj = { foo: () => {} };
        ]
        """,
    "classes": """
        (class_declaration name: (identifier) @name) @definition ;; class Foo {}
        (lexical_declaration (variable_declarator name: (identifier) @name value: (class))) @definition ;; const Foo = class {}
        """,
    # Could add queries for exports, variables, JSX components etc.
}


class JavascriptParser(BaseParser):
    """
    Parses JavaScript and JSX files (.js, .jsx, .ts, .tsx - though .ts/.tsx have dedicated parsers)
    using Tree-sitter to extract code entities and dependencies.

    This parser identifies functions, classes, and various import/require
    statements within JavaScript and JSX source code. It also utilizes the
    `basic_chunker` to break down the file content into text segments.
    Handles both standard JS and basic JSX syntax.

    Inherits from BaseParser.
    """

    def __init__(self):
        """Initializes the JavascriptParser and loads the Tree-sitter language and queries."""
        super().__init__()
        self.language = get_language("javascript") # Note: Tree-sitter uses 'javascript' for both JS and JSX
        self.parser = get_parser("javascript")
        self.queries = {}
        if self.language:
            try:
                self.queries = {
                    name: self.language.query(query_str)
                    for name, query_str in JAVASCRIPT_QUERIES.items()
                }
            except Exception as e:
                 logger.error(f"Failed to compile JavaScript queries: {e}", exc_info=True)
        else:
            logger.error("JavaScript tree-sitter language not loaded. JS/JSX parsing will be limited.")

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[DataPoint, None]:
        """
        Parses a JavaScript or JSX file, yielding TextChunks, CodeEntities
        (functions, classes), and Dependencies (imports, requires).

        Reads the file content, uses Tree-sitter to build an AST, and queries the
        AST to extract relevant code structures and dependencies. It also generates
        text chunks from the file content. Handles both standard JS and basic JSX syntax.

        Args:
            file_path: The absolute path to the JS/JSX file to be parsed.
            file_id: The unique ID of the SourceFile entity corresponding to this file.

        Yields:
            DataPoint objects: TextChunk, CodeEntity (FunctionDefinition, ClassDefinition),
            and Dependency entities extracted from the file.
        """
        if not self.parser or not self.language or not self.queries:
            logger.error(f"JavaScript parser not available or queries failed compilation, skipping parsing for {file_path}")
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
                # TODO: Add line number mapping for chunks if possible
                yield TextChunk(chunk_id_str=chunk_id_str, parent_id=file_id, text=chunk_text, chunk_index=i)

            # 2. Yield Code Entities (Functions, Classes)
            for entity_type, query_name, entity_class_name in [
                ("functions", "functions", "FunctionDefinition"),
                ("classes", "classes", "ClassDefinition"),
            ]:
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
                                # For assignments, the 'name' might be complex (e.g., member_expression)
                                # We might want the full name or just the final identifier
                                if name and name_node.type != 'identifier':
                                     name = name.split('.')[-1] # Heuristic: take last part

                                entity_text = get_node_text(node, content_bytes)
                                start_line = node.start_point[0] + 1
                                end_line = node.end_point[0] + 1
                                parameters = get_node_text(params_node, content_bytes) if params_node else ""

                                if name and entity_text:
                                    entity_id_str = f"{file_id}:{name}:{start_line}"
                                    yield CodeEntity(entity_id_str, entity_class_name, name, file_id, entity_text, start_line, end_line)
                                else:
                                     logger.warning(f"Could not extract name or text for JS {entity_type} at {file_path}:{start_line}")

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
                        dynamic_import_node: Optional[TSNODE_TYPE] = None

                        # Find specific captures within the statement
                        for child_capture in import_query.captures(node):
                            if child_capture[1] == "import_from":
                                import_from_node = child_capture[0]
                            elif child_capture[1] in ["default_import", "namespace_import", "named_import", "require_target"]:
                                import_target_node = child_capture[0]
                            elif child_capture[1] == "import_from" and node.type == "call_expression":
                                 dynamic_import_node = child_capture[0] # Dynamic import

                        if dynamic_import_node:
                            target = get_node_text(dynamic_import_node, content_bytes)
                            if target and target.startswith(('"', "'")):
                                target = target[1:-1]
                        elif import_from_node:
                            target = get_node_text(import_from_node, content_bytes)
                            # Clean quotes from string literal if necessary
                            if target and target.startswith(('"', "'")):
                                target = target[1:-1]
                        elif import_target_node:  # Case like require('module') where target is captured directly
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
                             logger.warning(f"Could not determine JS import target at {file_path}:{start_line}")


        except Exception as e:
            logger.error(f"Failed to parse JavaScript file {file_path}: {e}", exc_info=True)
