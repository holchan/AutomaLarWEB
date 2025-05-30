# src/parser/parsers/cpp_parser.py
from pydantic import BaseModel
from typing import AsyncGenerator, Optional, List, Dict, Any, Literal
from collections import defaultdict

from .base_parser import BaseParser
from ..entities import TextChunk, CodeEntity, Relationship, ParserOutput
from ..chunking import basic_chunker
from ..utils import read_file_content, get_node_text, logger, TSNODE_TYPE
from .treesitter_setup import get_parser, get_language

CPP_QUERIES_DEBUG = {
    "namespace_def_field_test": """
        (namespace_definition
          [(namespace_identifier) (nested_namespace_specifier)] @name_content
        )
        """,
    "namespace_alias_field_test": """
        (namespace_alias_definition
          (namespace_identifier) @alias_name
          name: [(namespace_identifier) (nested_namespace_specifier)] @target_name_node_content
        )
        """,
}

CPP_QUERIES = {
    "includes": """
        (preproc_include path: [(string_literal) (system_lib_string)] @include) @include_statement
        """,
    "function_definitions": """
        [
          (function_definition
            declarator: [
                (function_declarator declarator: (identifier) @name)
                (function_declarator declarator: (type_identifier) @name)
                (function_declarator declarator: (destructor_name) @name)
                (function_declarator declarator: (field_identifier) @name)
                (function_declarator declarator: (qualified_identifier) @name)
                (function_declarator declarator: (operator_name) @name)
            ]
            body: (compound_statement)
          ) @definition

          (function_definition
            declarator: [
                (function_declarator declarator: (identifier) @name)
                (function_declarator declarator: (type_identifier) @name)
                (function_declarator declarator: (destructor_name) @name)
                (function_declarator declarator: (field_identifier) @name)
                (function_declarator declarator: (qualified_identifier) @name)
                (function_declarator declarator: (operator_name) @name)
            ]
            (default_method_clause)
          ) @definition

          (function_definition
            declarator: [
                (function_declarator declarator: (identifier) @name)
                (function_declarator declarator: (type_identifier) @name)
                (function_declarator declarator: (destructor_name) @name)
                (function_declarator declarator: (field_identifier) @name)
                (function_declarator declarator: (qualified_identifier) @name)
                (function_declarator declarator: (operator_name) @name)
            ]
            (delete_method_clause)
          ) @definition
        ]
        """,
    "function_declarations": """
        [
          (declaration
            type: (_)
            declarator: (function_declarator
                declarator: (identifier) @name
                parameters: (parameter_list)
            )
          ) @definition

          (field_declaration
            type: (_)?
            declarator: [
                (function_declarator
                    declarator: [
                        (identifier) @name
                        (field_identifier) @name
                        (type_identifier) @name
                    ]
                )
                (destructor_name) @name
            ]
          ) @definition

          (declaration
            (storage_class_specifier)
            type: (_)
            declarator: (function_declarator
                declarator: (identifier) @name
                parameters: (parameter_list)
            )
          ) @definition
        ]
        """,
    "template_function_definitions": """
        [
          (template_declaration
              parameters: (template_parameter_list)
              (function_definition
                  declarator: [
                      (function_declarator declarator: (identifier) @name)
                      (function_declarator declarator: (field_identifier) @name)
                      (function_declarator declarator: (qualified_identifier) @name)
                      (function_declarator declarator: (operator_name) @name)
                      (function_declarator declarator: (type_identifier) @name)
                  ]
                  body: (compound_statement)
              )
          ) @definition

          (template_declaration
              parameters: (template_parameter_list)
              (function_definition
                  declarator: [
                      (function_declarator declarator: (identifier) @name)
                      (function_declarator declarator: (type_identifier) @name)
                      (function_declarator declarator: (destructor_name) @name)
                      (function_declarator declarator: (field_identifier) @name)
                      (function_declarator declarator: (qualified_identifier) @name)
                      (function_declarator declarator: (operator_name) @name)
                  ]
                  (default_method_clause)
              )
          ) @definition

          (template_declaration
              parameters: (template_parameter_list)
              (function_definition
                  declarator: [
                      (function_declarator declarator: (identifier) @name)
                      (function_declarator declarator: (type_identifier) @name)
                      (function_declarator declarator: (destructor_name) @name)
                      (function_declarator declarator: (field_identifier) @name)
                      (function_declarator declarator: (qualified_identifier) @name)
                      (function_declarator declarator: (operator_name) @name)
                  ]
                  (delete_method_clause)
              )
          ) @definition
        ]
        """,
    "template_function_declarations": """
        (template_declaration
            parameters: (template_parameter_list)
            (declaration
                declarator: (function_declarator
                    declarator: (identifier) @name
                    parameters: (parameter_list)
                )
            )
        ) @definition
        """,
    "classes": """
        (class_specifier
          name: (type_identifier) @name
          (base_class_clause)? @heritage
          body: (field_declaration_list)
        ) @definition
        """,
    "structs": """
        (struct_specifier
          name: (type_identifier) @name
          (base_class_clause)? @heritage
          body: (field_declaration_list)
        ) @definition
        """,
    "namespaces": """
        [
          (namespace_definition (namespace_identifier) @name) @definition
          (namespace_definition (nested_namespace_specifier) @name) @definition
        ]
        """,
    "enums": """
        [
          (enum_specifier name: (type_identifier) @name body: (enumerator_list)?) @definition
          (enum_specifier "class" name: (type_identifier) @name type: (type_identifier)? body: (enumerator_list)?) @definition
        ]
        """,
    "typedefs": """
        (type_definition declarator: [(type_identifier)(identifier)] @name) @definition
        """,
    "using_namespace": """
        (using_declaration "namespace" [ (identifier) (nested_namespace_specifier) ] @name) @using_statement
        """,
    "using_alias": """
        (alias_declaration name: (type_identifier) @name) @using_statement
        """,
    "namespace_aliases": """
        (namespace_alias_definition
          (namespace_identifier) @alias_new_name
          name: [ (namespace_identifier) (nested_namespace_specifier) ] @alias_target_name
        ) @definition
        """,
    "heritage_details": """
        (type_identifier) @extends_name
        """
}

class CppParser(BaseParser):
    def __init__(self):
        super().__init__()
        print("DEBUG: CppParser __init__ started.")
        self.language = get_language("cpp")
        print(f"DEBUG: CppParser language object: {self.language}")
        self.parser = get_parser("cpp")
        print(f"DEBUG: CppParser parser object: {self.parser}")
        self.queries: Dict[str, Any] = {}

        if self.language:
            logger.info("CppParser: Compiling C++ Tree-sitter queries...")
            print("DEBUG: CppParser: Entering query compilation loop.")

            all_queries_to_compile = {**CPP_QUERIES, **CPP_QUERIES_DEBUG}

            successful_queries_count = 0
            failed_query_names_with_errors: Dict[str, str] = {}

            for name, query_str in all_queries_to_compile.items():
                print(f"DEBUG: CppParser: Attempting to compile query '{name}'...", flush=True)
                try:
                    query_obj = self.language.query(query_str)
                    self.queries[name] = query_obj
                    successful_queries_count += 1
                    logger.info(f"CppParser: Successfully compiled C++ query: '{name}' -> {query_obj}")
                    print(f"DEBUG: CppParser: Successfully compiled C++ query: '{name}'", flush=True)
                except Exception as e:
                    error_type_name = type(e).__name__
                    error_msg = f"{error_type_name}: {e}"
                    logger.error(f"CppParser: FAILED to compile C++ query '{name}'. Error: {error_msg}. Query:\n{query_str}", exc_info=True, extra={"exception_message": str(e), "traceback": True})
                    print(f"DEBUG: CppParser: FAILED query '{name}'. Error: {error_msg}", flush=True)
                    failed_query_names_with_errors[name] = error_msg

            if successful_queries_count == len(all_queries_to_compile):
                logger.info(f"CppParser: All {len(all_queries_to_compile)} C++ queries compiled successfully.")
            else:
                logger.warning(f"CppParser: Successfully compiled {successful_queries_count}/{len(all_queries_to_compile)} C++ queries.")
                if failed_query_names_with_errors:
                    logger.warning(f"CppParser: Failed to compile the following queries: {failed_query_names_with_errors}")
        else:
            logger.error("CppParser: C++ tree-sitter language not loaded. Queries not compiled.")
        print("DEBUG: CppParser __init__ finished.")

    def _extract_list_details(self, query: Any, node: TSNODE_TYPE, capture_name: str, content_bytes: bytes) -> List[str]:
        details = []
        if not query or not node: return details
        try:
            for capture_obj, _ in query.captures(node):
                if capture_obj.name == capture_name:
                    text = get_node_text(capture_obj.node, content_bytes)
                    if text:
                        details.append(text)
        except Exception as e:
            logger.error(f"Error in _extract_list_details for capture '{capture_name}': {e}. Node type: {node.type if node else 'None'}", exc_info=True)
        return details

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[ParserOutput, None]:
        print(f"DEBUG PARSER ({file_path}): Entering parse method.")

        standard_queries_expected = set(CPP_QUERIES.keys())
        missing_standard_queries = standard_queries_expected - set(self.queries.keys())

        prerequisites_met = (
            self.parser and
            self.language and
            self.queries and
            not missing_standard_queries
        )
        if not prerequisites_met:
            error_msg_parts = ["C++ parser prerequisites failed."]
            if not self.parser: error_msg_parts.append("Parser not loaded")
            if not self.language: error_msg_parts.append("Language not loaded")
            if missing_standard_queries:
                error_msg_parts.append(f"Missing standard compiled queries: {missing_standard_queries}")

            all_expected_queries = set(CPP_QUERIES.keys()) | set(CPP_QUERIES_DEBUG.keys())
            all_missing_compiled_queries = all_expected_queries - set(self.queries.keys())
            if all_missing_compiled_queries:
                 logger.debug(f"[{file_path}] Full list of uncompiled queries (incl. debug queries if attempted): {all_missing_compiled_queries}")

            full_error_msg = f"For {file_path}: {'. '.join(error_msg_parts)}. SKIPPING detailed parsing."
            logger.error(full_error_msg)
            print(f"DEBUG PARSER ({file_path}): Prerequisites failed, {'. '.join(error_msg_parts)}")
            return

        content = await read_file_content(file_path)
        if content is None: return
        if not content.strip() and file_path.endswith((".cpp", ".hpp")): return

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
                chunk_id_val = f"{file_id}:{i}"
                chunk_node_val = TextChunk(id=chunk_id_val, start_line=chunk_start_line, end_line=chunk_end_line, chunk_content=chunk_text)
                yield chunk_node_val
                chunk_nodes.append(chunk_node_val)
                yield Relationship(source_id=file_id, target_id=chunk_id_val, type="CONTAINS_CHUNK")
                current_line = chunk_end_line + 1
            if chunk_nodes:
                logger.debug(f"[{file_path}] Yielded {len(chunk_nodes)} TextChunk nodes.")

            def find_chunk_for_node(node_param: TSNODE_TYPE) -> Optional[TextChunk]:
                node_start_line = node_param.start_point[0] + 1
                node_end_line = node_param.end_point[0] + 1
                best_chunk = None; min_diff = float('inf')
                for chunk_item in chunk_nodes:
                    if chunk_item.start_line <= node_start_line and chunk_item.end_line >= node_end_line:
                        diff = node_start_line - chunk_item.start_line
                        if diff < min_diff: min_diff = diff; best_chunk = chunk_item
                        elif diff == min_diff and best_chunk and (chunk_item.end_line - chunk_item.start_line) < (best_chunk.end_line - best_chunk.start_line): best_chunk = chunk_item
                if best_chunk: return best_chunk
                logger.warning(f"[{file_path}] Could not find containing chunk for node {node_param.type if node_param else 'None'} lines {node_start_line}-{node_end_line}")
                return None

            entity_configs = [
                ("function_definitions", "FunctionDefinition"),
                ("function_declarations", "FunctionDeclaration"),
                ("template_function_definitions", "FunctionDefinition"),
                ("template_function_declarations", "FunctionDeclaration"),
                ("classes", "ClassDefinition"),
                ("structs", "StructDefinition"),
                ("namespaces", "NamespaceDefinition"),
                ("enums", "EnumDefinition"),
                ("typedefs", "TypeDefinition"),
                ("namespace_aliases", "NamespaceAliasDefinition"),
            ]
            chunk_entity_counters = defaultdict(lambda: defaultdict(int))
            heritage_detail_query = self.queries.get("heritage_details")

            processed_node_starts = set()

            for query_name, entity_type_str_from_config in entity_configs:
                query = self.queries.get(query_name)
                if not query:
                    logger.info(f"[{file_path}] Standard query '{query_name}' is not compiled. Skipping this entity type.")
                    continue

                logger.debug(f"[{file_path}] Running query '{query_name}' (for entity type base: {entity_type_str_from_config})...")

                for match_id, captures_in_match_dict in query.matches(root_node):
                    outer_snippet_node: Optional[TSNODE_TYPE] = None
                    entity_node_for_processing: Optional[TSNODE_TYPE] = None
                    name_node: Optional[TSNODE_TYPE] = None
                    heritage_node: Optional[TSNODE_TYPE] = None
                    alias_new_name_node: Optional[TSNODE_TYPE] = None

                    actual_entity_type = entity_type_str_from_config

                    if not isinstance(captures_in_match_dict, dict):
                        logger.warning(f"Unexpected captures_in_match type: {type(captures_in_match_dict)} for query {query_name}. Match data: {captures_in_match_dict}. Skipping this match.")
                        continue

                    outer_snippet_node = captures_in_match_dict.get("definition", [None])[0]
                    entity_node_for_processing = outer_snippet_node

                    name_node = captures_in_match_dict.get("name", [None])[0]

                    if query_name == "template_function_definitions":
                        inner_func_def_node = None
                        if outer_snippet_node:
                            for i in range(outer_snippet_node.child_count):
                                child = outer_snippet_node.child(i)
                                if child and child.type == "function_definition":
                                    inner_func_def_node = child
                                    break
                        if inner_func_def_node:
                            entity_node_for_processing = inner_func_def_node
                        else:
                            logger.warning(f"Template def query '{query_name}' could not find inner function_definition for {outer_snippet_node.sexp()[:100] if outer_snippet_node else 'N/A'}.")
                            continue

                    elif query_name == "template_function_declarations":
                        inner_decl_node = None
                        if outer_snippet_node:
                            for i in range(outer_snippet_node.child_count):
                                child = outer_snippet_node.child(i)
                                if child and child.type == "declaration":
                                    decl_sub_node = child.child_by_field_name('declarator')
                                    if decl_sub_node and decl_sub_node.type == 'function_declarator':
                                        inner_decl_node = child
                                        break
                        if inner_decl_node:
                            entity_node_for_processing = inner_decl_node
                        else:
                            logger.warning(f"Template decl query '{query_name}' could not find inner declaration for {outer_snippet_node.sexp()[:100] if outer_snippet_node else 'N/A'}.")
                            continue

                    if not entity_node_for_processing:
                        if query_name not in ["includes", "using_namespace", "using_alias"]:
                             logger.warning(f"Query '{query_name}' matched but no primary entity node. Skipping.")
                        continue

                    if actual_entity_type in ["FunctionDefinition", "FunctionDeclaration"]:
                        if entity_node_for_processing.start_byte in processed_node_starts:
                            continue
                        processed_node_starts.add(entity_node_for_processing.start_byte)


                    if outer_snippet_node:
                        if "heritage" in captures_in_match_dict:
                            heritage_node_list = captures_in_match_dict.get("heritage")
                            if heritage_node_list and outer_snippet_node.type in ["class_specifier", "struct_specifier"] and heritage_node_list[0].parent == outer_snippet_node:
                                heritage_node = heritage_node_list[0]
                        if query_name == "namespace_aliases":
                             alias_new_name_node = captures_in_match_dict.get("alias_new_name", [None])[0]

                    snippet_node_for_display = outer_snippet_node if outer_snippet_node else entity_node_for_processing
                    snippet_content_str: Optional[str] = get_node_text(snippet_node_for_display, content_bytes)

                    current_name_str: Optional[str] = None
                    if actual_entity_type == "NamespaceAliasDefinition":
                        current_name_str = get_node_text(alias_new_name_node, content_bytes) if alias_new_name_node else None
                    elif name_node:
                         current_name_str = get_node_text(name_node, content_bytes)
                    elif actual_entity_type == "NamespaceDefinition" and not name_node:
                        current_name_str = "anonymous"

                    if not current_name_str or not snippet_content_str:
                        logger.debug(f"[{file_path}] Skipping from '{query_name}' name:'{current_name_str}' snippet:{bool(snippet_content_str)} EntityNode: {entity_node_for_processing.type if entity_node_for_processing else 'N/A'}")
                        continue

                    parent_chunk = find_chunk_for_node(snippet_node_for_display)
                    if not parent_chunk: continue
                    chunk_id = parent_chunk.id

                    id_name_part = current_name_str

                    idx = chunk_entity_counters[chunk_id][(actual_entity_type, id_name_part)]
                    chunk_entity_counters[chunk_id][(actual_entity_type, id_name_part)] += 1
                    code_entity_id = f"{chunk_id}:{actual_entity_type}:{id_name_part.replace('::', '_')}:{idx}"

                    yield CodeEntity(id=code_entity_id, type=actual_entity_type, snippet_content=snippet_content_str)
                    yield Relationship(source_id=chunk_id, target_id=code_entity_id, type="CONTAINS_ENTITY")

                    if actual_entity_type in ["ClassDefinition", "StructDefinition"] and heritage_node and heritage_detail_query:
                        logger.debug(f"Processing heritage for {code_entity_id}. Heritage node type: {heritage_node.type} (expected base_class_clause)")
                        if heritage_node.type == "base_class_clause":
                            extends_names = self._extract_list_details(heritage_detail_query, heritage_node, "extends_name", content_bytes)
                            for parent_name_item in extends_names:
                                yield Relationship(source_id=code_entity_id, target_id=parent_name_item, type="EXTENDS")
                                logger.debug(f"[{file_path}] EXTENDS: {current_name_str} -> {parent_name_item}")
                        else:
                            logger.warning(f"Heritage node for {code_entity_id} is type '{heritage_node.type}', but 'base_class_clause' was expected. Skipping EXTENDS.")

            processed_directives = set()

            def get_captures_list_from_match_dict_iter(captures_dict_param: Dict[str, List[TSNODE_TYPE]]):
                res = []
                if isinstance(captures_dict_param, dict):
                    for name_str, node_list_val in captures_dict_param.items():
                        for node_val in node_list_val:
                            res.append((name_str, node_val))
                return res

            include_query = self.queries.get("includes")
            if include_query:
                logger.debug(f"[{file_path}] Running query 'includes'...")
                for _, captures_in_match_dict in include_query.matches(root_node):
                    captures_list = get_captures_list_from_match_dict_iter(captures_in_match_dict)
                    statement_node: Optional[TSNODE_TYPE] = None; target_node: Optional[TSNODE_TYPE] = None
                    for capture_name_str, node_obj in captures_list:
                        if capture_name_str == "include_statement": statement_node = node_obj
                        elif capture_name_str == "include": target_node = node_obj
                    if statement_node and target_node:
                        target_module_string = get_node_text(target_node, content_bytes)
                        if target_module_string and target_module_string.startswith(('"', '<')): target_module_string = target_module_string[1:-1]
                        if target_module_string:
                            start_line = statement_node.start_point[0] + 1
                            import_key = (target_module_string, start_line, "include")
                            if import_key not in processed_directives:
                                yield Relationship(source_id=file_id, target_id=target_module_string, type="IMPORTS")
                                processed_directives.add(import_key); logger.debug(f"[{file_path}] IMPORTS (include): {file_id} -> {target_module_string}")
            else: logger.info(f"[{file_path}] Query 'includes' not available.")

            using_ns_query = self.queries.get("using_namespace")
            if using_ns_query:
                logger.debug(f"[{file_path}] Running query 'using_namespace'...")
                for _, captures_in_match_dict in using_ns_query.matches(root_node):
                    captures_list = get_captures_list_from_match_dict_iter(captures_in_match_dict)
                    statement_node: Optional[TSNODE_TYPE] = None; target_node: Optional[TSNODE_TYPE] = None
                    for capture_name_str, node_obj in captures_list:
                        if capture_name_str == "using_statement": statement_node = node_obj
                        elif capture_name_str == "name": target_node = node_obj
                    if statement_node and target_node:
                        target_namespace = get_node_text(target_node, content_bytes)
                        if target_namespace:
                            start_line = statement_node.start_point[0] + 1
                            using_key = (target_namespace, start_line, "using_namespace")
                            if using_key not in processed_directives:
                                yield Relationship(source_id=file_id, target_id=target_namespace, type="IMPORTS")
                                processed_directives.add(using_key); logger.debug(f"[{file_path}] IMPORTS (using namespace): {file_id} -> {target_namespace}")
            else: logger.info(f"[{file_path}] Query 'using_namespace' not available.")

            using_alias_query = self.queries.get("using_alias")
            if using_alias_query:
                logger.debug(f"[{file_path}] Running query 'using_alias' (type aliases)...")
                for _, captures_in_match_dict in using_alias_query.matches(root_node):
                    captures_list = get_captures_list_from_match_dict_iter(captures_in_match_dict)
                    statement_node: Optional[TSNODE_TYPE] = None; alias_name_node: Optional[TSNODE_TYPE] = None
                    for capture_name_str, node_obj in captures_list:
                        if capture_name_str == "using_statement": statement_node = node_obj
                        elif capture_name_str == "name": alias_name_node = node_obj
                    if statement_node and alias_name_node:
                        alias_name = get_node_text(alias_name_node, content_bytes)
                        if alias_name:
                            start_line = statement_node.start_point[0] + 1
                            alias_key = (alias_name, start_line, "type_alias")
                            if alias_key not in processed_directives:
                                logger.debug(f"[{file_path}] Processed 'using alias' (type alias) for: {alias_name}.")
                                processed_directives.add(alias_key)
            else: logger.info(f"[{file_path}] Query 'using_alias' not available.")

        except Exception as e:
            logger.error(f"Failed during detailed parsing of C++ file {file_path}: {e}", exc_info=True)
