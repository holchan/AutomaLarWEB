# src/parser/parsers/python_parser.py
from pydantic import BaseModel
from typing import AsyncGenerator, Optional, List, Dict
from collections import defaultdict

from .base_parser import BaseParser
from ..entities import TextChunk, CodeEntity, Relationship, ParserOutput
from ..chunking import basic_chunker
from ..utils import read_file_content, get_node_text, logger, TSNODE_TYPE
from .treesitter_setup import get_parser, get_language

PYTHON_QUERIES = {
    "imports": """
        [
            (import_statement name: (dotted_name) @module_name) @import_statement
            (import_from_statement
                module_name: (dotted_name)? @from_module
                name: (dotted_name) @imported_name
            ) @import_statement
            (import_from_statement
                module_name: (dotted_name)? @from_module
                name: (wildcard_import) @imported_name ;; For 'from x import *'
            ) @import_statement
        ]
        """,
    "functions": """
        (function_definition name: (identifier) @name) @definition
        """,
    "classes": """
        (class_definition
            name: (identifier) @name
            superclasses: (argument_list)? @superclasses
        ) @definition
        """,
    "superclass_names": """
        (argument_list (identifier) @name)
        """
}

class PythonParser(BaseParser):
    """
    Parses Python files (.py), yielding TextChunk, CodeEntity, and Relationship objects.
    """

    def __init__(self):
        """Initializes the PythonParser."""
        super().__init__()
        self.language = get_language("python")
        self.parser = get_parser("python")
        self.queries = {}
        if self.language:
            logger.info("Compiling Python Tree-sitter queries...")
            try:
                for name, query_str in PYTHON_QUERIES.items():
                    self.queries[name] = self.language.query(query_str)
                logger.info("Python queries compiled successfully.")
            except Exception as e:
                logger.error(f"Failed to compile Python queries: {e}", exc_info=True)
                self.queries = {}
        else:
            logger.error("Python tree-sitter language not loaded.")

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[ParserOutput, None]:
        """Parses a Python file."""
        required_queries = {"imports", "functions", "classes", "superclass_names"}
        if not self.parser or not self.language or not self.queries or not required_queries.issubset(self.queries.keys()):
            logger.error(f"Python parser prerequisites missing for {file_path}. Skipping detailed parsing.")
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
                chunk_node = TextChunk(
                    id=chunk_id,
                    start_line=chunk_start_line,
                    end_line=chunk_end_line,
                    chunk_content=chunk_text
                )
                yield chunk_node
                chunk_nodes.append(chunk_node)
                yield Relationship(source_id=file_id, target_id=chunk_id, type="CONTAINS_CHUNK")
                current_line = chunk_end_line + 1

            logger.debug(f"[{file_path}] Yielded {len(chunk_nodes)} TextChunk nodes.")

            def find_chunk_for_node(node: TSNODE_TYPE) -> Optional[TextChunk]:
                node_start_line = node.start_point[0] + 1
                node_end_line = node.end_point[0] + 1
                for chunk in chunk_nodes:
                    if chunk.start_line <= node_start_line and chunk.end_line >= node_end_line:
                        return chunk
                logger.warning(f"[{file_path}] Could not find containing chunk for node at lines {node_start_line}-{node_end_line}")
                return None

            entity_configs = [
                ("functions", "FunctionDefinition"),
                ("classes", "ClassDefinition"),
            ]
            chunk_entity_counters = defaultdict(lambda: defaultdict(int))
            superclass_query = self.queries.get("superclass_names")

            for query_name, entity_type_str in entity_configs:
                query = self.queries.get(query_name)
                if not query: continue

                logger.debug(f"[{file_path}] Running query '{query_name}'...")
                for match_id, captures_in_match in query.matches(root_node):
                    definition_node: Optional[TSNODE_TYPE] = None
                    name_node: Optional[TSNODE_TYPE] = None
                    superclasses_node: Optional[TSNODE_TYPE] = None

                    for capture_name, node in captures_in_match:
                        if capture_name == "definition": definition_node = node
                        elif capture_name == "name": name_node = node
                        elif capture_name == "superclasses": superclasses_node = node

                    if definition_node and name_node:
                        name = get_node_text(name_node, content_bytes)
                        if not name: continue
                        snippet_content = get_node_text(definition_node, content_bytes)
                        if not snippet_content: continue

                        start_line = definition_node.start_point[0] + 1
                        parent_chunk = find_chunk_for_node(definition_node)
                        if not parent_chunk: continue

                        chunk_id = parent_chunk.id
                        index_in_chunk = chunk_entity_counters[chunk_id][(entity_type_str, name)]
                        chunk_entity_counters[chunk_id][(entity_type_str, name)] += 1
                        code_entity_id = f"{chunk_id}:{entity_type_str}:{name}:{index_in_chunk}"

                        code_entity = CodeEntity(
                            id=code_entity_id,
                            type=entity_type_str,
                            snippet_content=snippet_content
                        )
                        yield code_entity
                        yield Relationship(source_id=chunk_id, target_id=code_entity_id, type="CONTAINS_ENTITY")

                        if entity_type_str == "ClassDefinition" and superclasses_node and superclass_query:
                            for sc_node, sc_capture_name in superclass_query.captures(superclasses_node):
                                if sc_capture_name == "name":
                                    superclass_name = get_node_text(sc_node, content_bytes)
                                    if superclass_name:
                                        yield Relationship(source_id=code_entity_id, target_id=superclass_name, type="EXTENDS")
                                        logger.debug(f"[{file_path}] Yielded EXTENDS: {name} -> {superclass_name}")

            import_query = self.queries.get("imports")
            if import_query:
                processed_imports = set()
                logger.debug(f"[{file_path}] Running query 'imports'...")
                for match_id, captures_in_match in import_query.matches(root_node):
                    statement_node: Optional[TSNODE_TYPE] = None
                    target_module_string: Optional[str] = None

                    module_name_node: Optional[TSNODE_TYPE] = None
                    from_module_node: Optional[TSNODE_TYPE] = None
                    imported_name_node: Optional[TSNODE_TYPE] = None

                    for capture_name, node in captures_in_match:
                        if capture_name == "import_statement": statement_node = node
                        elif capture_name == "module_name": module_name_node = node
                        elif capture_name == "from_module": from_module_node = node
                        elif capture_name == "imported_name": imported_name_node = node

                    if not statement_node: continue

                    start_line = statement_node.start_point[0] + 1

                    if from_module_node:
                        from_module = get_node_text(from_module_node, content_bytes) or ""
                        imported_name = get_node_text(imported_name_node, content_bytes) if imported_name_node else ""
                        target_module_string = from_module
                    elif module_name_node:
                        target_module_string = get_node_text(module_name_node, content_bytes)

                    if target_module_string:
                        import_key = (target_module_string, start_line)
                        if import_key not in processed_imports:
                            yield Relationship(source_id=file_id, target_id=target_module_string, type="IMPORTS")
                            processed_imports.add(import_key)
                            logger.debug(f"[{file_path}] Yielded IMPORTS relationship: {file_id} -> {target_module_string}")
                    else:
                        logger.warning(f"[{file_path}] Could not extract target module string from import statement at line {start_line}")

        except Exception as e:
            logger.error(f"Failed to parse Python file {file_path}: {e}", exc_info=True)
