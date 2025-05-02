import re # Import re if needed for fallback parsing
from typing import AsyncGenerator, Optional
from pydantic import BaseModel # Assuming BaseModel is used for type hinting
from tree_sitter import Node as TSNODE_TYPE # Assuming TSNODE_TYPE is Node

from cognee.infrastructure.files.utils.async_read_file import read_file_content
from cognee.modules.code.models.code_chunk import TextChunk
from cognee.modules.code.models.code_dependency import Dependency
from cognee.modules.code.models.code_entity import CodeEntity
from cognee.modules.code.parsers.languages import get_language, get_parser
from cognee.modules.code.parsers.utils.chunking import basic_chunker
from cognee.modules.code.parsers.utils.extraction import get_node_text
from .base_parser import BaseParser
from cognee.root_dir import get_absolute_path
from cognee.config import Config
config = Config()
config.load()

import logging
logger = logging.getLogger(__name__)

# Define Tree-sitter queries for Rust
RUST_QUERIES = {
    "imports": """
        [
            (use_declaration) @use_statement @definition
            (extern_crate_declaration) @extern_crate @definition
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
        (impl_item type: [(type_identifier) (generic_type)] @type) @definition ;; Capture the type being implemented for
        """,
    "macros": """
        (macro_definition name: (identifier) @name) @definition
        """,
    "mods": """
        (mod_item name: (identifier) @name) @definition
        """
}


class RustParser(BaseParser):
    def __init__(self):
        """Initializes the RustParser and loads the Tree-sitter language and queries."""
        super().__init__()
        self.language = get_language("rust")
        self.parser = get_parser("rust")
        self.queries = {}
        if self.language:
            logger.info("Attempting to compile Rust Tree-sitter queries one by one...")
            failed_queries = []
            for name, query_str in RUST_QUERIES.items():
                try:
                    self.queries[name] = self.language.query(query_str)
                    logger.debug(f"Successfully compiled Rust query: {name}")
                except Exception as e:
                    logger.error(f"Failed to compile Rust query '{name}': {e}", exc_info=True)
                    failed_queries.append(name)

            if not failed_queries:
                logger.info("Successfully compiled ALL Rust queries.")
            else:
                logger.error(f"Failed to compile the following Rust queries: {', '.join(failed_queries)}. Rust parsing will be limited.")
                # Decide if clearing queries is necessary based on which failed
                # For now, clear if any fail to ensure consistent behavior if core parsing fails
                self.queries = {}
        else:
            logger.error("Rust tree-sitter language not loaded.")


    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[BaseModel, None]:
        if not self.parser or not self.language or not self.queries:
            logger.error(f"Rust parser not available or queries failed compilation, skipping parsing for {file_path}")
            # Optional: Fallback to chunking only
            # content_fallback = await read_file_content(file_path)
            # if content_fallback:
            #    for i, chunk_text in enumerate(basic_chunker(content_fallback)):
            #        if chunk_text.strip(): yield TextChunk(f"{file_id}:chunk:{i}", file_id, chunk_text, i)
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

            # 2. Yield Code Entities (using matches)
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
                    logger.debug(f"Rust Parser: Checking {entity_class_name} for {file_path}")
                    try:
                         # --- Use query.matches() ---
                         for match_id, captures_in_match in query.matches(root_node):
                             definition_node: Optional[TSNODE_TYPE] = None
                             name_node: Optional[TSNODE_TYPE] = None
                             # Find the definition and name nodes within this specific match
                             for capture_name, node in captures_in_match:
                                 if capture_name == "definition":
                                     definition_node = node
                                 elif capture_name == "name":
                                     name_node = node
                                 # Break early if both found? Optional optimization

                             if definition_node and name_node:
                                 name = get_node_text(name_node, content_bytes)
                                 entity_text = get_node_text(definition_node, content_bytes)
                                 start_line = definition_node.start_point[0] + 1
                                 end_line = definition_node.end_point[0] + 1

                                 if name and entity_text:
                                     entity_id_str = f"{file_id}:{entity_class_name}:{name}:{start_line}"
                                     yield CodeEntity(entity_id_str, entity_class_name, name, file_id, entity_text, start_line, end_line)
                                     logger.debug(f"  Yielded Rust Entity: {entity_class_name} - {name}")
                                 else:
                                     logger.warning(f" Could not extract name or text for Rust {entity_class_name} at {file_path}:{start_line}")
                             elif definition_node and not name_node:
                                 # Handle cases like impl blocks where the @name capture might be the type, not a separate identifier
                                 if entity_class_name == "Implementation":
                                     impl_type_node = None
                                     # Check captures for 'type' instead of 'name' based on the impl query
                                     for cn, n in captures_in_match:
                                         if cn == 'type': # Query uses @type for the impl target
                                             impl_type_node = n
                                             break
                                     if impl_type_node:
                                         name = get_node_text(impl_type_node, content_bytes) # Use type as 'name'
                                         entity_text = get_node_text(definition_node, content_bytes)
                                         start_line = definition_node.start_point[0] + 1
                                         end_line = definition_node.end_point[0] + 1
                                         if name and entity_text:
                                             entity_id_str = f"{file_id}:{entity_class_name}:{name}:{start_line}"
                                             yield CodeEntity(entity_id_str, entity_class_name, name, file_id, entity_text, start_line, end_line)
                                             logger.debug(f"  Yielded Rust Entity: {entity_class_name} - {name} (from impl type)")
                                         else:
                                             logger.warning(f" Could not extract name(type) or text for Rust {entity_class_name} at {file_path}:{start_line}")
                                     else:
                                          logger.warning(f" Could not extract name/type node for Rust {entity_class_name} definition at {file_path}:{definition_node.start_point[0]+1}")
                                 else:
                                    logger.warning(f" Could not extract name node for Rust {entity_class_name} definition at {file_path}:{definition_node.start_point[0]+1}")

                    except Exception as entity_err:
                         logger.error(f"Error processing entities for query '{query_name}' in {file_path}: {entity_err}", exc_info=True)


            # 3. Yield Dependencies (use, extern crate) (using matches)
            if "imports" in self.queries:
                import_query = self.queries["imports"]
                processed_statement_starts = set() # Track start lines to avoid duplicates
                logger.debug(f"Rust Parser: Checking Dependencies for {file_path}")
                try:
                     # --- Use query.matches() ---
                     for match_id, captures_in_match in import_query.matches(root_node):
                         statement_node: Optional[TSNODE_TYPE] = None
                         target_node: Optional[TSNODE_TYPE] = None
                         target_text: Optional[str] = None

                         # Find the statement node and target node within this match
                         for capture_name, node in captures_in_match:
                             # The 'imports' query captures the whole statement as @definition
                             # We need to refine this to get the specific target path/crate
                             if capture_name == "definition": # This is the whole statement node
                                 statement_node = node
                                 # Now, try to find the specific target within this statement's children/captures
                                 if node.type == "use_declaration":
                                     # Look for 'scoped_use_list', 'use_wildcard', 'identifier', 'scoped_identifier' etc.
                                     # This requires knowing the Rust grammar structure well.
                                     # A simpler approach might be to add specific captures to the query.
                                     # Let's add @path to the query for use_declaration
                                     # RUST_QUERIES["imports"] = "[ (use_declaration path: [(_) (scoped_identifier)] @path) @use_statement (extern_crate_declaration name: (identifier) @crate_name) @extern_crate ]"
                                     # Assuming the query is updated like above:
                                     path_node = next((n for cn, n in captures_in_match if cn == "path"), None)
                                     if path_node: target_node = path_node
                                     else: logger.warning(f"Rust 'use' statement found at {file_path}:{node.start_point[0]+1}, but couldn't find @path capture.")

                                 elif node.type == "extern_crate_declaration":
                                     # Assuming query is updated with @crate_name:
                                     crate_name_node = next((n for cn, n in captures_in_match if cn == "crate_name"), None)
                                     if crate_name_node: target_node = crate_name_node
                                     else: logger.warning(f"Rust 'extern crate' statement found at {file_path}:{node.start_point[0]+1}, but couldn't find @crate_name capture.")

                             # --- Fallback/Alternative if query isn't updated ---
                             # This part is less reliable as it assumes structure based on node type only
                             elif capture_name == "use_statement": # If query uses @use_statement
                                 statement_node = node
                                 # Try finding the path node by traversing children (less robust)
                                 # path_node = find_child_node_by_type(node, ["scoped_identifier", "identifier", ...])
                                 # if path_node: target_node = path_node
                             elif capture_name == "extern_crate": # If query uses @extern_crate
                                 statement_node = node
                                 # Try finding the identifier child
                                 # crate_name_node = find_child_node_by_type(node, ["identifier"])
                                 # if crate_name_node: target_node = crate_name_node


                         if not statement_node: continue # Skip if no statement identified

                         start_line = statement_node.start_point[0] + 1
                         if start_line in processed_statement_starts: continue # Skip duplicates

                         if target_node:
                             target_text = get_node_text(target_node, content_bytes)
                         # Fallback: If target_node wasn't found, try extracting from snippet (brittle)
                         elif statement_node:
                             snippet_fallback = get_node_text(statement_node, content_bytes)
                             if snippet_fallback and snippet_fallback.startswith("use"):
                                 match = re.match(r"use\s+((?:[\w:]+::)*[\w*]+|\{.*\});?", snippet_fallback.strip())
                                 if match: target_text = match.group(1)
                             elif snippet_fallback and snippet_fallback.startswith("extern crate"):
                                  match = re.match(r"extern crate\s+(\w+);?", snippet_fallback.strip())
                                  if match: target_text = match.group(1)
                             if not target_text: logger.warning(f"Could not reliably extract target from Rust dependency statement at {file_path}:{start_line}. Snippet: {snippet_fallback}")


                         if target_text and statement_node:
                             end_line = statement_node.end_point[0] + 1
                             snippet = get_node_text(statement_node, content_bytes)
                             if snippet:
                                 dep_id_str = f"{file_id}:dep:{target_text}:{start_line}"
                                 yield Dependency(dep_id_str, file_id, target_text, snippet, start_line, end_line)
                                 logger.debug(f"  Yielded Rust Dependency: {target_text}")
                                 processed_statement_starts.add(start_line)
                             else:
                                 logger.warning(f"  Could not extract snippet for Rust import/use target '{target_text}' at {file_path}:{start_line}")
                         elif statement_node: # Log even if target extraction failed
                             logger.warning(f"  Could not determine Rust import/use target node for statement at {file_path}:{start_line}")

                except Exception as dep_err:
                    logger.error(f"Error processing dependencies for query 'imports' in {file_path}: {dep_err}", exc_info=True)

        except Exception as e:
            logger.error(f"Failed to parse Rust file {file_path}: {e}", exc_info=True)

# Helper function (optional, if needed for fallback)
def find_child_node_by_type(node: TSNODE_TYPE, types: list[str]) -> Optional[TSNODE_TYPE]:
    for child in node.children:
        if child.type in types:
            return child
    return None
