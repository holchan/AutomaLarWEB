# .roo/cognee/src/parser/parsers/cpp_parser.py
from pydantic import BaseModel
from typing import AsyncGenerator, Optional, List, Dict, Any, Set, Union
from collections import defaultdict

from .base_parser import BaseParser
from ..entities import CodeEntity, Relationship
from ..utils import get_node_text, logger, TSNODE_TYPE
from .treesitter_setup import get_parser, get_language

CPP_QUERIES = {
    "includes": """
        (preproc_include path: [(string_literal) (system_lib_string)] @include) @include_statement
        """,
    "function_definitions": """
        [
          (function_definition
            declarator: (function_declarator
                          declarator: [
                            (identifier) @name
                            (type_identifier) @name
                            (destructor_name) @name
                            (field_identifier) @name
                            (qualified_identifier) @name
                            (operator_name) @name
                          ]
                        )
            body: (compound_statement)
          ) @definition

          (function_definition ; For "= default"
            declarator: (function_declarator
                          declarator: [
                            (identifier) @name
                            (type_identifier) @name
                            (destructor_name) @name
                            (field_identifier) @name
                            (qualified_identifier) @name
                            (operator_name) @name
                          ]
                        )
            (default_method_clause)
          ) @definition

          (function_definition ; For "= delete"
            declarator: (function_declarator
                          declarator: [
                            (identifier) @name
                            (type_identifier) @name
                            (destructor_name) @name
                            (field_identifier) @name
                            (qualified_identifier) @name
                            (operator_name) @name
                          ]
                        )
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

          (field_declaration ; Catches method declarations (including constructors/destructors) within classes/structs
            type: (_)?
            declarator: (function_declarator
                          declarator: [
                              (identifier) @name
                              (field_identifier) @name
                              (type_identifier) @name
                              (destructor_name) @name
                              (operator_name) @name
                              (qualified_identifier) @name
                          ]
                        )
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
                  declarator: (function_declarator
                                declarator: [
                                    (identifier) @name
                                    (field_identifier) @name
                                    (qualified_identifier) @name
                                    (operator_name) @name
                                    (type_identifier) @name
                                ]
                              )
                  body: (compound_statement)
              )
          ) @definition

           (template_declaration
              parameters: (template_parameter_list)
              (function_definition
                  declarator: (function_declarator
                                declarator: [
                                    (identifier) @name
                                    (field_identifier) @name
                                    (qualified_identifier) @name
                                    (operator_name) @name
                                    (type_identifier) @name
                                ]
                              )
                  (default_method_clause)
              )
          ) @definition

           (template_declaration
              parameters: (template_parameter_list)
              (function_definition
                  declarator: (function_declarator
                                declarator: [
                                    (identifier) @name
                                    (field_identifier) @name
                                    (qualified_identifier) @name
                                    (operator_name) @name
                                    (type_identifier) @name
                                ]
                              )
                  (delete_method_clause)
              )
          ) @definition
        ]
        """,
    "template_function_declarations": """
        (template_declaration
            parameters: (template_parameter_list)
            (declaration
                type: (_)?
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
          body: (field_declaration_list)?
        ) @definition
        """,
    "structs": """
        (struct_specifier
          name: (type_identifier) @name
          (base_class_clause)? @heritage
          body: (field_declaration_list)?
        ) @definition
        """,
    "namespaces": """
        [
          (namespace_definition name: (namespace_identifier) @name body: (_)) @definition
          (namespace_definition name: (nested_namespace_specifier) @name body: (_)) @definition
          (namespace_definition body: (declaration_list)) @definition
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
          ;; For typedef int MyInt; or typedef OldType NewTypeName;
          (type_definition
            type: (_) @original_type  ;; Captures the original type part
            declarator: (type_identifier) @name ;; The new type name
          ) @definition

          ;; For typedef int *MyPtr;
          (type_definition
            type: (_) @original_type
            declarator: (pointer_declarator
                          ;; It could be (identifier) or (type_identifier) inside depending on grammar specifics
                          declarator: [(identifier) (type_identifier)] @name
                        )
          ) @definition

          ;; For typedef void (*FuncPtr)(int);
          (type_definition
            type: (_) @original_type ;; e.g., the 'void' part, params are part of declarator
            declarator: (pointer_declarator ;; the '*'
                          declarator: (function_declarator ;; the 'FuncPtr(int)' part
                                        declarator: [(identifier) (type_identifier)] @name ;; 'FuncPtr'
                                        parameters: (parameter_list) ;; '(int)'
                                      )
                        )
          ) @definition

          ;; For typedef int MyArray[10];
           (type_definition
            type: (_) @original_type ;; e.g., the 'int'
            declarator: (array_declarator
                            declarator: [(identifier) (type_identifier)] @name ;; 'MyArray'
                            size: (_)?
                        )
           ) @definition
        ]
        """,
    "using_namespace": """
        (using_declaration "namespace"
            [
              (identifier) @name
              (nested_namespace_specifier) @name
              (qualified_identifier) @name
            ]
        ) @using_statement
        """,
    "using_alias": """
        (alias_declaration
            name: (type_identifier) @name
            type: (_)
        ) @definition
        """,
    "namespace_aliases": """
        (namespace_alias_definition
          (namespace_identifier) @alias_new_name
          name: [
                  (namespace_identifier)
                  (nested_namespace_specifier)
                  (qualified_identifier)
                ] @alias_target_name
        ) @definition
        """,
    "heritage_details": """
        (type_identifier) @heritage_type_identifier
        (qualified_identifier) @heritage_qualified_identifier
        """,
}

ALL_QUERY_NAMES = set(CPP_QUERIES.keys())

AST_SCOPES_FOR_FQN = {
    "namespace_definition", "class_specifier", "struct_specifier",
    "function_definition",
    "template_declaration",
}


class CppParser(BaseParser):
    def __init__(self):
        super().__init__()
        self.language = get_language("cpp")
        self.parser = get_parser("cpp")
        self.queries: Dict[str, Any] = {}
        self.current_source_file_id_for_debug: Optional[str] = None

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
            logger.error("CppParser: C++ tree-sitter language not loaded. Queries not compiled. CppParser will not function correctly.")

    def _get_node_name_text(self, node: Optional[TSNODE_TYPE], content_bytes: bytes) -> Optional[str]:
        if not node: return None
        name = get_node_text(node, content_bytes)
        if name:
            if "::operator" in name:
                parts = name.split("::operator", 1)
                op_part = parts[1].split("(",1)[0].strip()
                name = f"{parts[0]}::operator{op_part}"
            elif name.startswith("operator"):
                op_part = name.replace("operator", "", 1).split("(",1)[0].strip()
                name = f"operator{op_part}"
        return name

    def _get_fqn_for_node(self,
                          name_node: Optional[TSNODE_TYPE],
                          definition_or_declaration_node: TSNODE_TYPE,
                          content_bytes: bytes,
                          root_node_for_global_check: TSNODE_TYPE,
                          source_file_id_for_debug: str) -> str:

        base_name_text = "anonymous"
        if name_node:
            base_name_text = self._get_node_name_text(name_node, content_bytes) or "unnamed_from_node"
        elif definition_or_declaration_node.type == "namespace_definition":
            pass
        else:
            logger.warning(f"FQN: name_node is None for def_node type '{definition_or_declaration_node.type}' in {source_file_id_for_debug}. Defaulting base_name to 'unnamed_entity'. Snippet: {get_node_text(definition_or_declaration_node, content_bytes)[:50]}")
            base_name_text = "unnamed_entity"

        scopes_reversed = []
        current_climb_node = definition_or_declaration_node.parent

        while current_climb_node and current_climb_node != root_node_for_global_check:
            if current_climb_node.type in AST_SCOPES_FOR_FQN:
                scope_name_text = "anonymous"
                potential_scope_name_node = current_climb_node.child_by_field_name("name")
                if potential_scope_name_node:
                    scope_name_text = self._get_node_name_text(potential_scope_name_node, content_bytes) or "anonymous"
                elif current_climb_node.type == "namespace_definition" and not potential_scope_name_node:
                    pass
                scopes_reversed.append(scope_name_text)
            current_climb_node = current_climb_node.parent

        scope_prefix_parts = [s for s in reversed(scopes_reversed) if s]
        final_fqn_parts = []
        leading_colons = ""

        if name_node and name_node.type == "qualified_identifier":
            raw_qualified_name = base_name_text
            if raw_qualified_name.startswith("::"):
                leading_colons = "::"
                raw_qualified_name = raw_qualified_name.lstrip(':')
            qualified_name_segments = [seg for seg in raw_qualified_name.split("::") if seg]

            temp_merged_parts = list(scope_prefix_parts)
            idx_to_match_from_qual = 0
            if temp_merged_parts and qualified_name_segments:
                if temp_merged_parts[-1] == qualified_name_segments[0] and len(qualified_name_segments) > 1 :
                    idx_to_match_from_qual = 1

            final_fqn_parts = temp_merged_parts + qualified_name_segments[idx_to_match_from_qual:]
        else:
            final_fqn_parts = scope_prefix_parts + [base_name_text]

        unique_parts = []
        if final_fqn_parts:
            first_part_to_consider = final_fqn_parts[0]
            if leading_colons and not first_part_to_consider and len(final_fqn_parts) > 1:
                unique_parts.append(final_fqn_parts[1])
                start_index_for_loop = 2
            elif first_part_to_consider:
                unique_parts.append(first_part_to_consider)
                start_index_for_loop = 1
            else:
                start_index_for_loop = 1

            for i in range(start_index_for_loop, len(final_fqn_parts)):
                current_part = final_fqn_parts[i]
                if not current_part: continue

                prev_part = unique_parts[-1] if unique_parts else None

                is_constructor = (name_node and name_node.type != "destructor_name" and
                                  current_part == prev_part and current_part == base_name_text)

                is_destructor_base_name = base_name_text.startswith('~')
                actual_class_name_for_destructor = base_name_text[1:] if is_destructor_base_name else None
                is_destructor = (name_node and name_node.type == "destructor_name" and
                                 current_part == base_name_text and
                                 prev_part == actual_class_name_for_destructor and actual_class_name_for_destructor is not None)

                if not prev_part or current_part != prev_part or is_constructor or is_destructor:
                    unique_parts.append(current_part)

        base_fqn_no_params = leading_colons + "::".join(filter(None, unique_parts))
        if not base_fqn_no_params:
            base_fqn_no_params = base_name_text if base_name_text and base_name_text != "anonymous" else "unnamed_entity_in_fqn"

        param_string = ""
        function_declarator_node = None

        if definition_or_declaration_node.type == "function_definition":
            declarator_child = definition_or_declaration_node.child_by_field_name("declarator")
            if declarator_child and declarator_child.type == "function_declarator":
                function_declarator_node = declarator_child
        elif definition_or_declaration_node.type == "template_declaration":
            func_def_child = next((c for c in definition_or_declaration_node.children if c.type == "function_definition"), None)
            if func_def_child:
                declarator_child = func_def_child.child_by_field_name("declarator")
                if declarator_child and declarator_child.type == "function_declarator":
                    function_declarator_node = declarator_child
        elif definition_or_declaration_node.type == "declaration":
            function_declarator_node = next((child for child in definition_or_declaration_node.children if child.type == "function_declarator"), None)
        elif definition_or_declaration_node.type == "field_declaration":
            direct_declarator = definition_or_declaration_node.child_by_field_name("declarator")
            if direct_declarator and direct_declarator.type == "function_declarator":
                 function_declarator_node = direct_declarator

        if function_declarator_node:
            param_list_node = function_declarator_node.child_by_field_name("parameters")
            if param_list_node and param_list_node.type == "parameter_list":
                param_type_texts = []
                for param_decl_node in param_list_node.named_children:
                    full_param_text_for_debug = get_node_text(param_decl_node, content_bytes)
                    logger.debug(f"FQN_PARAM_PROCESSING: File='{source_file_id_for_debug}' Entity='{base_fqn_no_params}' FullParamDecl='{full_param_text_for_debug}' Node.type='{param_decl_node.type}'")

                    type_str_for_param = ""
                    if param_decl_node.type == "parameter_declaration": # Standard parameter
                        name_identifier_of_param = None
                        param_declarator_node_for_name_search = param_decl_node.child_by_field_name("declarator")

                        logger.debug(f"FQN_PARAM_NAME_SEARCH: Initial param_declarator_node for '{full_param_text_for_debug}' is type '{param_declarator_node_for_name_search.type if param_declarator_node_for_name_search else 'None'}' text: '{get_node_text(param_declarator_node_for_name_search, content_bytes) if param_declarator_node_for_name_search else 'N/A'}'")
                        if param_declarator_node_for_name_search:
                            node_to_search_name_in = param_declarator_node_for_name_search
                            depth = 0
                            while node_to_search_name_in and depth < 5:
                                current_search_node_text = get_node_text(node_to_search_name_in, content_bytes)
                                logger.debug(f"FQN_PARAM_NAME_SEARCH:  Searching in node type '{node_to_search_name_in.type}', text '{current_search_node_text}'")
                                if node_to_search_name_in.type == 'identifier':
                                    name_identifier_of_param = node_to_search_name_in
                                    logger.debug(f"FQN_PARAM_NAME_SEARCH:   Found identifier (direct type match): '{get_node_text(name_identifier_of_param, content_bytes)}'")
                                    break

                                found_direct_child_id = False
                                for child_node_in_search in node_to_search_name_in.children:
                                    if child_node_in_search.type == 'identifier':
                                        name_identifier_of_param = child_node_in_search
                                        logger.debug(f"FQN_PARAM_NAME_SEARCH:   Found identifier (as direct child of {node_to_search_name_in.type}): '{get_node_text(name_identifier_of_param, content_bytes)}'")
                                        found_direct_child_id = True
                                        break
                                if found_direct_child_id:
                                    break

                                nested_declarator = node_to_search_name_in.child_by_field_name("declarator")
                                if not nested_declarator:
                                    if node_to_search_name_in.type == 'identifier' and not name_identifier_of_param:
                                        name_identifier_of_param = node_to_search_name_in
                                        logger.debug(f"FQN_PARAM_NAME_SEARCH:   Found identifier (no nested_declarator, current is id): '{get_node_text(name_identifier_of_param, content_bytes)}'")
                                    else:
                                        logger.debug(f"FQN_PARAM_NAME_SEARCH:   No nested_declarator and current node '{node_to_search_name_in.type}' is not identifier or name already found.")
                                    break
                                node_to_search_name_in = nested_declarator
                                depth += 1
                            if not name_identifier_of_param:
                                logger.debug(f"FQN_PARAM_NAME_SEARCH: Loop finished, name_identifier_of_param is still None for '{full_param_text_for_debug}'.")
                        else:
                            logger.debug(f"FQN_PARAM_NAME_SEARCH: param_declarator_node was None initially for '{full_param_text_for_debug}'. This usually means type-only parameter or abstract declarator.")

                        if name_identifier_of_param:
                            logger.critical(f"FQN_PARAM_ENTERED_NAMED_BLOCK: For Param='{full_param_text_for_debug}', Name Found='{get_node_text(name_identifier_of_param, content_bytes)}'")
                            param_name_for_log = get_node_text(name_identifier_of_param, content_bytes)

                            # Simplified: Type is everything before the identified name in the param_decl_node
                            if param_decl_node.start_byte < name_identifier_of_param.start_byte:
                                type_str_for_param = content_bytes[param_decl_node.start_byte:name_identifier_of_param.start_byte].decode('utf-8').strip()
                            else: # Name is at the start, so type info might be from a 'type' field or empty
                                type_node_direct = param_decl_node.child_by_field_name("type")
                                if type_node_direct:
                                    type_str_for_param = get_node_text(type_node_direct, content_bytes).strip()
                                else:
                                    type_str_for_param = "" # No preceding text and no direct type field
                                    logger.warning(f"FQN_PARAM_LOGIC (Named - Name at Start, No Type Field): Param '{full_param_text_for_debug}' resulted in empty base type before normalization.")

                            type_str_for_param = ' '.join(type_str_for_param.split()) # Normalize whitespace
                            logger.debug(f"FQN_PARAM_LOGIC (Named - Primary Slice): Type='{type_str_for_param}' for param '{param_name_for_log}'")

                        else: # No name_identifier_of_param found (e.g. abstract declarator, or just a type)
                            logger.critical(f"FQN_PARAM_ENTERED_UNNAMED_BLOCK: For Param='{full_param_text_for_debug}', Name NOT Found.")
                            type_node_direct = param_decl_node.child_by_field_name("type")
                            if type_node_direct:
                                type_str_for_param = ' '.join(get_node_text(type_node_direct, content_bytes).split())
                                logger.debug(f"FQN_PARAM_LOGIC (Unnamed/Abstract - Type Field): Using type field -> Type='{type_str_for_param}'")
                            else:
                                # Fallback to full text of param_decl_node if no 'type' field either
                                type_str_for_param = ' '.join(get_node_text(param_decl_node, content_bytes).split())
                                logger.debug(f"FQN_PARAM_LOGIC (Unnamed/Abstract - Full Text): No type field, using full text -> Type='{type_str_for_param}'")

                        if type_str_for_param:
                           param_type_texts.append(type_str_for_param)
                        else:
                            logger.warning(f"FQN_PARAM_TYPE_EMPTY_FINAL: Param '{full_param_text_for_debug}' resulted in empty type string.")

                    elif param_decl_node.type == "optional_parameter_declaration": # Handling for default arguments
                        logger.critical(f"FQN_PARAM_ENTERED_OPTIONAL_BLOCK: For Param='{full_param_text_for_debug}'")
                        # The goal is to get the type part, excluding the name and the default value.
                        # An optional_parameter_declaration usually has 'type' and 'name' (or 'declarator')
                        # and 'default_value'.
                        # Sometimes it wraps a 'parameter_declaration'.

                        core_type_node = param_decl_node.child_by_field_name("type")
                        core_declarator_node = param_decl_node.child_by_field_name("name") # Tree-sitter C++ uses 'name' for the declarator here
                        if not core_declarator_node: # Try 'declarator' if 'name' is not used for this
                             core_declarator_node = param_decl_node.child_by_field_name("declarator")

                        temp_type_str = ""
                        if core_type_node:
                            temp_type_str = get_node_text(core_type_node, content_bytes).strip()

                        if core_declarator_node: # If there's a declarator (like `* name` or just `name`)
                            # We need to extract type modifiers from declarator but not the name itself
                            name_ident_in_opt = None
                            node_to_search = core_declarator_node
                            while node_to_search:
                                if node_to_search.type == 'identifier': name_ident_in_opt = node_to_search; break
                                child_d = node_to_search.child_by_field_name("declarator")
                                if not child_d:
                                    if node_to_search.type == 'identifier': name_ident_in_opt = node_to_search
                                    break
                                node_to_search = child_d

                            if name_ident_in_opt:
                                if core_declarator_node.start_byte < name_ident_in_opt.start_byte:
                                    declarator_prefix = content_bytes[core_declarator_node.start_byte:name_ident_in_opt.start_byte].decode('utf-8').strip()
                                    temp_type_str = (temp_type_str + " " + declarator_prefix).strip() # Add modifiers like * or &
                            elif core_type_node is None: # No type node and no name, take full declarator as type
                                temp_type_str = get_node_text(core_declarator_node, content_bytes).strip()

                        type_str_for_param = ' '.join(temp_type_str.split())
                        logger.debug(f"FQN_PARAM_LOGIC (Optional Param): Extracted type='{type_str_for_param}'")
                        if type_str_for_param:
                           param_type_texts.append(type_str_for_param)
                        else:
                           logger.warning(f"FQN_PARAM_TYPE_EMPTY_OPTIONAL: Optional Param '{full_param_text_for_debug}' resulted in empty type string.")


                    elif param_decl_node.type == "variadic_parameter_declaration": # '...'
                        param_type_texts.append("...")
                    else:
                        unknown_param_text = get_node_text(param_decl_node, content_bytes)
                        normalized_unknown = ' '.join(unknown_param_text.split())
                        if normalized_unknown: param_type_texts.append(normalized_unknown)
                        logger.debug(f"FQN_PARAM_UNKNOWN_TYPE: Node type {param_decl_node.type} in {base_fqn_no_params} (file {source_file_id_for_debug}): Text='{unknown_param_text}'")

                if param_type_texts:
                    param_string_content = ",".join(param_type_texts)
                    param_string = f"({param_string_content})"
                else:
                    raw_param_list_text = get_node_text(param_list_node, content_bytes).strip()
                    if raw_param_list_text == "(void)" or raw_param_list_text == "()":
                        param_string = "()"
                    else:
                        logger.warning(f"FQN_PARAM_LIST_UNPARSED: Param list '{raw_param_list_text}' for {base_fqn_no_params} resulted in no types, using raw content.")
                        param_string = f"({raw_param_list_text.strip('()')})"
            else:
                param_string = "()"

        final_fqn = base_fqn_no_params + param_string
        logger.debug(f"FQN_RESULT: File='{source_file_id_for_debug}' NameNode='{get_node_text(name_node, content_bytes) if name_node else 'N/A'}' DefNode.type='{definition_or_declaration_node.type}' -> FQN='{final_fqn}'")
        return final_fqn

    def _extract_list_details(self, query: Any, node: TSNODE_TYPE, capture_name_to_match: str, content_bytes: bytes) -> List[str]:
        details = []
        if not query or not node: return details
        try:
            all_captures_from_node_raw = query.captures(node)

            if isinstance(all_captures_from_node_raw, list):
                for captured_node_obj, actual_capture_name_str in all_captures_from_node_raw:
                    if actual_capture_name_str == capture_name_to_match:
                        text = get_node_text(captured_node_obj, content_bytes)
                        if text:
                            details.append(text.strip())
            elif isinstance(all_captures_from_node_raw, dict):
                if capture_name_to_match in all_captures_from_node_raw:
                    nodes_for_capture = all_captures_from_node_raw[capture_name_to_match]
                    for captured_node_obj in nodes_for_capture:
                        text = get_node_text(captured_node_obj, content_bytes)
                        if text:
                            details.append(text.strip())
            else:
                source_file_id = self.current_source_file_id_for_debug if self.current_source_file_id_for_debug else 'UnknownFile'
                logger.warning(f"[{source_file_id}] _extract_list_details: query.captures(node) returned unexpected type: {type(all_captures_from_node_raw)}")

        except Exception as e:
            source_file_id = self.current_source_file_id_for_debug if self.current_source_file_id_for_debug else 'UnknownFile'
            logger.error(f"[{source_file_id}] Error in _extract_list_details for capture '{capture_name_to_match}': {e}. Node type: {node.type if node else 'None'}", exc_info=True)
        return details

    async def parse(self, source_file_id: str, full_content_string: str) -> AsyncGenerator[Union[List[int], CodeEntity, Relationship], None]:
        self.current_source_file_id_for_debug = source_file_id
        logger.info(f"CppParser: Starting parsing for {source_file_id}")

        if not self.parser or not self.language or (not self.queries and ALL_QUERY_NAMES):
            logger.error(f"CppParser for {source_file_id}: Not properly initialized. Aborting.")
            yield []
            self.current_source_file_id_for_debug = None
            return

        if not full_content_string.strip():
            logger.info(f"CppParser: Empty or whitespace-only content for {source_file_id}.")
            yield []
            self.current_source_file_id_for_debug = None
            return

        try:
            content_bytes = bytes(full_content_string, "utf8")
            tree = self.parser.parse(content_bytes)
            root_node = tree.root_node

            slice_lines_set: Set[int] = {0}
            queries_for_slicing = [
                "includes", "namespaces", "classes", "structs", "enums", "typedefs",
                "using_alias", "namespace_aliases",
                "function_definitions", "template_function_definitions",
                "function_declarations", "template_function_declarations"
            ]

            for query_key in queries_for_slicing:
                query_obj = self.queries.get(query_key)
                if not query_obj:
                    logger.debug(f"[{source_file_id}] Slicing: Query '{query_key}' not available. Skipping.")
                    continue

                for match_id, captures_dict in query_obj.matches(root_node):
                    node_to_slice_at: Optional[TSNODE_TYPE] = None
                    if "definition" in captures_dict:
                        node_to_slice_at = captures_dict.get("definition", [None])[0]
                    elif "include_statement" in captures_dict:
                         node_to_slice_at = captures_dict.get("include_statement", [None])[0]
                    elif "using_statement" in captures_dict:
                         node_to_slice_at = captures_dict.get("using_statement", [None])[0]

                    if node_to_slice_at:
                        slice_lines_set.add(node_to_slice_at.start_point[0])

            slice_lines = sorted(list(slice_lines_set))
            yield slice_lines
            logger.debug(f"[{source_file_id}] Yielded slice_lines: {slice_lines}")

            processed_node_starts_for_entities = set()
            heritage_detail_query = self.queries.get("heritage_details")

            entity_configs = [
                ("function_definitions", "FunctionDefinition", "name"),
                ("function_declarations", "FunctionDeclaration", "name"),
                ("template_function_definitions", "FunctionDefinition", "name"),
                ("template_function_declarations", "FunctionDeclaration", "name"),
                ("classes", "ClassDefinition", "name"),
                ("structs", "StructDefinition", "name"),
                ("namespaces", "NamespaceDefinition", "name"),
                ("enums", "EnumDefinition", "name"),
                ("typedefs", "TypeAlias", "name"),
                ("using_alias", "TypeAlias", "name"),
                ("namespace_aliases", "NamespaceAliasDefinition", "alias_new_name"),
            ]

            for query_name, element_type, name_capture_key in entity_configs:
                query_obj = self.queries.get(query_name)
                if not query_obj:
                    logger.debug(f"[{source_file_id}] Entity Extraction: Query '{query_name}' not available. Skipping.")
                    continue

                for match_id, captures_dict in query_obj.matches(root_node):
                    definition_node: Optional[TSNODE_TYPE] = captures_dict.get("definition", [None])[0]
                    name_node: Optional[TSNODE_TYPE] = captures_dict.get(name_capture_key, [None])[0]

                    if not definition_node:
                        continue

                    if definition_node.start_byte in processed_node_starts_for_entities:
                        continue
                    processed_node_starts_for_entities.add(definition_node.start_byte)

                    if not name_node and element_type not in ["NamespaceDefinition"]:
                        logger.debug(f"[{source_file_id}] No name_node for query '{query_name}', ET '{element_type}'. Def: {get_node_text(definition_node, content_bytes)[:30]}. Skip.")
                        continue

                    true_fqn = self._get_fqn_for_node(
                        name_node,
                        definition_node,
                        content_bytes,
                        root_node,
                        source_file_id
                    )
                    if not true_fqn or "unnamed_entity_in_fqn" in true_fqn:
                        logger.warning(f"[{source_file_id}] Invalid FQN '{true_fqn}' for Q '{query_name}', ET '{element_type}'. Def: {get_node_text(definition_node, content_bytes)[:50]}... Skip.")
                        continue

                    original_ast_start_line_0 = definition_node.start_point[0]
                    temp_ref_id = f"{true_fqn}@{original_ast_start_line_0}"
                    snippet_content_str = get_node_text(definition_node, content_bytes)

                    code_entity_instance = CodeEntity(
                        id=temp_ref_id,
                        type=element_type,
                        snippet_content=snippet_content_str
                    )
                    yield code_entity_instance
                    logger.debug(f"[{source_file_id}] Yielded CE: {temp_ref_id} (type: {element_type})")

                    if element_type in ["ClassDefinition", "StructDefinition"] and heritage_detail_query:
                        heritage_node = captures_dict.get("heritage", [None])[0]
                        if heritage_node and heritage_node.type == "base_class_clause":
                            all_parents_text = set(self._extract_list_details(heritage_detail_query, heritage_node, "heritage_type_identifier", content_bytes) + \
                                                   self._extract_list_details(heritage_detail_query, heritage_node, "heritage_qualified_identifier", content_bytes))
                            for p_name_raw in all_parents_text:
                                p_name = ' '.join(p_name_raw.split())
                                if p_name:
                                    yield Relationship(source_id=temp_ref_id, target_id=p_name, type="EXTENDS")
                                    logger.debug(f"[{source_file_id}] Yielded EXTENDS: {temp_ref_id} -> {p_name}")

            include_query = self.queries.get("includes")
            if include_query:
                for _, captures_in_match_dict in include_query.matches(root_node):
                    statement_node: Optional[TSNODE_TYPE] = captures_in_match_dict.get("include_statement", [None])[0]
                    target_node: Optional[TSNODE_TYPE] = captures_in_match_dict.get("include", [None])[0]
                    if statement_node and target_node:
                        include_path_raw = get_node_text(target_node, content_bytes)
                        if include_path_raw:
                            canonical_include_path = include_path_raw.strip('<>"')
                            external_fqn = ""
                            if include_path_raw.startswith("<"):
                                external_fqn = f"std::{canonical_include_path}"
                            else:
                                external_fqn = canonical_include_path

                            original_ast_start_line_0 = statement_node.start_point[0]
                            temp_ext_ref_id = f"{external_fqn}@{original_ast_start_line_0}"
                            import_snippet = get_node_text(statement_node, content_bytes)

                            ext_ref_entity = CodeEntity(
                                id=temp_ext_ref_id,
                                type="ExternalReference",
                                snippet_content=import_snippet
                            )
                            yield ext_ref_entity
                            logger.debug(f"[{source_file_id}] Yielded ExtRef CE: {temp_ext_ref_id}")
                            yield Relationship(source_id=source_file_id, target_id=temp_ext_ref_id, type="IMPORTS")
                            logger.debug(f"[{source_file_id}] Yielded IMPORTS Rel: {source_file_id} -> {temp_ext_ref_id}")

            using_ns_query = self.queries.get("using_namespace")
            if using_ns_query:
                 for _, captures_in_match_dict in using_ns_query.matches(root_node):
                    statement_node: Optional[TSNODE_TYPE] = captures_in_match_dict.get("using_statement", [None])[0]
                    name_node: Optional[TSNODE_TYPE] = captures_in_match_dict.get("name", [None])[0]
                    if statement_node and name_node:
                        namespace_name_str = get_node_text(name_node, content_bytes)
                        if namespace_name_str:
                            namespace_name_str = ' '.join(namespace_name_str.split())
                            original_ast_start_line_0 = statement_node.start_point[0]
                            using_directive_fqn = f"directive_using_namespace::{namespace_name_str}"
                            temp_using_ref_id = f"{using_directive_fqn}@{original_ast_start_line_0}"
                            using_snippet = get_node_text(statement_node, content_bytes)

                            using_ref_entity = CodeEntity(
                                id=temp_using_ref_id,
                                type="UsingDirective",
                                snippet_content=using_snippet
                            )
                            yield using_ref_entity
                            logger.debug(f"[{source_file_id}] Yielded UsingDirective CE: {temp_using_ref_id}")
                            yield Relationship(source_id=source_file_id, target_id=temp_using_ref_id, type="HAS_DIRECTIVE")
                            logger.debug(f"[{source_file_id}] Yielded HAS_DIRECTIVE Rel: {source_file_id} -> {temp_using_ref_id}")
                            yield Relationship(source_id=temp_using_ref_id, target_id=namespace_name_str, type="REFERENCES_NAMESPACE")
                            logger.debug(f"[{source_file_id}] Yielded REFERENCES_NAMESPACE Rel: {temp_using_ref_id} -> {namespace_name_str}")

        except Exception as e:
            logger.error(f"[{source_file_id}] CppParser failed during detailed parsing: {e}", exc_info=True)
        finally:
            self.current_source_file_id_for_debug = None
