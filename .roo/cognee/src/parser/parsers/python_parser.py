# src/parser/parsers/python_parser.py
from typing import AsyncGenerator, Optional
from .base_parser import BaseParser
from ..entities import DataPoint, TextChunk, CodeEntity, Dependency
from ..chunking import basic_chunker
from ..utils import read_file_content, get_node_text, logger, TSNODE_TYPE
from .treesitter_setup import get_parser, get_language

# Define Tree-sitter queries for Python
# These capture function/class definitions and imports
PYTHON_QUERIES = {
    "imports": """
        [
            (import_statement) @import_statement ;; Capture the whole import statement
            (import_from_statement) @import_statement ;; Capture the whole import from statement
        ]
        """,
    "functions": """
        (function_definition
            name: (identifier) @name
            parameters: (parameters)? @params
            body: (block)? @body
        ) @definition
        """,
    "classes": """
        (class_definition
            name: (identifier) @name) @definition
        """,
    # Could add queries for decorators, variables, etc. if needed
}

class PythonParser(BaseParser):
    """
    Parses Python files (.py) using Tree-sitter to extract code entities and dependencies.

    This parser identifies functions, classes, and import statements within Python
    source code. It also utilizes the `basic_chunker` to break down the file
    content into text segments.

    Inherits from BaseParser.
    """

    def __init__(self):
        """Initializes the PythonParser and loads the Tree-sitter language and queries."""
        super().__init__()
        self.language = get_language("python")
        self.parser = get_parser("python")
        self.queries = {}
        if self.language:
            try:
                self.queries = {
                    name: self.language.query(query_str)
                    for name, query_str in PYTHON_QUERIES.items()
                }
            except Exception as e:
                 logger.error(f"Failed to compile Python queries: {e}", exc_info=True)
        else:
            logger.error("Python tree-sitter language not loaded. Python parsing will be limited.")

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[DataPoint, None]:
        """
        Parses a Python file, yielding TextChunks, CodeEntities (functions, classes),
        and Dependencies (imports).

        Reads the file content, uses Tree-sitter to build an AST, and queries the
        AST to extract relevant code structures and dependencies. It also generates
        text chunks from the file content.

        Args:
            file_path: The absolute path to the Python file to be parsed.
            file_id: The unique ID of the SourceFile entity corresponding to this file.

        Yields:
            DataPoint objects: TextChunk, CodeEntity (FunctionDefinition, ClassDefinition),
            and Dependency entities extracted from the file.
        """
        if not self.parser or not self.language or not self.queries:
            logger.error(f"Python parser not available or queries failed compilation, skipping parsing for {file_path}")
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

            logger.debug(f"Python Parser: Checking Code Entities for {file_path}")
            # 2. Yield Code Entities (Functions, Classes)
            for entity_type, query_name, entity_class_name in [
                ("functions", "functions", "FunctionDefinition"),
                ("classes", "classes", "ClassDefinition"),
            ]:
                if query_name in self.queries:
                    query = self.queries[query_name]
                    logger.debug(f"Executing Python query '{query_name}'...")
                    for capture in query.captures(root_node):
                        node_type = capture[1]
                        node = capture[0]

                        if node_type == "definition":
                            name_node: Optional[TSNODE_TYPE] = None
                            # Find the @name capture within the definition node
                            for child_capture in query.captures(node):
                                if child_capture[1] == "name":
                                    name_node = child_capture[0]
                                    break

                            if name_node:
                                name = get_node_text(name_node, content_bytes)
                                entity_text = get_node_text(node, content_bytes)
                                start_line = node.start_point[0] + 1 # 1-based
                                end_line = node.end_point[0] + 1

                                params_node: Optional[TSNODE_TYPE] = None
                                body_node: Optional[TSNODE_TYPE] = None
                                for child_capture in query.captures(node):
                                    if child_capture[1] == "params":
                                        params_node = child_capture[0]
                                    elif child_capture[1] == "body":
                                        body_node = child_capture[0]

                                parameters = get_node_text(params_node, content_bytes) if params_node else ""
                                body = get_node_text(body_node, content_bytes) if body_node else ""

                                if name and entity_text:
                                    entity_id_str = f"{file_id}:{name}:{start_line}"
                                    logger.debug(f"Yielding Python CodeEntity: {entity_class_name} - {name}")
                                    yield CodeEntity(entity_id_str, entity_class_name, name, file_id, entity_text, start_line, end_line)
                                else:
                                     logger.warning(f"Could not extract name or text for {entity_type} at {file_path}:{start_line}")

            # 3. Yield Dependencies (Imports)
            if "imports" in self.queries:
                logger.debug("Executing Python query 'imports'...")
                import_query = self.queries["imports"]
                processed_imports = set()
                for capture in import_query.captures(root_node):
                    node_type = capture[1]
                    node = capture[0]

                    if node_type == "import_statement":
                        target = "unknown_import"
                        # Find specific @import or @import_from captures
                        import_target_node = None
                        import_from_node = None
                        alias_node: Optional[TSNODE_TYPE] = None # Capture alias
                        for child_capture in import_query.captures(node):
                            if child_capture[1] == "import":
                                import_target_node = child_capture[0]
                            elif child_capture[1] == "import_from":
                                import_from_node = child_capture[0]
                            elif child_capture[1] == "alias":
                                alias_node = child_capture[0]

                        if import_target_node:
                            target_name = get_node_text(import_target_node, content_bytes)
                            if alias_node:
                                target = get_node_text(alias_node, content_bytes)
                            elif import_from_node:
                                from_module = get_node_text(import_from_node, content_bytes)
                                target = f"{from_module}.{target_name}" if from_module else target_name
                            else:
                                target = target_name
                        elif import_from_node:  # Handle 'from x import *' or cases where only module is captured
                            target = get_node_text(import_from_node, content_bytes)

                        snippet = get_node_text(node, content_bytes)
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1

                        import_key = (target, start_line)
                        if target and snippet and import_key not in processed_imports:
                            dep_id_str = f"{file_id}:dep:{target}:{start_line}"
                            logger.debug(f"Yielding Python Dependency: {target}")
                            yield Dependency(dep_id_str, file_id, target, snippet, start_line, end_line)
                            processed_imports.add(import_key)
                        elif not target:
                             logger.warning(f"Could not determine Python import target at {file_path}:{start_line}")


        except Exception as e:
            logger.error(f"Failed to parse Python file {file_path}: {e}", exc_info=True)
