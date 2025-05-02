import re
from typing import AsyncGenerator, Optional
from pydantic import BaseModel
from tree_sitter import Node as TSNODE_TYPE

from cognee.infrastructure.files.utils.async_read_file import read_file_content
from cognee.modules.code.models.code_chunk import TextChunk
from cognee.modules.code.models.code_dependency import Dependency
from cognee.modules.code.models.code_entity import CodeEntity
from cognee.modules.code.parsers.languages import get_language, get_parser
from cognee.modules.code.parsers.utils.chunking import basic_chunker
from cognee.modules.code.parsers.utils.extraction import get_node_text
from .base_parser import BaseParser
from cognee.root_dir import get_absolute_path
from cognee.config import Config
config = Config()
config.load()

import logging
logger = logging.getLogger(__name__)

JAVASCRIPT_QUERIES = {
  "imports": """
    [
    ;; import ... from '...' statements
      (import_statement
        source: (string) @import_from
        ;; Optional captures for specific import types if needed later
        ;; (import_clause (identifier) @default_import)?
        ;; (import_clause (namespace_import (identifier) @namespace_import))?
        ;; (import_clause (named_imports (import_specifier name: (identifier) @named_import)))?
      ) @import_statement

    ;; require('...') assignment
      (lexical_declaration
        (variable_declarator
          name: [(identifier) (object_pattern)] @require_target ;; Allow identifier or destructuring
          value: (call_expression
            function: (identifier) @_req
            arguments: (arguments (string) @import_from)
          )
        )
        (#match? @_req "^require$") ;; Match the function name
      ) @require_statement ;; Capture the whole declaration

    ;; import('module') dynamic import
      (call_expression
        function: (import) ;; Specific 'import' keyword node used as function
        arguments: (arguments (string) @import_from)
      ) @import_statement ;; Treat as import statement for simplicity
    ]
        """,
     "functions": """
        [
            (function_declaration name: (identifier) @name) @definition ;; function foo() {}
            (function_expression name: (identifier)? @name) @definition ;; const bar = function foo() {}; (function foo() {})
            (arrow_function) @definition ;; const baz = () => {}; Often name is captured by variable_declarator
            (method_definition name: (property_identifier) @name) @definition ;; class { foo() {} }
            (pair key: (property_identifier) @name value: [(function_expression) (arrow_function)]) @definition ;; obj = { foo: function() {} }
            ;; Capture functions assigned to variables/properties
            (variable_declarator name: (identifier) @name value: [(function_expression) (arrow_function)]) @variable_assignment ;; Treat assignment as definition context
            (assignment_expression left: [(identifier)(member_expression)] @name right: [(function_expression)(arrow_function)]) @expression_assignment ;; Treat assignment as definition context
        ]
        """,
    "functions_alt": """
        [
            (function_declaration name: (identifier) @name) @definition
            (lexical_declaration (variable_declarator name: (identifier) @name value: (arrow_function))) @definition
            (lexical_declaration (variable_declarator name: (identifier) @name value: (function_expression))) @definition ;; Corrected node
            (expression_statement (assignment_expression left: [(identifier)(member_expression)] @name right: (arrow_function))) @definition
            (expression_statement (assignment_expression left: [(identifier)(member_expression)] @name right: (function_expression))) @definition ;; Corrected node
            (method_definition name: (property_identifier) @name) @definition
            (pair key: (property_identifier) @name value: [(arrow_function) (function_expression)]) @definition ;; Corrected node
        ]
        """,
    "classes": """
        [
            (class_declaration name: (identifier) @name) @definition
            (lexical_declaration (variable_declarator name: (identifier) @name value: (class))) @definition
        ]
        """,
}
JAVASCRIPT_QUERIES["functions"] = JAVASCRIPT_QUERIES.pop("functions_alt")

class JavascriptParser(BaseParser):
    def __init__(self):
        """Initializes the JavascriptParser and loads the Tree-sitter language and queries."""
        super().__init__()
        self.language = get_language("javascript")
        self.parser = get_parser("javascript")
        self.queries = {}
        self.expected_keys = {"imports", "functions", "classes"}
        if self.language:
            logger.info("Attempting to compile JavaScript Tree-sitter queries one by one...")
            failed_queries = []
            for name, query_str in JAVASCRIPT_QUERIES.items():
                try:
                    self.queries[name] = self.language.query(query_str)
                    logger.debug(f"Successfully compiled JavaScript query: {name}")
                except Exception as e:
                    logger.error(f"Failed to compile JavaScript query '{name}': {e}", exc_info=True)
                    failed_queries.append(name)

            if not failed_queries:
              logger.info("Successfully compiled ALL JavaScript queries.")
            else:
              logger.error(f"Failed to compile the following JavaScript queries: {', '.join(failed_queries)}. JavaScript parsing will be limited.")
              if any(key in failed_queries for key in self.expected_keys):
                logger.error(f"Core JS queries failed ({', '.join(failed_queries)}), clearing all queries.")
                self.queries = {}
              else:
                logger.warning(f"Non-core JS queries failed ({', '.join(failed_queries)}), proceeding with limited parsing.")

        else:
            logger.error("JavaScript tree-sitter language not loaded.")

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[BaseModel, None]:
        # Check if essential queries are loaded
        essential_queries_loaded = self.language and self.queries and self.expected_keys.issubset(self.queries.keys())

        content = await read_file_content(file_path)
        if content is None: return

        # Always yield chunks
        for i, chunk_text in enumerate(basic_chunker(content)):
                if chunk_text.strip(): yield TextChunk(f"{file_id}:chunk:{i}", file_id, chunk_text, i)

        # Only proceed with detailed parsing if essential queries are available
        if not essential_queries_loaded:
            logger.error(f"JS prerequisites missing or core queries failed compilation. Skipping detailed parsing for {file_path}")
            return # Exit after yielding chunks

        import_query = self.queries.get("imports")
        function_query = self.queries.get("functions")
        class_query = self.queries.get("classes")

        try:
            content_bytes = bytes(content, "utf8")
            tree = self.parser.parse(content_bytes)
            root_node = tree.root_node

            # 2. Process Dependencies (using matches)
            if import_query:
                processed_imports = set()
                logger.debug(f"Executing JS query 'imports' for {file_path}")
                for match_id, captures_in_match in import_query.matches(root_node):
                    statement_node: Optional[TSNODE_TYPE] = None
                    import_from_node: Optional[TSNODE_TYPE] = None
                    target = "unknown_import" # Default target

                    for capture_name, node in captures_in_match:
                        # Use the statement capture to get the full line and location
                        if capture_name in ["import_statement", "require_statement"]:
                            statement_node = node
                        # Use the specific capture for the source module path
                        elif capture_name == "import_from":
                            import_from_node = node

                    if not statement_node: continue # Need the statement for context/location

                    start_line = statement_node.start_point[0] + 1
                    # Avoid processing the same line multiple times if query matches overlap
                    if start_line in processed_imports: continue

                    if import_from_node:
                        target = get_node_text(import_from_node, content_bytes)
                        # Clean quotes
                        if target and target.startswith(('"', "'")): target = target[1:-1]
                    else:
                         # Fallback if @import_from wasn't captured (e.g., maybe just require target)
                         # Try to find it within the statement node (less reliable)
                         logger.warning(f"JS import/require statement found at line {start_line} without explicit @import_from capture. Target might be inaccurate.")
                         # Basic extraction from snippet as fallback
                         snippet_text = get_node_text(statement_node, content_bytes) or ""
                         match = re.search(r'require\([\'"]([^\'"]+)[\'"]\)|from\s+[\'"]([^\'"]+)[\'"]', snippet_text)
                         if match:
                             target = match.group(1) or match.group(2) or "unknown_require_fallback"


                    snippet = get_node_text(statement_node, content_bytes)
                    end_line = statement_node.end_point[0] + 1
                    import_key = (target, start_line) # Use tuple for set key

                    if target and target != "unknown_import" and snippet:
                        dep_id_str = f"{file_id}:dep:{target}:{start_line}"
                        logger.debug(f"Yielding JS Dependency: {target}")
                        yield Dependency(dep_id_str, file_id, target, snippet, start_line, end_line)
                        processed_imports.add(start_line) # Add line number to prevent duplicates
                    elif not target or target == "unknown_import":
                        logger.warning(f"Could not determine JS import/require target at {file_path}:{start_line}. Snippet: {snippet}")

            # 3. Process Functions/Classes (using matches)
            entity_configs = [
                (function_query, "FunctionDefinition"),
                (class_query, "ClassDefinition"),
            ]
            for query, entity_class_name in entity_configs:
                if query:
                     logger.debug(f"Executing JS query for '{entity_class_name}' in {file_path}")
                     for match_id, captures_in_match in query.matches(root_node):
                         definition_node: Optional[TSNODE_TYPE] = None
                         name_node: Optional[TSNODE_TYPE] = None
                         name = "anonymous" # Default for functions without explicit name capture

                         for capture_name, node in captures_in_match:
                             # Prioritize @definition capture for the node's extent
                             if capture_name == "definition": definition_node = node
                             elif capture_name == "name": name_node = node
                             # If no @definition, use assignment context as node extent
                             elif capture_name in ["variable_assignment", "expression_assignment"] and not definition_node:
                                 definition_node = node

                         if not definition_node: continue # Skip if no definition context found

                         if name_node:
                             potential_name = get_node_text(name_node, content_bytes)
                             # Clean up member expression names if needed
                             if potential_name and '.' in potential_name and entity_class_name == "FunctionDefinition":
                                 name = potential_name.split('.')[-1] # e.g., module.exports.func -> func
                             elif potential_name:
                                 name = potential_name
                         # If name wasn't captured via @name, it remains 'anonymous' or could be inferred if needed

                         entity_text = get_node_text(definition_node, content_bytes)
                         start_line = definition_node.start_point[0] + 1
                         end_line = definition_node.end_point[0] + 1

                         if name and entity_text:
                             entity_id_str = f"{file_id}:{entity_class_name}:{name}:{start_line}"
                             logger.debug(f"Yielding JS Entity: {entity_class_name} - {name}")
                             yield CodeEntity(entity_id_str, entity_class_name, name, file_id, entity_text, start_line, end_line)
                         else:
                             logger.warning(f"Could not extract name or text for JS {entity_class_name} at {file_path}:{start_line}")

        except Exception as e:
            logger.error(f"Failed to parse JavaScript file {file_path}: {e}", exc_info=True)
