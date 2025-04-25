# src/parser/parsers/cpp_parser.py
from typing import AsyncGenerator, Optional
from .base_parser import BaseParser
from ..entities import DataPoint, TextChunk, CodeEntity, Dependency
from ..chunking import basic_chunker
from ..utils import read_file_content, get_node_text, logger, TSNODE_TYPE
from .treesitter_setup import get_parser, get_language

# Define Tree-sitter queries for C++
# Extends C queries, adds classes, namespaces, templates (simplified)
CPP_QUERIES = {
    "includes": """
        (preproc_include path: [(string_literal) (system_lib_string)] @include) @include_statement
        """,
    "functions": """
        [
          (function_definition
            declarator: (function_declarator declarator: [(identifier) (qualified_identifier) (operator_name) (destructor_name)] @name)) @definition
          (template_declaration (function_definition declarator: (function_declarator declarator: (identifier) @name))) @definition ;; Basic template function
        ]
        """,
    "classes": """
        (class_specifier name: [(type_identifier) (identifier)] @name) @definition
        """,
    "structs": """
        (struct_specifier name: [(type_identifier) (identifier)] @name) @definition
        """,
    "namespaces": """
        (namespace_definition name: [(identifier) (nested_namespace_specifier)] @name) @definition
        """,
    "enums": """
        [(enum_specifier name: (type_identifier) @name) @definition
         (enum_specifier class name: (type_identifier) @name) @definition ;; enum class
        ]
        """,
    "typedefs": """
        (type_definition type: (_) declarator: (type_identifier) @name) @definition
        """,
    "using": """
        (using_declaration) @using_statement ;; using namespace std; using std::vector;
        """,
    # Could add templates, concepts, etc.
}

class CppParser(BaseParser):
    """
    Parses C++ files (.cpp, .hpp) using Tree-sitter to extract code entities and dependencies.

    This parser identifies functions, classes, structs, namespaces, enums,
    typedefs, include directives, and using declarations within C++ source code.
    It also utilizes the `basic_chunker` to break down the file content into
    text segments. Handles basic C++ syntax including namespaces and simple templates.

    Inherits from BaseParser.
    """

    def __init__(self):
        """Initializes the CppParser and loads the Tree-sitter language and queries."""
        super().__init__()
        self.language = get_language("cpp")
        self.parser = get_parser("cpp")
        self.queries = {}
        if self.language:
            try:
                self.queries = {
                    name: self.language.query(query_str)
                    for name, query_str in CPP_QUERIES.items()
                }
            except Exception as e:
                 logger.error(f"Failed to compile C++ queries: {e}", exc_info=True)
        else:
            logger.error("C++ tree-sitter language not loaded. C++ parsing will be limited.")

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[DataPoint, None]:
        """
        Parses a C++ file, yielding TextChunks, CodeEntities (functions, classes,
        structs, namespaces, enums, typedefs), and Dependencies (includes, using).

        Reads the file content, uses Tree-sitter to build an AST, and queries the
        AST to extract relevant code structures and dependencies. It also generates
        text chunks from the file content.

        Args:
            file_path: The absolute path to the C++ file to be parsed.
            file_id: The unique ID of the SourceFile entity corresponding to this file.

        Yields:
            DataPoint objects: TextChunk, CodeEntity (FunctionDefinition, ClassDefinition,
            StructDefinition, NamespaceDefinition, EnumDefinition, TypeDefinition), and
            Dependency entities extracted from the file.
        """
        if not self.parser or not self.language or not self.queries:
            logger.error(f"C++ parser not available or queries failed compilation, skipping parsing for {file_path}")
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
                yield TextChunk(chunk_id_str=chunk_id_str, parent_id=file_id, text=chunk_text, chunk_index=i)

            # 2. Yield Code Entities
            entity_configs = [
                ("functions", "FunctionDefinition"),
                ("classes", "ClassDefinition"),
                ("structs", "StructDefinition"),
                ("namespaces", "NamespaceDefinition"),
                ("enums", "EnumDefinition"),
                ("typedefs", "TypeDefinition"),
            ]

            for query_name, entity_class_name in entity_configs:
                if query_name in self.queries:
                    query = self.queries[query_name]
                    for capture in query.captures(root_node):
                        node_type = capture[1]
                        node = capture[0]

                        if node_type == "definition":
                            name_node: Optional[TSNODE_TYPE] = None
                            for child_capture in query.captures(node):
                                if child_capture[1] == "name":
                                    name_node = child_capture[0]
                                    break

                            if name_node:
                                name = get_node_text(name_node, content_bytes)
                                # Handle qualified names (e.g., Namespace::Class)
                                if name and '::' in name:
                                    name = name.split('::')[-1] # Take the last part as the simple name

                                entity_text = get_node_text(node, content_bytes)
                                start_line = node.start_point[0] + 1
                                end_line = node.end_point[0] + 1

                                if name and entity_text:
                                    entity_id_str = f"{file_id}:{name}:{start_line}"
                                    yield CodeEntity(entity_id_str, entity_class_name, name, file_id, entity_text, start_line, end_line)
                                else:
                                     logger.warning(f"Could not extract name or text for C++ {entity_class_name} at {file_path}:{start_line}")

            # 3. Yield Dependencies (Includes, Using)
            # Includes
            if "includes" in self.queries:
                include_query = self.queries["includes"]
                processed_includes = set()
                for capture in include_query.captures(root_node):
                    node_type = capture[1]
                    node = capture[0]

                    if node_type == "include_statement":
                        target_node: Optional[TSNODE_TYPE] = None
                        for child_capture in include_query.captures(node):
                             if child_capture[1] == "include":
                                 target_node = child_capture[0]
                                 break

                        if target_node:
                            target = get_node_text(target_node, content_bytes)
                            if target and target.startswith(('"', '<')):
                                target = target[1:-1]

                            snippet = get_node_text(node, content_bytes)
                            start_line = node.start_point[0] + 1
                            end_line = node.end_point[0] + 1

                            include_key = (target, start_line)
                            if target and snippet and include_key not in processed_includes:
                                dep_id_str = f"{file_id}:dep:{target}:{start_line}"
                                # Using Dependency entity, could create specific Include entity
                                yield Dependency(dep_id_str, file_id, target, snippet, start_line, end_line)
                                processed_includes.add(include_key)
                            elif not target:
                                 logger.warning(f"Could not determine C++ include target at {file_path}:{start_line}")

            # Using statements (Simplified: just capture the line)
            if "using" in self.queries:
                 using_query = self.queries["using"]
                 processed_usings = set()
                 for capture in using_query.captures(root_node):
                     node_type = capture[1]
                     node = capture[0]
                     if node_type == "using_statement":
                         snippet = get_node_text(node, content_bytes)
                         start_line = node.start_point[0] + 1
                         end_line = node.end_point[0] + 1
                         # Target extraction is complex, using snippet as proxy target for now
                         target = snippet.replace("using ", "").replace("namespace ", "").split(';')[0].strip()
                         using_key = (target, start_line)
                         if target and snippet and using_key not in processed_usings:
                              dep_id_str = f"{file_id}:dep:{target}:{start_line}"
                              yield Dependency(dep_id_str, file_id, target, snippet, start_line, end_line)
                              processed_usings.add(using_key)


        except Exception as e:
            logger.error(f"Failed to parse C++ file {file_path}: {e}", exc_info=True)
