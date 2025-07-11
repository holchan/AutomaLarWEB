from pydantic import BaseModel
from typing import AsyncGenerator, Optional, List, Dict
from collections import defaultdict

from .base_parser import BaseParser
from ..entities import TextChunk, CodeEntity, Relationship, ParserOutput
from ..chunking import basic_chunker
from ..utils import read_file_content, get_node_text, logger, TSNODE_TYPE
from .treesitter_setup import get_parser, get_language

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
        (type_definition declarator: (type_identifier) @name) @definition
        """,
}

class CParser(BaseParser):
    def __init__(self):
        super().__init__()
        self.language = get_language("c")
        self.parser = get_parser("c")
        self.queries = {}
        if self.language:
            logger.info("Compiling C Tree-sitter queries...")
            try:
                for name, query_str in C_QUERIES.items():
                    self.queries[name] = self.language.query(query_str)
                logger.info("C queries compiled successfully.")
            except Exception as e:
                logger.error(f"Failed to compile C query '{name}': {e}", exc_info=True)
        else:
            logger.error("C tree-sitter language not loaded.")

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[ParserOutput, None]:
        required_queries = set(C_QUERIES.keys())
        prerequisites_met = (
            self.parser and
            self.language and
            self.queries and
            required_queries.issubset(self.queries.keys())
        )
        if not prerequisites_met:
            missing_q = required_queries - self.queries.keys()
            logger.error(f"C parser prerequisites failed for {file_path}. Missing compiled queries: {missing_q}. Skipping.")
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
                chunk_id_str = f"{file_id}:{i}"
                chunk_node = TextChunk(id=chunk_id_str, type="TextChunk", start_line=chunk_start_line, end_line=chunk_end_line, chunk_content=chunk_text)
                yield chunk_node
                chunk_nodes.append(chunk_node)
                yield Relationship(source_id=file_id, target_id=chunk_id_str, type="CONTAINS_CHUNK")
                current_line = chunk_end_line + 1

            def find_chunk_for_node(node: TSNODE_TYPE) -> Optional[TextChunk]:
                if not node: return None
                node_start_line = node.start_point[0] + 1
                node_end_line = node.end_point[0] + 1
                best_chunk = None; min_diff = float('inf')
                for chunk in chunk_nodes:
                    if chunk.start_line <= node_start_line and chunk.end_line >= node_end_line:
                        diff = node_start_line - chunk.start_line
                        if diff < min_diff: min_diff = diff; best_chunk = chunk
                if not best_chunk:
                     logger.warning(f"[{file_path}] Could not find containing chunk for node at lines {node_start_line}-{node_end_line}")
                return best_chunk

            entity_configs = [
                ("functions", "FunctionDefinition"), ("structs", "StructDefinition"),
                ("unions", "UnionDefinition"), ("enums", "EnumDefinition"),
                ("typedefs", "TypeDefinition"),
            ]
            chunk_entity_counters = defaultdict(lambda: defaultdict(int))

            for query_name, entity_type_str in entity_configs:
                query = self.queries.get(query_name)
                if not query:
                    logger.warning(f"Query '{query_name}' not found/compiled for C parser in {file_path}")
                    continue

                for match_index, actual_captures_dict in query.matches(root_node):
                    captured_definition = actual_captures_dict.get("definition")
                    captured_name = actual_captures_dict.get("name")

                    definition_node: Optional[TSNODE_TYPE] = None
                    if captured_definition:
                        definition_node = captured_definition[0] if isinstance(captured_definition, list) else captured_definition

                    name_node: Optional[TSNODE_TYPE] = None
                    if captured_name:
                        name_node = captured_name[0] if isinstance(captured_name, list) else captured_name

                    if definition_node and name_node:
                        name = get_node_text(name_node, content_bytes)
                        if not name: continue
                        snippet_content = get_node_text(definition_node, content_bytes)
                        if not snippet_content: continue

                        parent_chunk = find_chunk_for_node(definition_node)
                        if not parent_chunk: continue

                        chunk_id_val = parent_chunk.id
                        index_in_chunk = chunk_entity_counters[chunk_id_val][(entity_type_str, name)]
                        chunk_entity_counters[chunk_id_val][(entity_type_str, name)] += 1
                        code_entity_id = f"{chunk_id_val}:{entity_type_str}:{name}:{index_in_chunk}"

                        code_entity = CodeEntity(id=code_entity_id, type=entity_type_str, snippet_content=snippet_content)
                        yield code_entity
                        yield Relationship(source_id=chunk_id_val, target_id=code_entity_id, type="CONTAINS_ENTITY")

            include_query = self.queries.get("includes")
            if include_query:
                processed_imports = set()
                for match_index, actual_captures_dict in include_query.matches(root_node):
                    captured_statement = actual_captures_dict.get("include_statement")
                    captured_target = actual_captures_dict.get("include")

                    statement_node: Optional[TSNODE_TYPE] = None
                    if captured_statement:
                        statement_node = captured_statement[0] if isinstance(captured_statement, list) else captured_statement

                    target_node: Optional[TSNODE_TYPE] = None
                    if captured_target:
                        target_node = captured_target[0] if isinstance(captured_target, list) else captured_target

                    if statement_node and target_node:
                        target_module_string = get_node_text(target_node, content_bytes)
                        if target_module_string and target_module_string.startswith(('"', '<')):
                            target_module_string = target_module_string[1:-1]
                        if target_module_string:
                            start_line = statement_node.start_point[0] + 1
                            import_key = (target_module_string, start_line)
                            if import_key not in processed_imports:
                                yield Relationship(source_id=file_id, target_id=target_module_string, type="IMPORTS")
                                processed_imports.add(import_key)
        except Exception as e:
            logger.error(f"Failed during detailed parsing of C file {file_path}: {e}", exc_info=True)
