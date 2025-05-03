# src/parser/parsers/rust_parser.py
import re
from typing import AsyncGenerator, Optional, List, Dict, Any
from collections import defaultdict
from pydantic import BaseModel

from .base_parser import BaseParser
from ..entities import TextChunk, CodeEntity, Relationship, ParserOutput
from ..chunking import basic_chunker
from ..utils import read_file_content, get_node_text, logger, TSNODE_TYPE
from .treesitter_setup import get_parser, get_language

RUST_QUERIES = {
    "imports": """
        [
            (use_declaration argument: (_) @path) @use_statement
            (extern_crate_declaration (identifier) @crate_name) @extern_crate
        ]
        """,
    "functions": """
        (function_item name: (identifier) @name) @definition
        """,
    "structs": """
        (struct_item name: (type_identifier) @name) @definition
        """,
    "enums": """
        (enum_item name: (type_identifier) @name) @definition
        """,
    "traits": """
        (trait_item name: (type_identifier) @name) @definition
        """,
    "impls": """
        (impl_item
            trait: (_) @trait_name ;; Optional: Capture the trait being implemented
            type: [(type_identifier) (generic_type)] @impl_type ;; Capture the type the impl is for
        ) @definition
        """,
    "macros": """
        (macro_definition name: (identifier) @name) @definition
        """,
    "mods": """
        (mod_item name: (identifier) @name) @definition
        """
}

class RustParser(BaseParser):
    """
    Parses Rust files (.rs), yielding TextChunk, CodeEntity (minimal),
    and Relationship objects.
    """
    def __init__(self):
        """Initializes the RustParser."""
        super().__init__()
        self.language = get_language("rust")
        self.parser = get_parser("rust")
        self.queries = {}
        if self.language:
            logger.info("Compiling Rust Tree-sitter queries...")
            try:
                for name, query_str in RUST_QUERIES.items():
                    self.queries[name] = self.language.query(query_str)
                logger.info("Rust queries compiled successfully.")
            except Exception as e:
                logger.error(f"Failed to compile Rust queries: {e}", exc_info=True)
                self.queries = {}
        else:
            logger.error("Rust tree-sitter language not loaded.")

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[ParserOutput, None]:
        """Parses a Rust file."""
        required_queries = {"imports", "functions", "structs", "enums", "traits", "impls"}
        if not self.parser or not self.language or not self.queries or not required_queries.issubset(self.queries.keys()):
            logger.error(f"Rust parser prerequisites missing for {file_path}. Skipping detailed parsing.")
            content_fallback = await read_file_content(file_path)
            if content_fallback:
                current_line = 1
                for i, chunk_text in enumerate(basic_chunker(content_fallback)):
                    if chunk_text.strip():
                        chunk_start_line = current_line
                        num_newlines = chunk_text.count('\n')
                        chunk_end_line = chunk_start_line + num_newlines
                        chunk_id = f"{file_id}:{i}"
                        yield TextChunk(id=chunk_id, chunk_content=chunk_text, start_line=chunk_start_line, end_line=chunk_end_line)
                        yield Relationship(source_id=file_id, target_id=chunk_id, type="CONTAINS_CHUNK")
                        current_line = chunk_end_line + 1
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
                for chunk in chunk_nodes:
                    if chunk.start_line <= node_start_line and chunk.end_line >= node_end_line:
                        return chunk
                logger.warning(f"[{file_path}] Could not find containing chunk for node at lines {node_start_line}-{node_end_line}")
                return None

            entity_configs = [
                ("functions", "FunctionDefinition"),
                ("structs", "StructDefinition"),
                ("enums", "EnumDefinition"),
                ("traits", "TraitDefinition"),
                ("impls", "Implementation"),
                ("macros", "MacroDefinition"),
                ("mods", "ModuleDefinition"),
            ]
            chunk_entity_counters = defaultdict(lambda: defaultdict(int))

            for query_name, entity_type_str in entity_configs:
                query = self.queries.get(query_name)
                if not query: continue

                logger.debug(f"[{file_path}] Running query '{query_name}'...")
                for match_id, captures_in_match in query.matches(root_node):
                    definition_node: Optional[TSNODE_TYPE] = None
                    name_node: Optional[TSNODE_TYPE] = None
                    trait_node: Optional[TSNODE_TYPE] = None

                    name_capture_key = "impl_type" if entity_type_str == "Implementation" else "name"

                    for capture_name, node in captures_in_match:
                        if capture_name == "definition": definition_node = node
                        elif capture_name == name_capture_key: name_node = node
                        elif capture_name == "trait_name": trait_node = node

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

                        if entity_type_str == "Implementation" and trait_node:
                            trait_name = get_node_text(trait_node, content_bytes)
                            if trait_name:
                                yield Relationship(source_id=code_entity_id, target_id=trait_name, type="IMPLEMENTS_TRAIT")
                                logger.debug(f"[{file_path}] Yielded IMPLEMENTS_TRAIT: {name} -> {trait_name}")

            import_query = self.queries.get("imports")
            if import_query:
                processed_imports = set()
                logger.debug(f"[{file_path}] Running query 'imports'...")
                for match_id, captures_in_match in import_query.matches(root_node):
                    statement_node: Optional[TSNODE_TYPE] = None
                    target_node: Optional[TSNODE_TYPE] = None
                    target_module_string: Optional[str] = None

                    for capture_name, node in captures_in_match:
                        if capture_name in ["use_statement", "extern_crate"]: statement_node = node
                        elif capture_name == "path": target_node = node
                        elif capture_name == "crate_name": target_node = node

                    if statement_node and target_node:
                        target_module_string = get_node_text(target_node, content_bytes)

                        if target_module_string:
                            start_line = statement_node.start_point[0] + 1
                            import_key = (target_module_string, start_line)

                            if import_key not in processed_imports:
                                yield Relationship(source_id=file_id, target_id=target_module_string, type="IMPORTS")
                                processed_imports.add(import_key)
                                logger.debug(f"[{file_path}] Yielded IMPORTS relationship: {file_id} -> {target_module_string}")
                        else:
                            logger.warning(f"[{file_path}] Could not extract target module string from use/extern statement at line {statement_node.start_point[0]+1}")

        except Exception as e:
            logger.error(f"Failed to parse Rust file {file_path}: {e}", exc_info=True)
