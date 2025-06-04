# src/parser/parsers/cpp_parser.py
from pydantic import BaseModel
from typing import AsyncGenerator, Optional, List, Dict, Any, Literal, Set, Tuple
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

          (function_definition ; For "= default"
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

          (function_definition ; For "= delete"
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

          (field_declaration ; Catches method declarations within classes/structs
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

          (declaration ; Catches 'extern' function declarations
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

          (template_declaration ; For "= default"
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

          (template_declaration ; For "= delete"
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
          body: (field_declaration_list)? ; Optional body means this captures forward decls too
        ) @definition
        """,
    "structs": """
        (struct_specifier
          name: (type_identifier) @name
          (base_class_clause)? @heritage
          body: (field_declaration_list)? ; Optional body means this captures forward decls too
        ) @definition
        """,
    "namespaces": """
        [
          (namespace_definition (namespace_identifier) @name) @definition
          (namespace_definition (nested_namespace_specifier) @name) @definition ; For A::B {}
          (namespace_definition body: (declaration_list)) @definition ; Anonymous namespace
        ]
        """,
    "enums": """
        [
          (enum_specifier name: (type_identifier) @name body: (enumerator_list)?) @definition
          (enum_specifier "class" name: (type_identifier) @name type: (type_identifier)? body: (enumerator_list)?) @definition
        ]
        """,
    "typedefs": """
        [
          (type_definition declarator: [(type_identifier) (identifier)] @name) @definition ; Simple typedefs
          (type_definition declarator: (pointer_declarator declarator: (identifier) @name)) @definition ; Typedef for pointers like int * IntPtr;
          (type_definition declarator: (function_declarator declarator: (identifier) @name)) @definition ; Typedef for func types like void MyFuncType();
          (type_definition declarator: (array_declarator declarator: (identifier) @name)) @definition ; Typedef for array types
          (type_definition  ; For function pointers like typedef void (*FuncPtr)(int);
            declarator: (pointer_declarator
                          declarator: (function_declarator
                                        declarator: (identifier) @name
                                      )
                        )
          ) @definition
        ]
        """,
    "using_namespace": """
        (using_declaration "namespace" [ (identifier) (nested_namespace_specifier) (qualified_identifier) ] @name) @using_statement
        """,
    "using_alias": """ ; For type aliases like 'using MyInt = int;'
        (alias_declaration name: (type_identifier) @name) @using_statement
        """,
    "namespace_aliases": """
        (namespace_alias_definition
          (namespace_identifier) @alias_new_name
          name: [ (namespace_identifier) (nested_namespace_specifier) (qualified_identifier)] @alias_target_name
        ) @definition
        """,
    "heritage_details": """ ; Used to extract names from base_class_clause
        (type_identifier) @heritage_type_identifier
        (qualified_identifier) @heritage_qualified_identifier
        """,
    "deleted_methods_test": """
        (function_definition
            declarator: (_) @declarator_node
            (delete_method_clause) @delete_node
        )
        """
}

ALL_QUERY_NAMES = set(CPP_QUERIES.keys())

AST_SCOPES_FOR_FQN = {
    "namespace_definition", "class_specifier", "struct_specifier",
    "function_definition", "template_declaration",
}

class CppParser(BaseParser):
    def __init__(self):
        super().__init__()
        self.language = get_language("cpp")
        self.parser = get_parser("cpp")
        self.queries: Dict[str, Any] = {}
        self.current_file_path: Optional[str] = None

        if self.language:
            successful_queries_count = 0
            failed_query_names_with_errors: Dict[str, str] = {}

            for name, query_str in CPP_QUERIES.items():
                try:
                    query_obj = self.language.query(query_str)
                    self.queries[name] = query_obj
                    successful_queries_count += 1
                except Exception as e:
                    error_msg = f"{type(e).__name__}: {e}"
                    logger.error(f"CppParser: FAILED to compile C++ query '{name}'. Error: {error_msg}. Query:\n{query_str}", exc_info=True)
                    failed_query_names_with_errors[name] = error_msg

            expected_query_count = len(ALL_QUERY_NAMES)
            if successful_queries_count == expected_query_count:
                logger.info(f"CppParser: All {expected_query_count} actively defined C++ queries compiled successfully.")
            else:
                logger.warning(f"CppParser: Successfully compiled {successful_queries_count}/{expected_query_count} C++ queries.")
                if failed_query_names_with_errors:
                    logger.warning(f"CppParser: Failed to compile the following queries: {failed_query_names_with_errors}")
        else:
            logger.error("CppParser: C++ tree-sitter language not loaded. Queries not compiled.")

    def _get_node_name_text(self, node: Optional[TSNODE_TYPE], content_bytes: bytes) -> Optional[str]:
        if not node: return None
        name = get_node_text(node, content_bytes)
        if name:
            if "::operator" in name:
                parts = name.split("::operator", 1)
                op_part = parts[1].split("(",1)[0]
                name = f"{parts[0]}::operator{op_part}"
            elif name.startswith("operator"):
                op_part = name.replace("operator", "", 1).split("(",1)[0]
                name = f"operator{op_part}"
        return name

    def _get_fqn_for_node(self,
                          name_node: TSNODE_TYPE,
                          content_bytes: bytes,
                          root_node_for_global_check: TSNODE_TYPE,
                          file_path: str,
                          query_name_for_debug: str
                         ) -> Tuple[str, str]:

        base_name_text = self._get_node_name_text(name_node, content_bytes) or "anonymous_or_unnamed"
        is_constructor = False
        is_destructor = False

        if name_node.parent and name_node.parent.type == "function_declarator":
            func_decl_node = name_node.parent
            func_def_or_field_decl_node = func_decl_node.parent
            if func_def_or_field_decl_node:
                temp_climber = func_def_or_field_decl_node.parent
                enclosing_class_name_text = None
                while temp_climber and temp_climber != root_node_for_global_check:
                    if temp_climber.type in {"class_specifier", "struct_specifier"}:
                        class_name_node_for_check = temp_climber.child_by_field_name("name")
                        if class_name_node_for_check:
                            enclosing_class_name_text = self._get_node_name_text(class_name_node_for_check, content_bytes)
                        break
                    temp_climber = temp_climber.parent
                if enclosing_class_name_text:
                    if name_node.type == "identifier" and base_name_text == enclosing_class_name_text:
                        is_constructor = True
                    elif name_node.type == "destructor_name" and base_name_text.startswith("~") and base_name_text.endswith(enclosing_class_name_text):
                        is_destructor = True

        simple_name_for_id_override = None
        if name_node.type == "destructor_name":
            simple_name_for_id_override = base_name_text

        if name_node.type == "namespace_definition" and not name_node.child_by_field_name("name"):
            return "anonymous", "anonymous"

        scopes_reversed = []
        climb_start_node = name_node.parent if name_node.type not in AST_SCOPES_FOR_FQN else name_node
        current_node = climb_start_node
        original_name_node_type = name_node.type

        while current_node and current_node.parent:
            parent_node = current_node.parent
            if current_node.type in AST_SCOPES_FOR_FQN:
                scope_name_node: Optional[TSNODE_TYPE] = None
                current_scope_name_text = "ERROR_NO_SCOPE_NAME_FOUND"
                if current_node.type == "namespace_definition":
                    scope_name_node = current_node.child_by_field_name("name")
                    if not scope_name_node: current_scope_name_text = "anonymous"
                    elif scope_name_node.type == "nested_namespace_specifier":
                        current_scope_name_text = get_node_text(scope_name_node, content_bytes)
                        scope_name_node = None
                    else: current_scope_name_text = self._get_node_name_text(scope_name_node, content_bytes)
                elif current_node.type in {"class_specifier", "struct_specifier"}:
                    scope_name_node = current_node.child_by_field_name("name")
                    current_scope_name_text = self._get_node_name_text(scope_name_node, content_bytes)
                if current_scope_name_text and current_scope_name_text != "ERROR_NO_SCOPE_NAME_FOUND":
                    scopes_reversed.append(current_scope_name_text)
            if current_node == root_node_for_global_check: break
            current_node = parent_node
            if not current_node: break

        leading_colons = ""
        cleaned_base_name_text = base_name_text
        if name_node.type == "qualified_identifier" and base_name_text.startswith("::"):
            leading_colons = "::"
            cleaned_base_name_text = base_name_text.lstrip(':')

        final_scopes = []
        for scope_part in reversed(scopes_reversed):
            if "::" in scope_part: final_scopes.extend(s for s in scope_part.split("::") if s)
            else:
                if scope_part: final_scopes.append(scope_part)

        fqn_parts_to_join = []
        if "::" in cleaned_base_name_text:
            base_parts = [p for p in cleaned_base_name_text.split("::") if p]
            fqn_parts_to_join = final_scopes + base_parts
            simple_name_for_id = base_parts[-1] if base_parts else cleaned_base_name_text
        elif is_constructor:
            fqn_parts_to_join = final_scopes + [cleaned_base_name_text]
            simple_name_for_id = cleaned_base_name_text
        elif is_destructor:
            fqn_parts_to_join = final_scopes + [cleaned_base_name_text]
            simple_name_for_id = cleaned_base_name_text
        else:
            fqn_parts_to_join = final_scopes + [cleaned_base_name_text]
            simple_name_for_id = cleaned_base_name_text

        unique_fqn_parts = []
        if fqn_parts_to_join:
            unique_fqn_parts.append(fqn_parts_to_join[0])
            for i in range(1, len(fqn_parts_to_join)):
                is_repeated_class_name_for_constructor = (
                    is_constructor and
                    fqn_parts_to_join[i] == fqn_parts_to_join[i-1] and
                    fqn_parts_to_join[i] == simple_name_for_id
                )
                if fqn_parts_to_join[i] != unique_fqn_parts[-1] or is_repeated_class_name_for_constructor:
                    if fqn_parts_to_join[i]:
                        unique_fqn_parts.append(fqn_parts_to_join[i])
        qualified_name_str = leading_colons + "::".join(unique_fqn_parts)

        if simple_name_for_id_override: simple_name_for_id = simple_name_for_id_override
        else:
            if "::" in qualified_name_str and not is_constructor and not is_destructor:
                 simple_name_for_id = qualified_name_str.split("::")[-1]
            elif is_constructor: simple_name_for_id = cleaned_base_name_text
            elif not is_constructor and not is_destructor : simple_name_for_id = cleaned_base_name_text

        # Changed FQN_... logs to logger.debug
        # logger.debug(f"[{file_path}] FQN_CLIMB_DEBUG for '{base_name_text}' ...")
        # logger.debug(f"[{file_path}] FQN_CLIMB_APPEND: Added '{current_scope_name_text}' ...")
        # logger.debug(f"[{file_path}]: FQN_DEBUG: base_name='{base_name_text}' ...")
        return qualified_name_str, simple_name_for_id

    def _extract_list_details(self, query: Any, node: TSNODE_TYPE, capture_name_to_match: str, content_bytes: bytes) -> List[str]:
        details = []
        if not query or not node: return details
        try:
            all_captures_from_node = query.captures(node)
            if node.type == "base_class_clause":
                logger.debug(f"[{self.current_file_path}] HERITAGE_DEBUG: _extract_list_details for base_class_clause. Target: '{capture_name_to_match}'.")
                logger.debug(f"[{self.current_file_path}] HERITAGE_DEBUG: Node Text: {get_node_text(node, content_bytes)}")
                logger.debug(f"[{self.current_file_path}] HERITAGE_DEBUG: Raw result of query.captures(node): {all_captures_from_node}")

            if isinstance(all_captures_from_node, list):
                 for captured_node_obj, actual_capture_name_str in all_captures_from_node:
                    if node.type == "base_class_clause":
                        logger.debug(f"[{self.current_file_path}] HERITAGE_DEBUG (list): Checking capture: Name='{actual_capture_name_str}', Node Type='{captured_node_obj.type}', Node Text='{get_node_text(captured_node_obj, content_bytes)}'")
                    if actual_capture_name_str == capture_name_to_match:
                        text = get_node_text(captured_node_obj, content_bytes)
                        if text:
                            details.append(text)
                            if node.type == "base_class_clause":
                                logger.debug(f"[{self.current_file_path}] HERITAGE_DEBUG (list): Matched and added '{text}' for '{capture_name_to_match}'")
            elif isinstance(all_captures_from_node, dict):
                if capture_name_to_match in all_captures_from_node:
                    list_of_captured_nodes = all_captures_from_node[capture_name_to_match]
                    for captured_node_obj in list_of_captured_nodes:
                        if node.type == "base_class_clause":
                            logger.debug(f"[{self.current_file_path}] HERITAGE_DEBUG (dict): Processing node for '{capture_name_to_match}': Node Type='{captured_node_obj.type}', Node Text='{get_node_text(captured_node_obj, content_bytes)}'")
                        text = get_node_text(captured_node_obj, content_bytes)
                        if text:
                            details.append(text)
                            if node.type == "base_class_clause":
                                 logger.debug(f"[{self.current_file_path}] HERITAGE_DEBUG (dict): Matched and added '{text}' for '{capture_name_to_match}'")
                elif node.type == "base_class_clause":
                     logger.debug(f"[{self.current_file_path}] HERITAGE_DEBUG (dict): Target capture '{capture_name_to_match}' not found in keys: {list(all_captures_from_node.keys())}")
            else:
                if node.type == "base_class_clause":
                    logger.warning(f"[{self.current_file_path}] HERITAGE_DEBUG: query.captures(node) returned unexpected type: {type(all_captures_from_node)}")
        except Exception as e:
            logger.error(f"[{self.current_file_path or 'UnknownFile'}] Error in _extract_list_details for capture '{capture_name_to_match}': {e}. Node type: {node.type if node else 'None'}", exc_info=True)
        return details

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[ParserOutput, None]:
        self.current_file_path = file_path
        logger.info(f"CppParser: Starting parsing for {file_path} (ID: {file_id})")

        queries_for_prereq_check = ALL_QUERY_NAMES.copy()
        queries_for_prereq_check.discard("deleted_methods_test")

        missing_standard_queries = queries_for_prereq_check - set(self.queries.keys())

        prerequisites_met = (self.parser and self.language and not missing_standard_queries)
        if not prerequisites_met:
            error_msg_parts = ["C++ parser prerequisites failed."]
            if not self.parser: error_msg_parts.append("Parser not loaded")
            if not self.language: error_msg_parts.append("Language not loaded")
            if missing_standard_queries:
                error_msg_parts.append(f"Missing standard compiled queries: {missing_standard_queries}")
            if "deleted_methods_test" not in self.queries and "deleted_methods_test" in CPP_QUERIES:
                 logger.warning(f"[{file_path}] Debug query 'deleted_methods_test' also failed to compile.")
            full_error_msg = f"For {file_path}: {'. '.join(error_msg_parts)}. SKIPPING detailed parsing."
            logger.error(full_error_msg)
            self.current_file_path = None; return

        content = await read_file_content(file_path)
        if content is None: self.current_file_path = None; return
        if not content.strip(): self.current_file_path = None; return

        try:
            content_bytes = bytes(content, "utf8")
            tree = self.parser.parse(content_bytes)
            root_node = tree.root_node

            chunk_nodes: List[TextChunk] = []
            current_line_num = 1
            for i, chunk_text_content in enumerate(basic_chunker(content)):
                if not chunk_text_content.strip():
                    current_line_num += chunk_text_content.count('\n'); continue
                chunk_start_line = current_line_num
                num_newlines_in_chunk = chunk_text_content.count('\n')
                chunk_end_line = chunk_start_line + num_newlines_in_chunk
                chunk_id_val = f"{file_id}:{i}"
                chunk_node_val = TextChunk(id=chunk_id_val, start_line=chunk_start_line, end_line=chunk_end_line, chunk_content=chunk_text_content)
                yield chunk_node_val; chunk_nodes.append(chunk_node_val)
                yield Relationship(source_id=file_id, target_id=chunk_id_val, type="CONTAINS_CHUNK")
                current_line_num = chunk_end_line + 1
            if chunk_nodes: logger.debug(f"[{file_path}] Yielded {len(chunk_nodes)} TextChunk nodes.")

            def find_chunk_for_node(node_to_find: Optional[TSNODE_TYPE]) -> Optional[TextChunk]:
                if not node_to_find: return None
                node_start_line = node_to_find.start_point[0] + 1
                node_end_line = node_to_find.end_point[0] + 1
                best_fit_chunk = None; min_line_diff_at_start = float('inf')
                for chk in chunk_nodes:
                    if chk.start_line <= node_start_line and chk.end_line >= node_end_line:
                        current_diff = node_start_line - chk.start_line
                        if current_diff < min_line_diff_at_start:
                            min_line_diff_at_start = current_diff; best_fit_chunk = chk
                        elif current_diff == min_line_diff_at_start and best_fit_chunk and \
                             (chk.end_line - chk.start_line) < (best_fit_chunk.end_line - best_fit_chunk.start_line):
                            best_fit_chunk = chk
                if not best_fit_chunk:
                    for chk in chunk_nodes:
                        if chk.start_line <= node_start_line <= chk.end_line:
                            best_fit_chunk = chk
                            logger.warning(f"[{file_path}] Node {node_to_find.type} ({node_start_line}-{node_end_line}) not fully contained. Assigning to chunk {chk.id} ({chk.start_line}-{chk.end_line}) containing its start line.")
                            break
                if not best_fit_chunk:
                     logger.warning(f"[{file_path}] Could not find containing chunk for node {node_to_find.type if node_to_find else 'None'} lines {node_start_line}-{node_end_line}")
                return best_fit_chunk

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
            processed_node_starts_for_entities = set()
            heritage_detail_query = self.queries.get("heritage_details")

            for query_name, base_entity_type in entity_configs:
                query_obj = self.queries.get(query_name)
                if not query_obj:
                    logger.info(f"[{file_path}] Standard query '{query_name}' not compiled or missing. Skipping.")
                    continue
                for match_id, captures_dict in query_obj.matches(root_node):
                    definition_node: Optional[TSNODE_TYPE] = captures_dict.get("definition", [None])[0]
                    name_node: Optional[TSNODE_TYPE] = captures_dict.get("name", [None])[0]
                    if query_name == "namespace_aliases": name_node = captures_dict.get("alias_new_name", [None])[0]
                    if not definition_node: logger.debug(f"[{file_path}] Query '{query_name}' no '@definition'. Skip."); continue
                    if definition_node.start_byte in processed_node_starts_for_entities: continue
                    processed_node_starts_for_entities.add(definition_node.start_byte)
                    node_for_fqn_name = name_node
                    if query_name == "namespaces" and not name_node and definition_node.type == "namespace_definition":
                        node_for_fqn_name = definition_node
                    if not node_for_fqn_name and base_entity_type != "NamespaceDefinition":
                        logger.debug(f"[{file_path}] Query '{query_name}' no valid name node. Def type: {definition_node.type}. Skip."); continue

                    qualified_name_str, simple_name_for_id = self._get_fqn_for_node(
                        node_for_fqn_name, content_bytes, root_node, file_path, query_name
                    )
                    if not qualified_name_str: logger.warning(f"[{file_path}] FQN empty for {node_for_fqn_name.type}. Skip."); continue

                    actual_entity_type = base_entity_type

                    id_name_part = qualified_name_str.replace("::", "_SCOPE_")
                    snippet_content_str = get_node_text(definition_node, content_bytes)
                    if not snippet_content_str: logger.debug(f"[{file_path}] No snippet for {qualified_name_str}. Skip."); continue
                    parent_chunk = find_chunk_for_node(definition_node);
                    if not parent_chunk: continue
                    chunk_id_for_entity = parent_chunk.id
                    idx = chunk_entity_counters[chunk_id_for_entity][(actual_entity_type, id_name_part)]
                    chunk_entity_counters[chunk_id_for_entity][(actual_entity_type, id_name_part)] = idx + 1
                    code_entity_id_val = f"{chunk_id_for_entity}:{actual_entity_type}:{id_name_part}:{idx}"

                    if "anonymous_or_unnamed" in qualified_name_str and actual_entity_type == "FunctionDefinition":
                        logger.info(f"ANON_FUNC_DBG: Snippet: {snippet_content_str[:100].strip()}, Query: '{query_name}', EntityType: '{actual_entity_type}', SimpleName: '{simple_name_for_id}', FQN: '{qualified_name_str}', ID: '{code_entity_id_val}'")
                    if actual_entity_type == "FunctionDefinition" and "= delete" in snippet_content_str:
                        logger.info(f"DELETE_DBG: Snippet: {snippet_content_str[:100].strip()}, Query: '{query_name}', EntityType: '{actual_entity_type}', SimpleName: '{simple_name_for_id}', FQN: '{qualified_name_str}'")

                    yield CodeEntity(id=code_entity_id_val, type=actual_entity_type, snippet_content=snippet_content_str)
                    yield Relationship(source_id=chunk_id_for_entity, target_id=code_entity_id_val, type="CONTAINS_ENTITY")

                    if actual_entity_type in ["ClassDefinition", "StructDefinition"] and heritage_detail_query:
                        heritage_node = captures_dict.get("heritage", [None])[0]
                        if heritage_node and heritage_node.type == "base_class_clause":
                            all_parents = set(self._extract_list_details(heritage_detail_query, heritage_node, "heritage_type_identifier", content_bytes) + \
                                              self._extract_list_details(heritage_detail_query, heritage_node, "heritage_qualified_identifier", content_bytes))
                            for p_name in all_parents:
                                if p_name: yield Relationship(source_id=code_entity_id_val, target_id=p_name.strip(), type="EXTENDS"); logger.debug(f"[{file_path}] EXTENDS: {qualified_name_str} -> {p_name.strip()}")
                        elif heritage_node: logger.warning(f"[{file_path}] Heritage for {qualified_name_str} type '{heritage_node.type}', expected 'base_class_clause'. Skip EXTENDS.")

            processed_directives = set()
            include_query = self.queries.get("includes")
            if include_query:
                for _, captures_in_match_dict in include_query.matches(root_node):
                    statement_node: Optional[TSNODE_TYPE] = captures_in_match_dict.get("include_statement", [None])[0]
                    target_node: Optional[TSNODE_TYPE] = captures_in_match_dict.get("include", [None])[0]
                    if statement_node and target_node:
                        target_module_str = get_node_text(target_node, content_bytes)
                        if target_module_str:
                            if (target_module_str.startswith('<') and target_module_str.endswith('>')) or \
                               (target_module_str.startswith('"') and target_module_str.endswith('"')):
                                target_module_str = target_module_str[1:-1]
                            start_line = statement_node.start_point[0] + 1
                            import_key = (target_module_str, start_line, "include")
                            if import_key not in processed_directives:
                                yield Relationship(source_id=file_id, target_id=target_module_str, type="IMPORTS")
                                processed_directives.add(import_key)

            using_ns_query = self.queries.get("using_namespace")
            if using_ns_query:
                for _, captures_in_match_dict in using_ns_query.matches(root_node):
                    statement_node: Optional[TSNODE_TYPE] = captures_in_match_dict.get("using_statement", [None])[0]
                    target_node: Optional[TSNODE_TYPE] = captures_in_match_dict.get("name", [None])[0]
                    if statement_node and target_node:
                        target_namespace_str = get_node_text(target_node, content_bytes)
                        if target_namespace_str:
                            start_line = statement_node.start_point[0] + 1
                            using_key = (target_namespace_str, start_line, "using_namespace")
                            if using_key not in processed_directives:
                                yield Relationship(source_id=file_id, target_id=target_namespace_str, type="IMPORTS")
                                processed_directives.add(using_key)

        except Exception as e:
            logger.error(f"[{file_path}] Failed during detailed parsing of C++ file: {e}", exc_info=True)
        finally:
            self.current_file_path = None
