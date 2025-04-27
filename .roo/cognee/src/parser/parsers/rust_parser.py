# src/parser/parsers/rust_parser.py
from pydantic import BaseModel # Import BaseModel for type hinting
from typing import AsyncGenerator, Optional
from .base_parser import BaseParser
from pydantic import BaseModel # Import BaseModel for type hinting
from ..entities import TextChunk, CodeEntity, Dependency # Removed DataPoint import
from ..chunking import basic_chunker
from ..utils import read_file_content, get_node_text, logger, TSNODE_TYPE
from .treesitter_setup import get_parser, get_language

# Define Tree-sitter queries for Rust
RUST_QUERIES = {
    "imports": """
        [
            ;; Capture the full path node within use_declaration's argument
            (use_declaration argument: (_) @path) @use_statement
            (extern_crate_declaration (identifier) @crate_name) @extern_crate ;; extern crate serde;
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
            trait: [(type_identifier) (generic_type)]? ;; Optional trait being implemented
            type: [(type_identifier) (generic_type)] @name ;; The type the impl is for
        ) @definition
        """,
    "macros": """
        [
            (macro_definition name: (identifier) @name) @definition ;; macro_rules! my_macro { ... }
            ;; Capturing macro invocations might be noisy, focus on definitions for now
            ;; (macro_invocation macro: (identifier) @macro_name)
        ]
        """,
    "mods": """
        (mod_item name: (identifier) @name) @definition ;; mod my_module;
        """,
    # Could add consts, statics, type aliases
}

class RustParser(BaseParser):
    """
    Parses Rust files (.rs) using Tree-sitter to extract code entities and dependencies.

    This parser identifies functions, structs, enums, traits, implementation blocks,
    macros, module declarations, and use/extern crate statements within Rust
    source code. It also utilizes the `basic_chunker` to break down the file
    content into text segments.

    Inherits from BaseParser.
    """

    def __init__(self):
        """Initializes the RustParser and loads the Tree-sitter language and queries."""
        super().__init__()
        self.language = get_language("rust")
        self.parser = get_parser("rust")
        self.queries = {}
        if self.language:
            try:
                self.queries = {
                    name: self.language.query(query_str)
                    for name, query_str in RUST_QUERIES.items()
                }
            except Exception as e:
                 logger.error(f"Failed to compile Rust queries: {e}", exc_info=True)
                 self.queries = {} # Ensure queries dict is empty on failure
        else:
            logger.error("Rust tree-sitter language not loaded. Rust parsing will be limited.")

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[BaseModel, None]: # Use BaseModel hint
        """
        Parses a Rust file, yielding TextChunks, CodeEntities (functions, structs,
        enums, traits, impls, mods, macros), and Dependencies (use, extern crate).

        Reads the file content, uses Tree-sitter to build an AST, and queries the
        AST to extract relevant code structures and dependencies. It also generates
        text chunks from the file content.

        Args:
            file_path: The absolute path to the Rust file to be parsed.
            file_id: The unique ID of the SourceFile entity corresponding to this file.

        Yields:
            BaseModel objects: TextChunk, CodeEntity (FunctionDefinition, StructDefinition,
            EnumDefinition, TraitDefinition, Implementation, MacroDefinition, ModuleDefinition),
            and Dependency entities extracted from the file.
        """
        if not self.parser or not self.language or not self.queries:
            logger.error(f"Rust parser not available or queries failed compilation, skipping parsing for {file_path}")
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
                ("structs", "StructDefinition"),
                ("enums", "EnumDefinition"),
                ("traits", "TraitDefinition"),
                ("impls", "Implementation"), # Represents an impl block
                ("macros", "MacroDefinition"),
                ("mods", "ModuleDefinition"),
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
                                entity_text = get_node_text(node, content_bytes)
                                start_line = node.start_point[0] + 1
                                end_line = node.end_point[0] + 1

                                if name and entity_text:
                                    # For impl blocks, the 'name' is the type being implemented
                                    entity_id_str = f"{file_id}:{entity_class_name}:{name}:{start_line}"
                                    yield CodeEntity(entity_id_str, entity_class_name, name, file_id, entity_text, start_line, end_line)
                                else:
                                     logger.warning(f"Could not extract name or text for Rust {entity_class_name} at {file_path}:{start_line}")

            # 3. Yield Dependencies (use, extern crate)
            if "imports" in self.queries:
                import_query = self.queries["imports"]
                processed_statement_starts = set() # Track start lines of processed statements
                logger.debug(f"Rust Parser: Checking Dependencies for {file_path}")

                captures = import_query.captures(root_node)

                # Iterate through captures, focusing on statement nodes
                for node, capture_name in captures:
                    statement_node: Optional[TSNODE_TYPE] = None
                    target_node: Optional[TSNODE_TYPE] = None
                    target_text: Optional[str] = None

                    # Identify the statement node based on the capture name from the query
                    if capture_name == "use_statement":
                        # Ensure the node type matches, although capture name should be reliable
                        if node.type == "use_declaration":
                            statement_node = node
                    elif capture_name == "extern_crate":
                         if node.type == "extern_crate_declaration":
                            statement_node = node
                    else:
                        # This capture is 'path' or 'crate_name', skip processing here
                        # We'll find the target via traversal from the statement node
                        continue

                    # If not a statement node we care about, skip
                    if not statement_node:
                        continue

                    # Check if we've already processed this statement via its start line
                    statement_start_line = statement_node.start_point[0]
                    if statement_start_line in processed_statement_starts:
                        continue
                    processed_statement_starts.add(statement_start_line)

                    # --- Find Target Text using Direct Node Traversal ---
                    if statement_node.type == "use_declaration":
                        # Find the argument node (could be various types like use_list, scoped_use_list, path, etc.)
                        arg_node = statement_node.child_by_field_name("argument")
                        if arg_node:
                            # Simplification: Get text of the whole argument node.
                            # More robust: traverse arg_node to find the core path/identifier.
                            target_node = arg_node # Use the argument node itself for text
                            target_text = get_node_text(target_node, content_bytes)
                            logger.debug(f"Found use target: '{target_text}' via argument node")

                    elif statement_node.type == "extern_crate_declaration":
                        name_node = statement_node.child_by_field_name("name") # Should be 'identifier' type
                        if name_node:
                            target_node = name_node
                            target_text = get_node_text(target_node, content_bytes)
                            logger.debug(f"Found extern crate target: '{target_text}' via name node")

                    # --- Yield Dependency ---
                    if target_text and statement_node:
                        start_line = statement_node.start_point[0] + 1
                        end_line = statement_node.end_point[0] + 1
                        snippet = get_node_text(statement_node, content_bytes)

                        if snippet: # Ensure snippet is not empty
                            dep_id_str = f"{file_id}:dep:{target_text}:{start_line}"
                            logger.debug(f"Yielding Rust Dependency: {dep_id_str} (Target: {target_text}, Snippet: '{snippet[:50]}...')")
                            yield Dependency(dep_id_str, file_id, target_text, snippet, start_line, end_line)
                            # Note: processed_statement_starts handles deduplication
                        else:
                             logger.warning(f"Could not extract snippet for Rust import/use target '{target_text}' at {file_path}:{start_line}")
                    else:
                         logger.warning(f"Could not determine Rust import/use target or statement node at {file_path}:{statement_node.start_point[0] + 1 if statement_node else 'unknown line'}")


        except Exception as e:
            logger.error(f"Failed to parse Rust file {file_path}: {e}", exc_info=True)
