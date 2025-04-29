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

            # --- IMPORTANT: Apply similar logic to ENTITY loops ---
            # The loops for functions, structs, etc., also use captures()
            # They likely need the same adaptation (iterate by 2, check types)

            for query_name, entity_class_name in entity_configs:
                if query_name in self.queries:
                    query = self.queries[query_name]
                    logger.debug(f"Rust Parser: Checking {entity_class_name} for {file_path}")
                    try:
                        captures_iterable = query.captures(root_node)
                        captures_list = list(captures_iterable)
                        logger.debug(f" Rust {query_name} captures list length: {len(captures_list)}")

                        ent_i = 0
                        while ent_i < len(captures_list) - 1:
                            node_candidate = captures_list[ent_i]
                            name_candidate = captures_list[ent_i+1]

                            # Corrected Check: Node followed by string capture name
                            if hasattr(node_candidate, 'type') and isinstance(name_candidate, str):
                                node = node_candidate
                                capture_name = name_candidate
                                logger.debug(f" Processing entity pair: capture_name='{capture_name}', node_type='{node.type}'")


                                if capture_name == "definition": # Found a definition node
                                    # Now find the 'name' capture *within* this definition node's range
                                    # Assume the @name follows @definition immediately in the flat list
                                    name_node: Optional[TSNODE_TYPE] = None
                                    if ent_i + 3 < len(captures_list): # Check if there are enough items for name node/name capture
                                         potential_name_node = captures_list[ent_i + 2]
                                         potential_name_capture = captures_list[ent_i + 3]
                                         if potential_name_capture == 'name' and hasattr(potential_name_node, 'type'):
                                             # Check if the name node is actually a child of the definition node (more robust)
                                             # This check might be complex/slow, skipping for now based on assumption
                                             name_node = potential_name_node
                                             logger.debug(f"  Found potential name node for {entity_class_name} definition.")
                                         else:
                                             logger.debug(f"  Name capture ('{potential_name_capture}') did not follow definition capture ('{capture_name}') as expected.")
                                    else:
                                        logger.debug(f"  Not enough items remaining in captures list to find name node after definition.")


                                    # --- [ Original name extraction and yielding logic ] ---
                                    if name_node:
                                        name = get_node_text(name_node, content_bytes)
                                        entity_text = get_node_text(node, content_bytes) # Use the 'definition' node for full text
                                        start_line = node.start_point[0] + 1
                                        end_line = node.end_point[0] + 1

                                        if name and entity_text:
                                            entity_id_str = f"{file_id}:{entity_class_name}:{name}:{start_line}"
                                            yield CodeEntity(entity_id_str, entity_class_name, name, file_id, entity_text, start_line, end_line)
                                            logger.debug(f"  Yielded Rust Entity: {entity_class_name} - {name}")
                                        else:
                                            logger.warning(f" Could not extract name or text for Rust {entity_class_name} at {file_path}:{start_line}")
                                    else:
                                        logger.warning(f" Could not extract name node for Rust {entity_class_name} definition at {file_path}:{node.start_point[0]+1}")
                                    # --- [ End original logic ] ---

                                ent_i += 2 # Move past the definition node/name pair regardless of finding name
                            else:
                                # If the first item of the pair wasn't 'definition', just move past it
                                ent_i += 2
                        else:
                            logger.warning(f"Skipping unexpected entity item structure at index {ent_i}: item={node_candidate}, next_item={name_candidate}")
                            ent_i += 1 # Move one step forward, hoping the next item aligns
                    except Exception as entity_err:
                         logger.error(f"Error processing entities for query '{query_name}': {entity_err}", exc_info=True)
            # --- END ENTITY LOOP MODIFICATION ---

            # 3. Yield Dependencies (use, extern crate)
            if "imports" in self.queries:
                import_query = self.queries["imports"]
                processed_statement_starts = set() # Track start lines of processed statements
                logger.debug(f"Rust Parser: Checking Dependencies for {file_path}")

            try:
                captures_iterable = import_query.captures(root_node)
                logger.debug(f"Rust import captures type: {type(captures_iterable)}")

                # --- MODIFIED: Iterate assuming alternating node/name structure ---
                captures_list = list(captures_iterable) # Convert to list first for easier indexing
                logger.debug(f"Rust captures list length: {len(captures_list)}")

                i = 0
                while i < len(captures_list) - 1: # Need at least two items (node, name)
                    node_candidate = captures_list[i]
                    name_candidate = captures_list[i+1]

                    # Check if the types seem right (Node followed by str)
                    # Corrected Check: Node followed by string capture name
                    if hasattr(node_candidate, 'type') and isinstance(name_candidate, str):
                        node = node_candidate
                        capture_name = name_candidate
                        logger.debug(f" Processing pair: capture_name='{capture_name}', node_type='{node.type}'")

                        # --- Now the original logic to check capture_name and process ---
                        statement_node: Optional[TSNODE_TYPE] = None
                        # ... (rest of the logic: finding statement_node, target, yielding) ...
                        # Identify the statement node based on the capture name from the query
                        if capture_name == "use_statement":
                           if node.type == "use_declaration": statement_node = node
                        elif capture_name == "extern_crate":
                           if node.type == "extern_crate_declaration": statement_node = node
                        # If it's not a capture name we use to identify the *statement*, skip pair
                        else:
                            logger.debug(f"  Skipping pair starting with non-statement capture '{capture_name}'")
                            i += 2 # Move past this pair
                            continue

                        if not statement_node:
                            logger.debug(f"  Capture '{capture_name}' did not yield expected statement node.")
                            i += 2 # Move past this pair
                            continue

                        # --- [Original dependency processing logic here] ---
                        statement_start_line = statement_node.start_point[0]
                        if statement_start_line in processed_statement_starts:
                            logger.debug(f"  Skipping already processed statement at line {statement_start_line+1}")
                            i += 2 # Move past this pair
                            continue
                        processed_statement_starts.add(statement_start_line)

                        # Find Target Text... yield Dependency... etc.
                        target_node: Optional[TSNODE_TYPE] = None
                        target_text: Optional[str] = None
                        # (Find target logic...)
                        if statement_node.type == "use_declaration":
                            arg_node = statement_node.child_by_field_name("argument")
                            if arg_node: target_node = arg_node; target_text = get_node_text(target_node, content_bytes)
                        elif statement_node.type == "extern_crate_declaration":
                            name_node = statement_node.child_by_field_name("name")
                            if name_node: target_node = name_node; target_text = get_node_text(target_node, content_bytes)

                        if target_text and statement_node:
                            start_line = statement_node.start_point[0] + 1; end_line = statement_node.end_point[0] + 1
                            snippet = get_node_text(statement_node, content_bytes)
                            if snippet:
                                dep_id_str = f"{file_id}:dep:{target_text}:{start_line}"
                                yield Dependency(dep_id_str, file_id, target_text, snippet, start_line, end_line)
                                logger.debug(f"  Yielded Rust Dependency: {target_text}")
                            else: logger.warning(f"  Could not extract snippet for Rust import/use target '{target_text}'")
                        else: logger.warning(f"  Could not determine Rust import/use target or statement node")
                        # --- [End of original dependency processing logic] ---

                        i += 2 # Move past the processed pair
                    else:
                        logger.warning(f"Skipping unexpected item structure at index {i}: item={node_candidate}, next_item={name_candidate}")
                        i += 1 # Move one step forward, hoping the next item aligns

                # --- END MODIFIED ---

            except Exception as e_outer:
                logger.error(f"Error setting up or iterating Rust import captures: {e_outer}", exc_info=True)


        except Exception as e:
            logger.error(f"Failed to parse Rust file {file_path}: {e}", exc_info=True)
