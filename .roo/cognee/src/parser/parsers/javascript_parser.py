# src/parser/parsers/javascript_parser.py
import re
from typing import AsyncGenerator, Optional, List, Dict
from collections import defaultdict
from pydantic import BaseModel

from .base_parser import BaseParser
from ..entities import TextChunk, CodeEntity, Relationship, ParserOutput
from ..chunking import basic_chunker
from ..utils import read_file_content, get_node_text, logger, TSNODE_TYPE
from .treesitter_setup import get_parser, get_language

JAVASCRIPT_QUERIES = {
"imports": """
    [
        (import_statement source: (string) @import_from) @import_statement
        (lexical_declaration
            (variable_declarator
            value: (call_expression function: (identifier) @_req arguments: (arguments (string) @import_from)))
            (#match? @_req "^require$")
        ) @import_statement
    ]
    """,
    "functions": """
        [
            (function_declaration name: (identifier) @name) @definition
            (lexical_declaration (variable_declarator name: (identifier) @name value: (arrow_function))) @definition
            (lexical_declaration (variable_declarator name: (identifier) @name value: (function_expression))) @definition
            (expression_statement (assignment_expression left: [(identifier)(member_expression)] @name right: (arrow_function))) @definition
            (expression_statement (assignment_expression left: [(identifier)(member_expression)] @name right: (function_expression))) @definition
            (method_definition name: (property_identifier) @name) @definition
            (pair key: (property_identifier) @name value: [(arrow_function) (function_expression)]) @definition
        ]
        """,
    "classes": """
        (class_declaration
            name: (identifier) @name
            heritage: (extends_clause value: (_) @extends_name)?
        ) @definition
        """
}

class JavascriptParser(BaseParser):
    """
    Parses JavaScript files (.js, .jsx), yielding TextChunk, CodeEntity (minimal),
    and Relationship objects. Skips file if prerequisites fail.
    """
    def __init__(self):
        """Initializes the JavascriptParser."""
        super().__init__()
        self.language = get_language("javascript")
        self.parser = get_parser("javascript")
        self.queries = {}
        if self.language:
            logger.info("Compiling JavaScript Tree-sitter queries...")
            try:
                for name, query_str in JAVASCRIPT_QUERIES.items():
                    self.queries[name] = self.language.query(query_str)
                logger.info("JavaScript queries compiled successfully.")
            except Exception as e:
                logger.error(f"Failed to compile JavaScript queries: {e}", exc_info=True)
                self.queries = {}
        else:
            logger.error("JavaScript tree-sitter language not loaded.")

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[ParserOutput, None]:
        """Parses a JavaScript file. Yields nothing if prerequisites fail."""
        required_queries = {"imports", "functions", "classes"}
        prerequisites_met = (
            self.parser and
            self.language and
            self.queries and
            required_queries.issubset(self.queries.keys())
        )
        if not prerequisites_met:
            logger.error(f"JavaScript parser prerequisites missing or core queries failed for {file_path}. SKIPPING detailed parsing for this file.")
            return

        content = await read_file_content(file_path)
        if content is None: return

        try:
            content_bytes = bytes(content, "utf8")
            tree = self.parser.parse(content_bytes)
            root_node = tree.root_node

            chunks_data = basic_chunker(content)
            chunk_nodes: List[TextChunk] = []
            current_line = 1
            for i, chunk_text in enumerate(chunks_data):
                if not chunk_text.strip():
                    num_newlines = chunk_text.count('\n')
                    current_line += num_newlines
                    continue
                chunk_start_line = current_line
                num_newlines = chunk_text.count('\n')
                chunk_end_line = chunk_start_line + num_newlines
                chunk_id = f"{file_id}:{i}"
                chunk_node = TextChunk(id=chunk_id, start_line=chunk_start_line, end_line=chunk_end_line, chunk_content=chunk_text)
                yield chunk_node
                chunk_nodes.append(chunk_node)
                yield Relationship(source_id=file_id, target_id=chunk_id, type="CONTAINS_CHUNK")
                current_line = chunk_end_line + 1

            logger.debug(f"[{file_path}] Yielded {len(chunk_nodes)} TextChunk nodes.")

            def find_chunk_for_node(node: TSNODE_TYPE) -> Optional[TextChunk]:
                node_start_line = node.start_point[0] + 1
                node_end_line = node.end_point[0] + 1
                best_chunk = None
                min_diff = float('inf')
                for chunk in chunk_nodes:
                    if chunk.start_line <= node_start_line and chunk.end_line >= node_end_line:
                        diff = node_start_line - chunk.start_line
                        if diff < min_diff:
                            min_diff = diff
                            best_chunk = chunk
                if best_chunk: return best_chunk
                logger.warning(f"[{file_path}] Could not find containing chunk for node at lines {node_start_line}-{node_end_line}")
                return None

            entity_configs = [
                ("functions", "FunctionDefinition"),
                ("classes", "ClassDefinition"),
            ]
            chunk_entity_counters = defaultdict(lambda: defaultdict(int))

            for query_name, entity_type_str in entity_configs:
                query = self.queries.get(query_name)
                logger.debug(f"[{file_path}] Running query '{query_name}'...")
                for match_id, captures_in_match in query.matches(root_node):
                    definition_node: Optional[TSNODE_TYPE] = None
                    name_node: Optional[TSNODE_TYPE] = None
                    extends_node: Optional[TSNODE_TYPE] = None

                    for capture_name, node in captures_in_match:
                        if capture_name == "definition": definition_node = node
                        elif capture_name == "name": name_node = node
                        elif capture_name == "extends_name": extends_node = node

                    if entity_type_str == "FunctionDefinition" and not name_node and definition_node:
                        parent = definition_node.parent
                        if parent and parent.type == 'variable_declarator':
                            potential_name_node = parent.child_by_field_name('name')
                            if potential_name_node:
                                name_node = potential_name_node
                                logger.debug(f"[{file_path}] Inferred function name '{get_node_text(name_node, content_bytes)}' from variable assignment.")

                    if definition_node:
                        name = get_node_text(name_node, content_bytes) if name_node else "anonymous"
                        if entity_type_str == "ClassDefinition" and not name_node: continue

                        snippet_content = get_node_text(definition_node, content_bytes)
                        if not snippet_content: continue
                        parent_chunk = find_chunk_for_node(definition_node)
                        if not parent_chunk: continue
                        chunk_id = parent_chunk.id
                        index_in_chunk = chunk_entity_counters[chunk_id][(entity_type_str, name)]
                        chunk_entity_counters[chunk_id][(entity_type_str, name)] += 1
                        code_entity_id = f"{chunk_id}:{entity_type_str}:{name}:{index_in_chunk}"
                        code_entity = CodeEntity(id=code_entity_id, type=entity_type_str, snippet_content=snippet_content)
                        yield code_entity
                        yield Relationship(source_id=chunk_id, target_id=code_entity_id, type="CONTAINS_ENTITY")

                        if entity_type_str == "ClassDefinition" and extends_node:
                            extends_name_str = get_node_text(extends_node, content_bytes)
                            if extends_name_str:
                                yield Relationship(source_id=code_entity_id, target_id=extends_name_str, type="EXTENDS")
                                logger.debug(f"[{file_path}] Yielded EXTENDS: {name} -> {extends_name_str}")

            import_query = self.queries.get("imports")
            processed_imports = set()
            logger.debug(f"[{file_path}] Running query 'imports'...")
            for match_id, captures_in_match in import_query.matches(root_node):
                statement_node: Optional[TSNODE_TYPE] = None
                target_node: Optional[TSNODE_TYPE] = None
                for capture_name, node in captures_in_match:
                    if capture_name == "import_statement": statement_node = node
                    elif capture_name == "import_from": target_node = node

                if statement_node and target_node:
                    target_module_string = get_node_text(target_node, content_bytes)
                    if target_module_string and target_module_string.startswith(('"', "'")):
                        target_module_string = target_module_string[1:-1]
                    if target_module_string:
                        start_line = statement_node.start_point[0] + 1
                        import_key = (target_module_string, start_line)
                        if import_key not in processed_imports:
                            yield Relationship(source_id=file_id, target_id=target_module_string, type="IMPORTS")
                            processed_imports.add(import_key)
                            logger.debug(f"[{file_path}] Yielded IMPORTS relationship: {file_id} -> {target_module_string}")
                    else:
                        logger.warning(f"[{file_path}] Could not extract target module string from import/require statement at line {statement_node.start_point[0]+1}")

        except Exception as e:
            logger.error(f"Failed during detailed parsing of JavaScript file {file_path}: {e}", exc_info=True)
