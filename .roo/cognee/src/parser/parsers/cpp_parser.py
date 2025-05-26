from pydantic import BaseModel
from typing import AsyncGenerator, Optional, List, Dict, Any
from collections import defaultdict

from .base_parser import BaseParser
from ..entities import TextChunk, CodeEntity, Relationship, ParserOutput
from ..chunking import basic_chunker
from ..utils import read_file_content, get_node_text, logger, TSNODE_TYPE
from .treesitter_setup import get_parser, get_language

CPP_QUERIES = {
    "includes": """
        (preproc_include path: [(string_literal) (system_lib_string)] @include) @include_statement
        """,
    "functions": """
        (function_definition
            declarator: [
                (function_declarator declarator: (identifier) @name)
                (function_declarator declarator: (field_identifier) @name)
                (function_declarator declarator: (operator_name) @name)
                (destructor_name) @name
            ]
        ) @definition
        """,
    "classes": """
        (class_specifier
            name: [(type_identifier) (identifier)] @name
            base_clause: (base_clause)? @heritage
        ) @definition
        """,
    "structs": """
        (struct_specifier
            name: [(type_identifier) (identifier)] @name
            base_clause: (base_clause)? @heritage
        ) @definition
        """,
    "namespaces": """
        (namespace_definition name: (identifier) @name) @definition
        """,
    "enums": """
        [
            (enum_specifier name: [(type_identifier) (identifier)] @name) @definition
            (enum_specifier class name: [(type_identifier) (identifier)] @name) @definition
        ]
        """,
    "typedefs": """
        (type_definition declarator: [(type_identifier)(identifier)] @name) @definition
        """,
    "using_namespace": """
        (using_declaration "namespace" name: [(identifier)(nested_namespace_specifier)] @name) @using_statement
        """,
    "using_alias": """
        (alias_declaration name: (type_identifier) @name) @using_statement
        """,
    "heritage_details": """
        (base_specifier name: [(identifier)(type_identifier)(qualified_identifier)] @extends_name)
        """
}

class CppParser(BaseParser):
    """
    Parses C++ files (.cpp, .hpp), yielding TextChunk, CodeEntity (minimal),
    and Relationship objects. Skips file if prerequisites fail.
    """
    def __init__(self):
        """Initializes the CppParser."""
        super().__init__()
        self.language = get_language("cpp")
        self.parser = get_parser("cpp")
        self.queries = {}
        if self.language:
            logger.info("Compiling C++ Tree-sitter queries...")
            try:
                for name, query_str in CPP_QUERIES.items():
                    self.queries[name] = self.language.query(query_str)
                logger.info("C++ queries compiled successfully.")
            except Exception as e:
                logger.error(f"Failed to compile C++ queries: {e}", exc_info=True)
                self.queries = {}
        else:
            logger.error("C++ tree-sitter language not loaded.")

    def _extract_list_details(self, query: Any, node: TSNODE_TYPE, capture_name: str, content_bytes: bytes) -> List[str]:
        """Helper to find all instances of a capture within a node."""
        details = []
        if not query or not node: return details
        for captured_node, captured_node_name in query.captures(node):
            if captured_node_name == capture_name:
                text = get_node_text(captured_node, content_bytes)
                if text:
                    details.append(text)
        return details

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[ParserOutput, None]:
        """Parses a C++ file. Yields nothing if prerequisites fail."""
        required_queries = set(CPP_QUERIES.keys())
        prerequisites_met = (
            self.parser and
            self.language and
            self.queries and
            required_queries.issubset(self.queries.keys())
        )
        if not prerequisites_met:
            logger.error(f"C++ parser prerequisites missing or core queries failed for {file_path}. SKIPPING detailed parsing for this file.")
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
                ("structs", "StructDefinition"),
                ("namespaces", "NamespaceDefinition"),
                ("enums", "EnumDefinition"),
                ("typedefs", "TypeDefinition"),
            ]
            chunk_entity_counters = defaultdict(lambda: defaultdict(int))
            heritage_detail_query = self.queries.get("heritage_details")

            for query_name, entity_type_str in entity_configs:
                query = self.queries.get(query_name)
                logger.debug(f"[{file_path}] Running query '{query_name}'...")
                for match_id, captures_in_match in query.matches(root_node):
                    definition_node: Optional[TSNODE_TYPE] = None
                    name_node: Optional[TSNODE_TYPE] = None
                    heritage_node: Optional[TSNODE_TYPE] = None

                    for capture_name, node in captures_in_match:
                        if capture_name == "definition": definition_node = node
                        elif capture_name == "name": name_node = node
                        elif capture_name == "heritage": heritage_node = node

                    if definition_node and name_node:
                        name = get_node_text(name_node, content_bytes)
                        if not name: continue
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

                        if entity_type_str in ["ClassDefinition", "StructDefinition"] and heritage_node and heritage_detail_query:
                            extends_names = self._extract_list_details(heritage_detail_query, heritage_node, "extends_name", content_bytes)
                            for parent_name in extends_names:
                                yield Relationship(source_id=code_entity_id, target_id=parent_name, type="EXTENDS")
                                logger.debug(f"[{file_path}] Yielded EXTENDS: {name} -> {parent_name}")

            processed_directives = set()

            include_query = self.queries.get("includes")
            logger.debug(f"[{file_path}] Running query 'includes'...")
            for match_id, captures_in_match in include_query.matches(root_node):
                statement_node: Optional[TSNODE_TYPE] = None
                target_node: Optional[TSNODE_TYPE] = None
                for capture_name, node in captures_in_match:
                    if capture_name == "include_statement": statement_node = node
                    elif capture_name == "include": target_node = node
                if statement_node and target_node:
                    target_module_string = get_node_text(target_node, content_bytes)
                    if target_module_string and target_module_string.startswith(('"', '<')):
                        target_module_string = target_module_string[1:-1]
                    if target_module_string:
                        start_line = statement_node.start_point[0] + 1
                        import_key = (target_module_string, start_line)
                        if import_key not in processed_directives:
                            yield Relationship(source_id=file_id, target_id=target_module_string, type="IMPORTS")
                            processed_directives.add(import_key)
                            logger.debug(f"[{file_path}] Yielded IMPORTS relationship (include): {file_id} -> {target_module_string}")

            using_ns_query = self.queries.get("using_namespace")
            if using_ns_query:
                logger.debug(f"[{file_path}] Running query 'using_namespace'...")
                for match_id, captures_in_match in using_ns_query.matches(root_node):
                    statement_node: Optional[TSNODE_TYPE] = None
                    target_node: Optional[TSNODE_TYPE] = None
                    for capture_name, node in captures_in_match:
                        if capture_name == "using_statement": statement_node = node
                        elif capture_name == "name": target_node = node
                    if statement_node and target_node:
                        target_namespace = get_node_text(target_node, content_bytes)
                        if target_namespace:
                            start_line = statement_node.start_point[0] + 1
                            using_key = (target_namespace, start_line)
                            if using_key not in processed_directives:
                                yield Relationship(source_id=file_id, target_id=target_namespace, type="IMPORTS")
                                processed_directives.add(using_key)
                                logger.debug(f"[{file_path}] Yielded IMPORTS relationship (using namespace): {file_id} -> {target_namespace}")

            using_alias_query = self.queries.get("using_alias")
            if using_alias_query:
                logger.debug(f"[{file_path}] Running query 'using_alias'...")
                for match_id, captures_in_match in using_alias_query.matches(root_node):
                    statement_node: Optional[TSNODE_TYPE] = None
                    target_node: Optional[TSNODE_TYPE] = None
                    for capture_name, node in captures_in_match:
                        if capture_name == "using_statement": statement_node = node
                        elif capture_name == "name": target_node = node
                    if statement_node and target_node:
                        alias_name = get_node_text(target_node, content_bytes)
                        if alias_name:
                            start_line = statement_node.start_point[0] + 1
                            alias_key = (alias_name, start_line)
                            if alias_key not in processed_directives:
                                processed_directives.add(alias_key)
                                logger.debug(f"[{file_path}] Processed 'using alias' for: {alias_name} (No relationship yielded)")

        except Exception as e:
            logger.error(f"Failed during detailed parsing of C++ file {file_path}: {e}", exc_info=True)
