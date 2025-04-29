# src/parser/parsers/javascript_parser.py
from pydantic import BaseModel
from typing import AsyncGenerator, Optional
from .base_parser import BaseParser
from ..entities import TextChunk, CodeEntity, Dependency
from ..chunking import basic_chunker
from ..utils import read_file_content, get_node_text, logger, TSNODE_TYPE
from .treesitter_setup import get_parser, get_language
import os

# --- QUERIES based on AI Expert analysis of MODERN grammar ---
JAVASCRIPT_QUERIES = {
    "imports": """
        [
            ;; Combined import statement query using optional captures
            (import_statement
              (import_clause (identifier) @default_import)? ;; Optional default import name
              (import_clause (namespace_import (identifier) @namespace_import))? ;; Optional namespace name
              (import_clause (named_imports (import_specifier name: (identifier) @named_import)))? ;; Optional named import name
              (import_clause (named_imports (import_specifier property: (identifier) @property_import name: (identifier) @named_import_alias)))? ;; Optional named import with alias
              source: (string) @import_from ;; Source field is reliable now
            ) @import_statement

            ;; require('...')
            (lexical_declaration
              (variable_declarator
                name: (identifier) @require_target
                value: (call_expression
                         function: (identifier) @_req
                         arguments: (arguments (string) @import_from)
                       )
              )
              (#match? @_req "^require$")
            ) @require_statement

            ;; import("module")
            (call_expression
              function: (import) ;; Specific 'import' node
              arguments: (arguments (string) @import_from)
            ) @import_statement
        ]
        """,
    "functions": """
        [
            (function_declaration name: (identifier) @name parameters: (formal_parameters)? @params) @definition
            (lexical_declaration
              (variable_declarator
                name: (identifier) @name
                value: (arrow_function parameters: (formal_parameters)? @params)
              )
            ) @definition
             (lexical_declaration ;; Assignment of anonymous function
              (variable_declarator
                name: (identifier) @name
                value: (function_expression) ;; <<< CORRECTED node name
              )
            ) @definition
            (expression_statement
              (assignment_expression
                left: [(identifier) (member_expression)] @name
                right: (arrow_function parameters: (formal_parameters)? @params)
              )
            ) @definition
            (expression_statement ;; Assignment of anonymous function
              (assignment_expression
                left: [(identifier) (member_expression)] @name
                right: (function_expression) ;; <<< CORRECTED node name
              )
            ) @definition
            (method_definition name: (property_identifier) @name parameters: (formal_parameters)? @params) @definition
            (pair
              key: (property_identifier) @name
              value: (arrow_function parameters: (formal_parameters)? @params)
            ) @definition
            (pair ;; Assignment of anonymous function
              key: (property_identifier) @name
              value: (function_expression) ;; <<< CORRECTED node name
            ) @definition
        ]
        """,
    "classes": """
        [
            (class_declaration name: (identifier) @name) @definition
            (lexical_declaration (variable_declarator name: (identifier) @name value: (class))) @definition
        ]
        """,
}
# --- END QUERIES ---

class JavascriptParser(BaseParser):
     def __init__(self):
        """Initializes the JavascriptParser and loads the Tree-sitter language and queries."""
        super().__init__()
        self.language = get_language("javascript")
        self.parser = get_parser("javascript")
        self.queries = {}
        if self.language:
            logger.info("Attempting to compile JavaScript Tree-sitter queries one by one...") # Changed log
            # --- MODIFIED: Compile one by one for better error reporting ---
            failed_queries = []
            for name, query_str in JAVASCRIPT_QUERIES.items():
                print(f"DEBUG: Compiling JS query: {name}") # FORCE PRINT
                try:
                    self.queries[name] = self.language.query(query_str)
                    logger.debug(f"Successfully compiled JavaScript query: {name}")
                    print(f"DEBUG: Successfully compiled JS query: {name}") # FORCE PRINT
                except Exception as e:
                    logger.error(f"Failed to compile JavaScript query '{name}': {e}", exc_info=True)
                    print(f"DEBUG: FAILED to compile JS query '{name}': {e}") # FORCE PRINT
                    failed_queries.append(name)

            if not failed_queries:
                logger.info("Successfully compiled ALL JavaScript queries.")
            else:
                logger.error(f"Failed to compile the following JavaScript queries: {', '.join(failed_queries)}. JavaScript parsing will be limited.")
                self.queries = {} # Clear queries if ANY failed
             # --- END MODIFICATION ---
        else:
            logger.error("JavaScript tree-sitter language not loaded.")

     # Reverted to simpler parse logic relying on direct query captures
     async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[BaseModel, None]:
        expected_queries = {"imports", "functions", "classes"}
        if not self.language or not self.queries or not expected_keys.issubset(self.queries.keys()):
             logger.error(f"JS prerequisites missing (Lang: {bool(self.language)}, Queries Compiled: {bool(self.queries)}). Skipping detailed parsing for {file_path}")
             content_fallback = await read_file_content(file_path)
             if content_fallback:
                 for i, chunk_text in enumerate(basic_chunker(content_fallback)):
                     if chunk_text.strip(): yield TextChunk(f"{file_id}:chunk:{i}", file_id, chunk_text, i)
             return

        import_query = self.queries.get("imports")
        function_query = self.queries.get("functions")
        class_query = self.queries.get("classes")
        content = await read_file_content(file_path)
        if content is None: return

        try:
            content_bytes = bytes(content, "utf8")
            tree = self.parser.parse(content_bytes)
            root_node = tree.root_node

            # 1. Yield Chunks
            for i, chunk_text in enumerate(basic_chunker(content)):
                 if chunk_text.strip(): yield TextChunk(f"{file_id}:chunk:{i}", file_id, chunk_text, i)

            # 2. Process Dependencies (using direct captures)
            if import_query:
                processed_imports = set()
                # Use captures() method which returns (node, capture_name) tuples
                for node, capture_name in import_query.captures(root_node):
                    # We need the statement node AND the source node for each match
                    # This requires slightly more complex state management if captures are separate
                    # For simplicity, let's assume the AI query structure works where @import_from
                    # is captured alongside the relevant @import_statement or @require_statement
                    # within the *same match*. We'll need to find both within the captures of a single match.

                    # This part might need refinement based on how query.captures actually groups things.
                    # A safer approach might be query.matches and processing captures per match.
                    # Let's stick to the simpler captures() for now and refine if needed.

                    # Find the relevant statement node associated with this capture if needed
                    # (Logic depends heavily on the exact query structure and capture names used)
                    # For now, let's assume we get the info needed per capture event (might be wrong)

                    statement_node: Optional[TSNODE_TYPE] = None
                    target = "unknown_import"
                    import_from_node: Optional[TSNODE_TYPE] = None

                    # If the capture is the statement itself
                    if capture_name in ["import_statement", "require_statement"]:
                       statement_node = node
                       # Need to find the associated @import_from for this statement
                       # This is hard with captures() alone. query.matches() is better here.
                       # Let's revert to matches approach for clarity
                       pass # Skip processing here, handle in matches loop below

                    # --- Reverting to matches loop for cleaner state per import ---
                processed_imports_matches = set()
                for match_id, captures_in_match in import_query.matches(root_node):
                    statement_node_match: Optional[TSNODE_TYPE] = None
                    import_from_node_match: Optional[TSNODE_TYPE] = None
                    target_match = "unknown_import"

                    for capture_name_match, node_match in captures_in_match:
                        if capture_name_match in ["import_statement", "require_statement"]:
                            statement_node_match = node_match
                        elif capture_name_match == "import_from":
                            import_from_node_match = node_match

                    if not statement_node_match: continue # Need the statement

                    if import_from_node_match:
                        target_match = get_node_text(import_from_node_match, content_bytes)
                        if target_match and target_match.startswith(('"', "'")): target_match = target_match[1:-1]
                    else:
                        # This indicates the query didn't capture @import_from for this match
                        logger.warning(f"Could not find @import_from capture for statement at {file_path}:{statement_node_match.start_point[0]+1}")
                        continue

                    snippet = get_node_text(statement_node_match, content_bytes)
                    start_line = statement_node_match.start_point[0] + 1
                    end_line = statement_node_match.end_point[0] + 1
                    import_key = (target_match, start_line)

                    if target_match and snippet and import_key not in processed_imports_matches:
                        dep_id_str = f"{file_id}:dep:{target_match}:{start_line}"
                        yield Dependency(dep_id_str, file_id, target_match, snippet, start_line, end_line)
                        processed_imports_matches.add(import_key)
                 # --- End matches loop ---


            # 3. Process Functions/Classes (using direct captures)
            if function_query:
                 for node, capture_name in function_query.captures(root_node):
                    if capture_name == "definition":
                        name_node = next((c[0] for c in function_query.captures(node) if c[1] == 'name'), None)
                        if name_node:
                            name = get_node_text(name_node, content_bytes)
                            if name and name_node.type != 'identifier' and '.' in name: name = name.split('.')[-1]
                            entity_text = get_node_text(node, content_bytes)
                            start_line = node.start_point[0] + 1; end_line = node.end_point[0] + 1
                            if name and entity_text: yield CodeEntity(f"{file_id}:{name}:{start_line}", "FunctionDefinition", name, file_id, entity_text, start_line, end_line)

            if class_query:
                 for node, capture_name in class_query.captures(root_node):
                     if capture_name == "definition":
                        name_node = next((c[0] for c in class_query.captures(node) if c[1] == 'name'), None)
                        if name_node:
                            name = get_node_text(name_node, content_bytes)
                            entity_text = get_node_text(node, content_bytes)
                            start_line = node.start_point[0] + 1; end_line = node.end_point[0] + 1
                            if name and entity_text: yield CodeEntity(f"{file_id}:{name}:{start_line}", "ClassDefinition", name, file_id, entity_text, start_line, end_line)

        except Exception as e:
            logger.error(f"Failed to parse JavaScript file {file_path}: {e}", exc_info=True)
