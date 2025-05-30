from typing import AsyncGenerator, Optional, Dict, List, Any
from ..entities import TextChunk, CodeEntity, Relationship, ParserOutput
from ..chunking import basic_chunker
from ..utils import read_file_content, get_node_text, logger, TSNODE_TYPE
from .treesitter_setup import get_parser, get_language
from .base_parser import BaseParser

TYPESCRIPT_QUERIES = {
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
            (function_signature name: (identifier) @name) @definition
            (lexical_declaration (variable_declarator name: (identifier) @name value: [(arrow_function) (function)])) @definition
            (method_definition name: (property_identifier) @name) @definition
            (method_signature name: (property_identifier) @name) @definition
        ]
        """,
    "classes": """
        (class_declaration
            name: [(identifier) (type_identifier)] @name
            heritage: (class_heritage)? @heritage
        ) @definition
        """,
    "interfaces": """
        (interface_declaration
            name: (type_identifier) @name
            heritage: (extends_clause)? @heritage
        ) @definition
        """,
    "types": """
        (type_alias_declaration name: (type_identifier) @name) @definition
        """,
    "enums": """
        (enum_declaration name: (identifier) @name) @definition
        """,
    "heritage_details": """
        [
        (extends_clause value: [(identifier) (type_identifier) (generic_type)] @extends_name)
        (implements_clause type: [(identifier) (type_identifier) (generic_type)] @implements_name)
        ]
    """
}

class TypescriptParser(BaseParser):
    """
    Parses TypeScript/TSX files, yielding TextChunk, CodeEntity (minimal),
    and Relationship objects based on the FINAL entity definitions.
    """
    def __init__(self):
        super().__init__()
        self.language = get_language("typescript")
        self.parser = get_parser("typescript")
        self.queries = {}
        if self.language:
            logger.info("Compiling TypeScript Tree-sitter queries...")
            try:
                for name, query_str in TYPESCRIPT_QUERIES.items():
                    self.queries[name] = self.language.query(query_str)
                logger.info("TypeScript queries compiled successfully.")
            except Exception as e:
                logger.error(f"Failed to compile TypeScript queries: {e}", exc_info=True)
                self.queries = {}
        else:
            logger.error("TypeScript tree-sitter language not loaded.")

    def _extract_list_details(self, query: Any, node: TSNODE_TYPE, capture_name: str, content_bytes: bytes) -> List[str]:
        """Helper to find all instances of a capture within a node."""
        details = []
        if not query or not node: return details
        for child_capture_name, child_node in query.captures(node):
            if child_capture_name == capture_name:
                text = get_node_text(child_node, content_bytes)
                if text:
                    details.append(text)
        return details

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[ParserOutput, None]:
        required_queries = {"imports", "functions", "classes", "interfaces", "types", "enums", "heritage_details"}
        if not self.parser or not self.language or not self.queries or not required_queries.issubset(self.queries.keys()):
            logger.error(f"TypeScript parser prerequisites missing. Skipping detailed parsing for {file_path}")
            content_fallback = await read_file_content(file_path)
            if content_fallback:
                for i, chunk_text in enumerate(basic_chunker(content_fallback)):
                    if chunk_text.strip():
                        start_line = content_fallback.count('\n', 0, content_fallback.find(chunk_text)) + 1 if chunk_text in content_fallback else 1
                        end_line = start_line + chunk_text.count('\n')
                        chunk_id = f"{file_id}:{i}"
                        yield TextChunk(id=chunk_id, chunk_content=chunk_text, start_line=start_line, end_line=end_line)
                        yield Relationship(source_id=file_id, target_id=chunk_id, type="CONTAINS_CHUNK")
            return

        content = await read_file_content(file_path)
        if content is None: return

        try:
            content_bytes = bytes(content, "utf8")
            tree = self.parser.parse(content_bytes)
            root_node = tree.root_node

            chunk_nodes = []
            for i, chunk_text in enumerate(basic_chunker(content)):
                if chunk_text.strip():
                    start_line = content[:content.find(chunk_text)].count('\n') + 1 if content.find(chunk_text) != -1 else 1
                    end_line = start_line + chunk_text.count('\n')
                    chunk_id = f"{file_id}:{i}"
                    chunk_node = TextChunk(id=chunk_id, chunk_content=chunk_text, start_line=start_line, end_line=end_line)
                    chunk_nodes.append(chunk_node)
                    yield chunk_node
                    yield Relationship(source_id=file_id, target_id=chunk_id, type="CONTAINS_CHUNK")

            def find_containing_chunk(entity_start_line: int) -> Optional[TextChunk]:
                best_chunk = None
                for chunk in chunk_nodes:
                    if chunk.start_line <= entity_start_line:
                        if best_chunk is None or chunk.start_line > best_chunk.start_line:
                            if entity_start_line <= chunk.end_line:
                                best_chunk = chunk
                    elif best_chunk is not None:
                        break
                return best_chunk

            entity_configs = [
                ("functions", "FunctionDefinition"),
                ("classes", "ClassDefinition"),
                ("interfaces", "InterfaceDefinition"),
                ("types", "TypeDefinition"),
                ("enums", "EnumDefinition"),
            ]
            entity_counter_in_chunk = {}
            heritage_detail_query = self.queries.get("heritage_details")

            for query_name, entity_type_str in entity_configs:
                if query_name in self.queries:
                    query = self.queries[query_name]
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
                            start_line = definition_node.start_point[0] + 1

                            containing_chunk = find_containing_chunk(start_line)
                            if not containing_chunk:
                                logger.warning(f"No containing chunk for {entity_type_str} '{name}' at line {start_line} in {file_path}")
                                continue

                            chunk_id = containing_chunk.id

                            entity_key = f"{chunk_id}:{entity_type_str}:{name}"
                            entity_index = entity_counter_in_chunk.get(entity_key, 0)
                            entity_counter_in_chunk[entity_key] = entity_index + 1
                            entity_id = f"{chunk_id}:{entity_type_str}:{name}:{entity_index}"

                            yield CodeEntity(
                                id=entity_id,
                                type=entity_type_str,
                                snippet_content=snippet_content,
                            )
                            yield Relationship(source_id=chunk_id, target_id=entity_id, type="CONTAINS_ENTITY")

                            if entity_type_str in ["ClassDefinition", "InterfaceDefinition"] and heritage_node and heritage_detail_query:
                                extends_names = self._extract_list_details(heritage_detail_query, heritage_node, "extends_name", content_bytes)
                                for parent_name in extends_names:
                                    yield Relationship(source_id=entity_id, target_id=parent_name, type="EXTENDS")

                                if entity_type_str == "ClassDefinition":
                                    implements_names = self._extract_list_details(heritage_detail_query, heritage_node, "implements_name", content_bytes)
                                    for interface_name in implements_names:
                                        yield Relationship(source_id=entity_id, target_id=interface_name, type="IMPLEMENTS")

            if "imports" in self.queries:
                import_query = self.queries["imports"]
                processed_imports = set()
                for match_id, captures_in_match in import_query.matches(root_node):
                    statement_node: Optional[TSNODE_TYPE] = None
                    import_from_node: Optional[TSNODE_TYPE] = None
                    target_module: Optional[str] = None
                    for capture_name, node in captures_in_match:
                        if capture_name == "import_statement": statement_node = node
                        elif capture_name == "import_from": import_from_node = node
                    if not statement_node: continue
                    if import_from_node:
                        target_module = get_node_text(import_from_node, content_bytes)
                        if target_module and target_module.startswith(('"', "'")):
                            target_module = target_module[1:-1]
                    else:
                        logger.debug(f"Import statement without explicit source at {file_path}:{statement_node.start_point[0]+1}")
                        continue
                    start_line = statement_node.start_point[0] + 1
                    import_key = (target_module, start_line)

                    if target_module and import_key not in processed_imports:
                        yield Relationship(source_id=file_id, target_id=target_module, type="IMPORTS")
                        processed_imports.add(import_key)

        except Exception as e:
            logger.error(f"Failed to parse TypeScript file {file_path}: {e}", exc_info=True)
