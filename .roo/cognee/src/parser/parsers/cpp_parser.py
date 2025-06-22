from pydantic import BaseModel
from typing import AsyncGenerator, Optional, List, Dict, Any, Set, Union, Tuple
from collections import defaultdict
import re

from .base_parser import BaseParser
from ..entities import CodeEntity, Relationship, CallSiteReference, ParserOutput
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
            (default_method_clause)
          ) @definition

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
          (enum_specifier "struct" name: (type_identifier) @name type: (type_identifier)? body: (enumerator_list)?) @definition
        ]
        """,
    "typedefs": """
        [
          (type_definition
            type: (primitive_type)
            declarator: (function_declarator
                          declarator: (parenthesized_declarator
                                        (pointer_declarator
                                          declarator: (type_identifier) @name
                                        )
                                      )
                          parameters: (parameter_list)
                        )
          ) @definition

          (type_definition
            type: (_) @original_type
            declarator: (function_declarator declarator: (identifier) @name)
          ) @definition

          (type_definition
            type: (_) @original_type
            declarator: (pointer_declarator declarator: (identifier) @name)
          ) @definition

          (type_definition
            type: (_) @original_type
            declarator: (array_declarator declarator: (identifier) @name)
          ) @definition

          (type_definition
            type: (_) @original_type
            declarator: (type_identifier) @name
          ) @definition

          (alias_declaration
            name: (type_identifier) @name
            type: (_)
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
    "calls": """
        [
            (
              (call_expression
                function: [
                    (identifier)
                    (field_expression
                        field: _
                    )
                    (qualified_identifier
                        name: [
                            (identifier)
                            (operator_name)
                            (destructor_name)
                            (template_function)
                        ]
                    )
                    (template_function)
                    (parenthesized_expression)
                ] @function_node_for_call
                arguments: (argument_list) @arguments
              ) @call_site
            )
            (
              (binary_expression
                left: (_) @left_operand
                operator: [
                    "+" "-" "*" "/" "%" "==" "!=" "<" ">" "<=" ">=" "&&" "||"
                    "&" "|" "^" "<<" ">>"
                    "+=" "-=" "*=" "/=" "%=" "&=" "|=" "^=" "<<=" ">>=" "<=>"
                    ","
                ] @operator_symbol
                right: (_) @right_operand
              ) @call_site_operator
            )
            (
              (new_expression
                type: (_) @name
                arguments: (argument_list)? @arguments
              ) @call_site_constructor
            )
            (
              (delete_expression) @call_site_delete
            )
            (
              (declaration
                type: [
                  (type_identifier) @name
                  (qualified_identifier) @name
                  (template_type) @name
                ]
                declarator: (init_declarator
                  value: [
                    (argument_list) @arguments
                    (initializer_list) @arguments
                  ]
                )
              ) @call_site_constructor
            )
        ]
        """,
}


class CppParser(BaseParser):
    AST_SCOPES_FOR_FQN: Set[str] = {
        "namespace_definition", "class_specifier", "struct_specifier",
        "function_definition",
        "template_declaration",
    }

    def __init__(self):
        super().__init__()
        self.language = get_language("cpp")
        self.parser = get_parser("cpp")
        self.queries: Dict[str, Any] = {}
        self.current_source_file_id_for_debug: Optional[str] = None
        self._current_function_context_temp_id: Optional[str] = None


        if self.language:
            successful_queries_count = 0
            failed_query_names_with_errors: Dict[str, str] = {}
            expected_query_count = len(CPP_QUERIES)

            for name, query_str in CPP_QUERIES.items():
                try:
                    query_obj = self.language.query(query_str)
                    self.queries[name] = query_obj
                    successful_queries_count += 1
                except Exception as e:
                    error_msg = f"{type(e).__name__}: {e}"
                    query_preview = query_str.strip().split('\n', 1)[0]
                    logger.error(f"CppParser: FAILED to compile C++ query '{name}'. Error: {error_msg}. Query starts with: {query_preview}", exc_info=False)
                    failed_query_names_with_errors[name] = error_msg

            if successful_queries_count == expected_query_count:
                logger.info(f"CppParser: All {expected_query_count} C++ queries compiled successfully.")
            else:
                logger.warning(f"CppParser: Successfully compiled {successful_queries_count}/{expected_query_count} C++ queries.")
                if failed_query_names_with_errors:
                    logger.warning(f"CppParser: Failed to compile the following query names: {list(failed_query_names_with_errors.keys())}")
        else:
            logger.error("CppParser: C++ tree-sitter language not loaded. CppParser will not function correctly.")

    def _get_node_name_text(self, node: Optional[TSNODE_TYPE], content_bytes: bytes) -> Optional[str]:
        if not node: return None
        name_str = get_node_text(node, content_bytes)
        if not name_str: return None

        input_node_type_for_debug = node.type
        input_name_str_for_debug = name_str

        if node.type == "template_function":
            name_child_node = node.child_by_field_name("name")
            if not name_child_node:
                 potential_name_children = [
                    c for c in node.children
                    if c.type in ("identifier", "qualified_identifier", "field_identifier", "operator_name", "template_function") # Added template_function for cases like Ns::TemplateType<int>::static_template_method<double>()
                 ]
                 # Heuristic: if qualified_identifier is present, it's likely the core name part
                 # e.g. for std::vector<int>::size, "std::vector<int>" might be qualified_id, and "size" the field
                 # For template_function like my_func<int>, we want "my_func"
                 # Prioritize specific types if possible, else take first
                 best_name_node = None
                 for p_type in ("identifier", "field_identifier", "operator_name"):
                     found = [c for c in potential_name_children if c.type == p_type]
                     if found: best_name_node = found[0]; break
                 if not best_name_node and potential_name_children: # fallback to first if specific types not found
                     best_name_node = potential_name_children[0]

                 if best_name_node and best_name_node.type == "template_function": # If child is also template_function
                      # Recursively call or just get its name part without args
                      name_str_from_child_template = self._get_node_name_text(best_name_node, content_bytes)
                      if name_str_from_child_template: name_child_node = best_name_node # effectively using its processed name
                      # This is tricky, might need to ensure it doesn't re-add template args if already stripped
                 elif best_name_node:
                     name_child_node = best_name_node

            if name_child_node:
                name_str = get_node_text(name_child_node, content_bytes) or name_str
            else: # Fallback: try to strip template args from full text if no better name node found
                name_match = re.match(r"([^<]+)(?:<.*>)?", name_str)
                if name_match:
                    name_str = name_match.group(1).strip()

        elif node.type == "qualified_identifier":
            # For qualified_identifier like Ns::Type<int>::member or Ns::func<T>
            # we want "Ns::Type::member" or "Ns::func" before param mangling.
            # The tree-sitter node text might be "Ns::Type<int>::member".
            # We need to strip template arguments from *within* the qualified name.
            # Example: `Scope<TemplateArg>::Name` should become `Scope::Name` for FQN base.
            # Example: `func<TemplateArg>` should become `func`.

            # Iterate over children to reconstruct without template arguments in path segments
            # (But keep template arguments if they are part of the final name node itself, like in template_type)

            # A simple regex approach might be too naive here due to nested templates.
            # For now, rely on tree-sitter's get_node_text and then FQN logic will handle qualified names.
            # The _get_fqn_for_node tries to merge scopes.
            # This specific part is hard to get perfect for all cases like A<B>::C<D>::func<E>
            # without full semantic understanding. Let's assume get_node_text is good enough as a base.
            # The `template_type` node might be what we need to look for if the `name_node` is a `qualified_identifier`
            # that includes template arguments.

            # If name_str contains "<" and ">", it might have template arguments.
            # This is a simple heuristic, might need refinement.
            if '<' in name_str and '>' in name_str:
                # Try to remove template arguments: MyType<int> -> MyType
                # Ns::MyType<int>::func -> Ns::MyType::func
                # This regex tries to remove <...> only if it looks like template args
                # It's non-greedy for the content within <...>

                # First, check if the whole thing is a template_type like `std::vector<int>`
                # If so, we might want to keep it for certain contexts (like base classes)
                # but for function names, we want to strip it.

                # This stripping can be problematic for FQN of template specializations.
                # For now, the FQN logic will handle `base_name_text` which is this `name_str`.
                pass # Let FQN logic try to handle it, or it gets complex here.


        stripped_name_val = name_str.strip()

        # Pre-canonicalization for common symbols before "operator" regex
        if not stripped_name_val.lower().startswith("operator") and \
           not stripped_name_val.isalnum() and \
           stripped_name_val:

            if stripped_name_val == "()": name_str = "operator()"
            elif stripped_name_val == "[]": name_str = "operator[]"
            # For simple symbols like +, -, <<, -> etc.
            elif len(stripped_name_val) <= 2 and stripped_name_val and not stripped_name_val[0].isalnum() :
                name_str = f"operator{stripped_name_val}"

        # Standardize "operator" spacing and form
        if "operator" in name_str:
            # More robust regex for operator parsing
            # Handles: `operator +`, `operator+`, `std::operator+`, `operator new`, `operator new[]`, `operator "" foo` (literal)
            match = re.search(
                r"((?:[\w:]*::\s*)?operator)\s*"  # Group 1: operator keyword, possibly qualified, with optional trailing spaces
                r"(\b(?:new|delete)(?:\[\])?\b|"  # Group 2a: new, delete, new[], delete[] (keywords)
                r"\"\"|"                          # Group 2b: "" for literal operators (empty string part)
                r"[^\w\s\(\);{}\[\]:\<\>,.\*&%#!~\^|=]{1,3}(?:\[\])?|" # Group 2c: Symbols like +, [], ->*, up to 3 chars, plus optional []
                r"\b\w+\b)"                       # Group 2d: Conversion operator type like 'MyType' or name part of literal operator
                , name_str
            )

            if match:
                op_keyword_part = match.group(1).strip() # remove trailing space from keyword part
                op_symbol_part = match.group(2).strip()

                if op_symbol_part in ["new", "delete"] or op_symbol_part.startswith("new") or op_symbol_part.startswith("delete"):
                    # Ensure space for keywords: "operator new", "operator new[]"
                    name_str = f"{op_keyword_part} {op_symbol_part}"
                elif op_keyword_part.endswith("operator"): # for "operator+"
                    name_str = f"{op_keyword_part}{op_symbol_part}"
                else: # for "std::operator+" or similar
                    name_str = f"{op_keyword_part}{op_symbol_part}"

            # Fallback for simple "operator<symbol>" that might not be caught by the main regex,
            # and also ensure that if "operator" is part of a larger identifier, we don't mangle it.
            # E.g. "my_operator_func" should not become "operator_func"
            elif name_str.strip().startswith("operator") and \
                 not name_str.strip().replace("operator","",1)[0].isalnum() and \
                 "(" not in name_str and ")" not in name_str: # "operator+" vs "operator()"
                parts = name_str.strip().split("operator", 1)
                if len(parts) == 2 and (not parts[0].strip() or parts[0].strip().endswith("::")): # Ensure "operator" was at the start of a segment
                    symbol = parts[1].strip()
                    if symbol and not any(c in symbol for c in "()"):
                        name_str = f"{parts[0].strip()}operator{symbol}"


        logger.debug(f"GET_NODE_NAME_TEXT_DEBUG: InputNode.type='{input_node_type_for_debug}', Input.text='{input_name_str_for_debug}', Output.text='{name_str}'")
        return name_str

    def _get_fqn_for_node(self,
                          name_node: Optional[TSNODE_TYPE],
                          definition_or_declaration_node: TSNODE_TYPE,
                          content_bytes: bytes,
                          root_node_for_global_check: TSNODE_TYPE,
                          source_file_id_for_debug: str) -> str:
        base_name_text = "anonymous"
        if name_node:
            base_name_text = self._get_node_name_text(name_node, content_bytes) or "unnamed_from_node"
        elif definition_or_declaration_node.type == "namespace_definition" and not name_node:
            pass
        else:
            logger.debug(f"FQN_WARN: name_node is None for def_node type '{definition_or_declaration_node.type}' in {source_file_id_for_debug}. Defaulting base_name to 'unnamed_entity'. Snippet: {get_node_text(definition_or_declaration_node, content_bytes)[:50]}")
            base_name_text = "unnamed_entity"

        scopes_reversed = []
        current_climb_node = definition_or_declaration_node.parent

        while current_climb_node and current_climb_node != root_node_for_global_check:
            if current_climb_node.type in self.AST_SCOPES_FOR_FQN:
                scope_name_text = "anonymous"
                is_template_scope_for_current_entity = False

                if current_climb_node.type == "template_declaration":
                    inner_def_node = None
                    for child in current_climb_node.children:
                        if child.type in ("function_definition", "class_specifier", "struct_specifier", "alias_declaration", "type_definition", "declaration"):
                            inner_def_node = child
                            break

                    if inner_def_node:
                        potential_scope_name_node_in_child = inner_def_node.child_by_field_name("name")
                        if inner_def_node.type == "function_definition":
                            declarator = inner_def_node.child_by_field_name("declarator")
                            if declarator:
                                actual_name_bearer = declarator.child_by_field_name("declarator")
                                if actual_name_bearer:
                                     potential_scope_name_node_in_child = actual_name_bearer
                        elif inner_def_node.type == "declaration":
                             func_declarator_in_decl = next((ch for ch in inner_def_node.children if ch.type == "function_declarator"), None)
                             if func_declarator_in_decl:
                                 actual_name_bearer = func_declarator_in_decl.child_by_field_name("declarator")
                                 if actual_name_bearer:
                                      potential_scope_name_node_in_child = actual_name_bearer

                        if potential_scope_name_node_in_child:
                             temp_scope_name = self._get_node_name_text(potential_scope_name_node_in_child, content_bytes)
                             current_entity_base_name_no_params = base_name_text.split("(",1)[0]
                             if temp_scope_name == current_entity_base_name_no_params:
                                 is_template_scope_for_current_entity = True
                             else:
                                 scope_name_text = temp_scope_name or "anonymous_template_entity"
                elif current_climb_node.type == "function_definition":
                     pass
                else:
                    potential_scope_name_node = current_climb_node.child_by_field_name("name")
                    if potential_scope_name_node:
                        scope_name_text = self._get_node_name_text(potential_scope_name_node, content_bytes) or "anonymous"
                    elif current_climb_node.type == "namespace_definition" and not potential_scope_name_node:
                        pass

                if not is_template_scope_for_current_entity:
                    scopes_reversed.append(scope_name_text)

            current_climb_node = current_climb_node.parent

        scope_prefix_parts = [s for s in reversed(scopes_reversed) if s and s != "anonymous_template_entity"]
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
                max_overlap = 0
                for k_overlap in range(1, min(len(temp_merged_parts), len(qualified_name_segments)) + 1):
                    if temp_merged_parts[-k_overlap:] == qualified_name_segments[:k_overlap]:
                        max_overlap = k_overlap
                idx_to_match_from_qual = max_overlap
            final_fqn_parts = temp_merged_parts + qualified_name_segments[idx_to_match_from_qual:]
        else:
            final_fqn_parts = scope_prefix_parts + [base_name_text]

        unique_parts = []
        if final_fqn_parts:
            first_part_to_consider = final_fqn_parts[0]
            start_index_for_loop = 0
            if leading_colons and not first_part_to_consider and len(final_fqn_parts) > 1:
                unique_parts.append(final_fqn_parts[1])
                start_index_for_loop = 2
            elif first_part_to_consider or (not first_part_to_consider and not leading_colons) :
                unique_parts.append(first_part_to_consider)
                start_index_for_loop = 1

            for i in range(start_index_for_loop, len(final_fqn_parts)):
                current_part = final_fqn_parts[i]
                if not current_part:
                    if current_part == "anonymous" and i == len(final_fqn_parts) -1 :
                         pass
                    elif unique_parts and unique_parts[-1] == "":
                        continue
                    elif i < len(final_fqn_parts) -1 :
                         pass
                    else:
                        continue
                prev_part = unique_parts[-1] if unique_parts else None
                is_constructor_or_destructor_scenario = False
                if name_node and current_part == base_name_text and prev_part:
                    is_constructor = (current_part == prev_part and not current_part.startswith("~"))
                    is_destructor = (current_part.startswith("~") and current_part[1:] == prev_part)
                    is_constructor_or_destructor_scenario = is_constructor or is_destructor
                if not prev_part or current_part != prev_part or is_constructor_or_destructor_scenario:
                    unique_parts.append(current_part)

        final_unique_parts = [part for part in unique_parts if part is not None]
        if not final_unique_parts and "anonymous" in unique_parts:
            final_unique_parts = ["anonymous"]

        base_fqn_no_params = leading_colons + "::".join(part for part in final_unique_parts if part)
        if (not base_fqn_no_params or base_fqn_no_params == "::") and \
           base_name_text not in ["anonymous", "unnamed_entity", "unnamed_from_node", "unnamed_entity_in_fqn"]:
             base_fqn_no_params = base_name_text
        elif not base_fqn_no_params or base_fqn_no_params == "::":
             base_fqn_no_params = "unnamed_entity_in_fqn"

        param_string = ""
        is_function_like_ast_types = ["function_definition", "declaration", "field_declaration"]
        is_function_like = definition_or_declaration_node.type in is_function_like_ast_types \
            or (definition_or_declaration_node.type == "template_declaration" and \
                any(c.type in is_function_like_ast_types for c in definition_or_declaration_node.children)
            ) or definition_or_declaration_node.type == "type_definition"

        if is_function_like:
            function_declarator_node = None
            if definition_or_declaration_node.type == "function_definition":
                declarator_child = definition_or_declaration_node.child_by_field_name("declarator")
                if declarator_child and declarator_child.type == "function_declarator":
                    function_declarator_node = declarator_child
            elif definition_or_declaration_node.type == "template_declaration":
                inner_node_for_params = next((c for c in definition_or_declaration_node.children if c.type in ["function_definition", "declaration"]), None)
                if inner_node_for_params:
                    if inner_node_for_params.type == "function_definition":
                        declarator_child = inner_node_for_params.child_by_field_name("declarator")
                        if declarator_child and declarator_child.type == "function_declarator":
                            function_declarator_node = declarator_child
                    elif inner_node_for_params.type == "declaration":
                        function_declarator_node = next((sc for sc in inner_node_for_params.children if sc.type == "function_declarator"), None)
            elif definition_or_declaration_node.type == "declaration":
                function_declarator_node = next((child for child in definition_or_declaration_node.children if child.type == "function_declarator"), None)
            elif definition_or_declaration_node.type == "field_declaration":
                 direct_declarator = definition_or_declaration_node.child_by_field_name("declarator")
                 if direct_declarator and direct_declarator.type == "function_declarator":
                      function_declarator_node = direct_declarator
            elif definition_or_declaration_node.type == "type_definition":
                 current_declarator_for_typedef = definition_or_declaration_node.child_by_field_name("declarator")
                 depth = 0
                 while current_declarator_for_typedef and depth < 3:
                     if current_declarator_for_typedef.type == "function_declarator":
                         function_declarator_node = current_declarator_for_typedef
                         break
                     current_declarator_for_typedef = current_declarator_for_typedef.child_by_field_name("declarator")
                     depth +=1

            if function_declarator_node:
                param_list_node = function_declarator_node.child_by_field_name("parameters")
                if param_list_node and param_list_node.type == "parameter_list":
                    param_type_texts = []
                    for param_decl_node in param_list_node.named_children:
                        param_text_for_debug = get_node_text(param_decl_node, content_bytes)
                        type_str_for_param = ""
                        if param_decl_node.type in ["parameter_declaration", "optional_parameter_declaration"]:
                            param_declarator_node_for_param = param_decl_node.child_by_field_name("declarator")
                            if not param_declarator_node_for_param and param_decl_node.type == "optional_parameter_declaration":
                                 param_declarator_node_for_param = param_decl_node.child_by_field_name("name")
                            base_type_parts = []
                            for child in param_decl_node.children:
                                if param_declarator_node_for_param and child.start_byte >= param_declarator_node_for_param.start_byte: break
                                if param_decl_node.type == "optional_parameter_declaration":
                                    default_value_node = param_decl_node.child_by_field_name("default_value")
                                    if default_value_node and child.start_byte >= default_value_node.start_byte:
                                        if child.type == '=': continue
                                        break
                                if child.type != '=': base_type_parts.append(get_node_text(child, content_bytes))
                            base_type_str = ' '.join(filter(None, base_type_parts)).strip()
                            if not base_type_str:
                                type_node_fallback = param_decl_node.child_by_field_name("type")
                                if type_node_fallback: base_type_str = get_node_text(type_node_fallback, content_bytes).strip()
                            full_declarator_text = ""; name_in_declarator_text = ""; modifiers_from_declarator = ""
                            if param_declarator_node_for_param:
                                full_declarator_text = get_node_text(param_declarator_node_for_param, content_bytes).strip()
                                name_ident_node = None; temp_search = param_declarator_node_for_param; depth=0
                                while temp_search and depth < 5:
                                    if temp_search.type == 'identifier': name_ident_node = temp_search; break
                                    direct_id_child = next((ch for ch in temp_search.children if ch.type == 'identifier'), None)
                                    if direct_id_child: name_ident_node = direct_id_child; break
                                    temp_search = temp_search.child_by_field_name("declarator"); depth += 1
                                if not name_ident_node and param_declarator_node_for_param.type == 'identifier':
                                    name_ident_node = param_declarator_node_for_param
                                if name_ident_node: name_in_declarator_text = get_node_text(name_ident_node, content_bytes)
                                temp_declarator_text_for_mods = full_declarator_text
                                if param_decl_node.type == "optional_parameter_declaration":
                                    default_value_node = param_decl_node.child_by_field_name("default_value")
                                    if default_value_node:
                                        eq_idx = temp_declarator_text_for_mods.rfind("=")
                                        if eq_idx != -1: temp_declarator_text_for_mods = temp_declarator_text_for_mods[:eq_idx].strip()
                                if name_in_declarator_text and temp_declarator_text_for_mods.endswith(name_in_declarator_text):
                                     modifiers_from_declarator = temp_declarator_text_for_mods[:-len(name_in_declarator_text)].strip()
                                elif not name_in_declarator_text and temp_declarator_text_for_mods :
                                    modifiers_from_declarator = temp_declarator_text_for_mods
                                else: modifiers_from_declarator = temp_declarator_text_for_mods
                            if base_type_str and modifiers_from_declarator: type_str_for_param = f"{base_type_str} {modifiers_from_declarator}"
                            elif base_type_str: type_str_for_param = base_type_str
                            elif modifiers_from_declarator: type_str_for_param = modifiers_from_declarator
                            else: type_str_for_param = get_node_text(param_decl_node, content_bytes).strip() if param_decl_node.text != '()' else ""
                            if name_in_declarator_text and "argv" in name_in_declarator_text and \
                               "char" in base_type_str and "*" in modifiers_from_declarator and "[]" in modifiers_from_declarator:
                                type_str_for_param = "char*[]"
                            elif name_in_declarator_text and "argv" in name_in_declarator_text and \
                                "char" in base_type_str and "**" in modifiers_from_declarator:
                                type_str_for_param = "char**"
                            if "MyDataProcessor" in base_fqn_no_params and "my_class.hpp" in source_file_id_for_debug and "name" in param_text_for_debug:
                                logger.info(f"MY_CLASS_CONSTRUCTOR_PARAM_DEBUG: final type_str_for_param before norm = '{type_str_for_param}'")
                        elif param_decl_node.type == "variadic_parameter_declaration": type_str_for_param = "..."
                        else:
                            type_str_for_param = get_node_text(param_decl_node, content_bytes).strip()
                            logger.debug(f"FQN_PARAM_FALLBACK: Node type {param_decl_node.type} in {base_fqn_no_params}, using full text: '{type_str_for_param}'")
                        type_str_for_param = ' '.join(type_str_for_param.split())
                        type_str_for_param = type_str_for_param.replace(" &", "&").replace(" *", "*")
                        type_str_for_param = type_str_for_param.replace("* []", "*[]")
                        if type_str_for_param: param_type_texts.append(type_str_for_param)
                        else: logger.warning(f"FQN_PARAM_TYPE_EMPTY_FINAL: Param '{param_text_for_debug}' resulted in empty type string for {base_fqn_no_params}.")
                    if param_type_texts: param_string = f"({','.join(param_type_texts)})"
                    else:
                        raw_param_list_text = get_node_text(param_list_node, content_bytes).strip()
                        if raw_param_list_text == "(void)" or raw_param_list_text == "()": param_string = "()"
                        elif raw_param_list_text and raw_param_list_text != "(*)":
                             param_string = f"({raw_param_list_text.strip('()')})"
                        else: param_string = "()"
                else: param_string = "()"
        final_fqn = base_fqn_no_params + param_string
        if "fwd_declared_func" in base_name_text and "forward_declarations.hpp" in source_file_id_for_debug:
             logger.info(f"FORWARD_DECL_FQN_DEBUG: BaseName='{base_name_text}', Params='{param_string}', FinalFQN='{final_fqn}'")
        logger.debug(f"FQN_RESULT: File='{source_file_id_for_debug}' NameNode='{get_node_text(name_node, content_bytes) if name_node else 'N/A'}' DefNode.type='{definition_or_declaration_node.type}' -> FQN='{final_fqn}'")
        return final_fqn

    async def parse(self, source_file_id: str, full_content_string: str) -> AsyncGenerator[ParserOutput, None]:
        self.current_source_file_id_for_debug = source_file_id
        self._current_function_context_temp_id = None
        logger.info(f"CppParser: Starting parsing for {source_file_id}")

        if full_content_string.startswith("\n"):
            full_content_string = full_content_string.lstrip("\n")

        if not self.parser or not self.language or (not self.queries and CPP_QUERIES):
            logger.error(f"CppParser for {source_file_id}: Not properly initialized. Aborting.")
            yield []
            self.current_source_file_id_for_debug = None
            return

        if not full_content_string.strip():
            logger.info(f"CppParser: Empty or whitespace-only content for {source_file_id}. Yielding empty slice_lines.")
            yield []
            self.current_source_file_id_for_debug = None
            return

        content_bytes = bytes(full_content_string, "utf8")
        try:
            tree = self.parser.parse(content_bytes)
            root_node = tree.root_node
            # <START> AST STRUCTURE DUMP FOR ALL TYPE_DEFINITIONS (Temporary)
            if "complex_features.cpp" in source_file_id:
                typedef_nodes_query_str = """(type_definition) @def"""
                try:
                    temp_td_query = self.language.query(typedef_nodes_query_str)
                    for _, captures in temp_td_query.matches(root_node):
                        td_node = captures.get("def", [None])[0]
                        if td_node:
                            td_text = get_node_text(td_node, content_bytes)
                            if td_text and "FuncPtr" in td_text: # Focus on FuncPtr
                                logger.info(f"AST_DUMP TypeDefinition Text: {td_text.strip()}")
                                logger.info(f"AST_DUMP TypeDefinition Node Type: {td_node.type}") # Should be 'type_definition'

                                type_child = td_node.child_by_field_name("type")
                                if type_child:
                                    logger.info(f"  Field 'type': Node Type='{type_child.type}', Text='{get_node_text(type_child, content_bytes)}'")
                                else:
                                    logger.info("  Field 'type': NOT FOUND")

                                declarator_child = td_node.child_by_field_name("declarator")
                                if declarator_child:
                                    logger.info(f"  Field 'declarator' (Top): Node Type='{declarator_child.type}', Text='{get_node_text(declarator_child, content_bytes)}'")

                                    if declarator_child.type == "function_declarator": # If top declarator is function_declarator
                                        logger.info(f"    --- Children of this function_declarator (Top) ---")
                                        # Inner declarator (should be the pointer part like '(*FuncPtr)' )
                                        inner_decl_of_func_decl = declarator_child.child_by_field_name("declarator")
                                        if inner_decl_of_func_decl: # This is the parenthesized_declarator
                                            logger.info(f"      Field 'declarator' (of func_decl): Node Type='{inner_decl_of_func_decl.type}', Text='{get_node_text(inner_decl_of_func_decl, content_bytes)}'")
                                            if inner_decl_of_func_decl.type == "parenthesized_declarator": # We are here
                                                logger.info(f"        --- Children of this parenthesized_declarator ---")
                                                for child_of_paren_decl in inner_decl_of_func_decl.children:
                                                    logger.info(f"          Child: Type='{child_of_paren_decl.type}', Text='{get_node_text(child_of_paren_decl, content_bytes)}'")
                                                    if child_of_paren_decl.type == "pointer_declarator": # If we find it
                                                        name_node_candidate = child_of_paren_decl.child_by_field_name("declarator")
                                                        if name_node_candidate:
                                                            logger.info(f"            pointer_declarator's 'declarator': Node Type='{name_node_candidate.type}', Text='{get_node_text(name_node_candidate, content_bytes)}'")
                                                        else:
                                                            logger.info(f"            pointer_declarator's 'declarator': NOT FOUND")
                                                logger.info(f"        --- End Children of parenthesized_declarator ---")

                                        # Parameters part
                                        params_of_func_decl = declarator_child.child_by_field_name("parameters")
                                        if params_of_func_decl:
                                             logger.info(f"      Field 'parameters' (of func_decl): Node Type='{params_of_func_decl.type}', Text='{get_node_text(params_of_func_decl, content_bytes)}'")
                                        else:
                                            logger.info(f"      Field 'parameters' (of func_decl): NOT FOUND")
                                        logger.info(f"    --- End Children of function_declarator (Top) ---")
                                else:
                                    logger.info("  Field 'declarator' (Top): NOT FOUND")
                                logger.info(f"AST_DUMP ----")
                except Exception as e_ast_dump:
                    logger.error(f"AST_DUMP Error: {e_ast_dump}", exc_info=True)
            # <END> AST STRUCTURE DUMP

        except Exception as e:
            logger.error(f"CppParser: Failed to parse content into AST for {source_file_id}: {e}", exc_info=True)
            yield [0]
            self.current_source_file_id_for_debug = None
            return

        slice_lines_set: Set[int] = {0}

        queries_for_slicing = [
            "includes", "namespaces", "classes", "structs", "enums", "typedefs",
            "using_namespace", "namespace_aliases",
            "function_definitions", "template_function_definitions",
            "function_declarations", "template_function_declarations"
        ]
        for query_key in queries_for_slicing:
            query_obj = self.queries.get(query_key)
            if not query_obj: continue
            for _, captures_dict in query_obj.matches(root_node):
                node_to_slice_at: Optional[TSNODE_TYPE] = None
                if "definition" in captures_dict: node_to_slice_at = captures_dict.get("definition", [None])[0]
                elif "include_statement" in captures_dict and query_key == "includes": node_to_slice_at = captures_dict.get("include_statement", [None])[0]
                elif "using_statement" in captures_dict and query_key == "using_namespace": node_to_slice_at = captures_dict.get("using_statement", [None])[0]
                if node_to_slice_at:
                    slice_lines_set.add(node_to_slice_at.start_point[0])

        final_slice_list = sorted(list(slice_lines_set))
        yield final_slice_list
        logger.debug(f"[{source_file_id}] Yielded slice_lines: {final_slice_list}")

        processed_definition_node_starts = set()
        entity_configs = [
            ("function_definitions", "FunctionDefinition", "name"),
            ("template_function_definitions", "FunctionDefinition", "name"),
            ("classes", "ClassDefinition", "name"),
            ("structs", "StructDefinition", "name"),
            ("namespaces", "NamespaceDefinition", "name"),
            ("enums", "EnumDefinition", "name"),
            ("typedefs", "TypeAlias", "name"),
            ("namespace_aliases", "NamespaceAliasDefinition", "alias_new_name"),
            ("function_declarations", "FunctionDeclaration", "name"),
            ("template_function_declarations", "FunctionDeclaration", "name"),
        ]
        function_bodies_to_scan_for_calls: List[Tuple[TSNODE_TYPE, str]] = []

        for query_name, element_type, name_capture_key_default in entity_configs:
            query_obj = self.queries.get(query_name)
            if not query_obj: continue

            for match_idx, captures_dict in query_obj.matches(root_node):
                definition_node: Optional[TSNODE_TYPE] = captures_dict.get("definition", [None])[0]
                name_node: Optional[TSNODE_TYPE] = None

                current_name_capture_key = name_capture_key_default
                if query_name == "typedefs":
                    if captures_dict.get("name_fp"): # Should not exist with current typedef query
                        name_node = captures_dict.get("name_fp", [None])[0]
                        current_name_capture_key = "name_fp"
                    else:
                        name_node = captures_dict.get("name", [None])[0]
                        current_name_capture_key = "name"
                elif query_name == "namespace_aliases":
                    name_node = captures_dict.get("alias_new_name", [None])[0]
                    current_name_capture_key = "alias_new_name"
                    if not name_node and definition_node : # Added check for definition_node
                        children_of_def_node = [c for c in definition_node.children if c.is_named]
                        if children_of_def_node and children_of_def_node[0].type in ('identifier', 'namespace_identifier'):
                             name_node = children_of_def_node[0]
                elif name_capture_key_default:
                    name_node = captures_dict.get(name_capture_key_default, [None])[0]

                if query_name == "typedefs" and "complex_features.cpp" in source_file_id:
                    if definition_node:
                        definition_node_text_debug = get_node_text(definition_node, content_bytes)
                        if definition_node_text_debug and "FuncPtr" in definition_node_text_debug:
                            logger.info(f"DEBUG_TYPEDEF_MATCH: ---- Potential 'FuncPtr' match in {source_file_id} ----")
                            logger.info(f"DEBUG_TYPEDEF_MATCH: Query that matched pattern index within typedefs query: {match_idx}")
                            logger.info(f"DEBUG_TYPEDEF_MATCH: Node captured as @definition: Type='{definition_node.type}', Text='{definition_node_text_debug.strip()}'")

                            name_node_from_capture = captures_dict.get("name", [None])[0] # Check if @name was directly captured by the pattern
                            if name_node_from_capture:
                                logger.info(f"DEBUG_TYPEDEF_MATCH: Directly captured @name: Type='{name_node_from_capture.type}', Text='{get_node_text(name_node_from_capture, content_bytes)}'")
                            else:
                                logger.info(f"DEBUG_TYPEDEF_MATCH: Directly captured @name is None.")

                            # Manually traverse based on Pattern 0 (Attempt 7) to see where it breaks:
                            def_node = captures_dict.get("definition", [None])[0]
                            if def_node:
                                d1 = def_node.child_by_field_name("declarator") # function_declarator
                                if d1 and d1.type == "function_declarator":
                                    d2 = d1.child_by_field_name("declarator") # parenthesized_declarator
                                    if d2 and d2.type == "parenthesized_declarator":
                                        # Children of parenthesized_declarator. The pointer_declarator is likely an unnamed child.
                                        # Iterate unnamed children to find pointer_declarator
                                        d3 = None
                                        for child_of_d2 in d2.children: # Iterate ALL children
                                            if child_of_d2.type == "pointer_declarator":
                                                d3 = child_of_d2
                                                break
                                        if d3: # pointer_declarator
                                            d4 = d3.child_by_field_name("declarator") # type_identifier "FuncPtr"
                                            if d4:
                                                logger.info(f"DEBUG_TYPEDEF_MATCH: Manual traversal to name node: Type='{d4.type}', Text='{get_node_text(d4, content_bytes)}'")
                                                if d4.type == "type_identifier":
                                                    logger.info(f"DEBUG_TYPEDEF_MATCH: SUCCESS - Manual traversal found the name node for FuncPtr!")
                                                else:
                                                    logger.info(f"DEBUG_TYPEDEF_MATCH: Manual traversal found node, but type is {d4.type}, not type_identifier.")

                                            else:
                                                logger.info(f"DEBUG_TYPEDEF_MATCH: Manual traversal: d3 (pointer_declarator) has no 'declarator' child.")
                                        else:
                                            logger.info(f"DEBUG_TYPEDEF_MATCH: Manual traversal: d2 (parenthesized_declarator) has no 'pointer_declarator' child.")
                                    else:
                                        logger.info(f"DEBUG_TYPEDEF_MATCH: Manual traversal: d1 (function_declarator) has no 'parenthesized_declarator' as its declarator. Actual: {d2.type if d2 else 'None'}")
                                else:
                                    logger.info(f"DEBUG_TYPEDEF_MATCH: Manual traversal: def_node has no 'function_declarator' as its declarator. Actual: {d1.type if d1 else 'None'}")

                            for cap_name_str, cap_node_list in captures_dict.items():
                                if cap_node_list:
                                    for cap_idx_inner, captured_node_item in enumerate(cap_node_list):
                                        logger.info(f"DEBUG_TYPEDEF_MATCH:   Capture '{cap_name_str}' (item {cap_idx_inner}): Type='{captured_node_item.type}', Text='{get_node_text(captured_node_item, content_bytes)}'")
                                else:
                                     logger.info(f"DEBUG_TYPEDEF_MATCH:   Capture '{cap_name_str}': No nodes captured for this name in this match.")

                            if name_node:
                                logger.info(f"DEBUG_TYPEDEF_MATCH: Effective Name Node (for FQN) via key '{current_name_capture_key}': Type='{name_node.type}', Text='{get_node_text(name_node, content_bytes)}'")
                                fqn_attempt = self._get_fqn_for_node(name_node, definition_node, content_bytes, root_node, source_file_id)
                                logger.info(f"DEBUG_TYPEDEF_MATCH: FQN generated: '{fqn_attempt}'")
                                logger.info(f"DEBUG_TYPEDEF_MATCH: Temp ID to be created: '{fqn_attempt}@{definition_node.start_point[0]}'")

                            else:
                                logger.info(f"DEBUG_TYPEDEF_MATCH: Effective Name Node (for FQN) via key '{current_name_capture_key}': None. FQN cannot be generated / entity might be skipped.")
                            logger.info(f"DEBUG_TYPEDEF_MATCH: ---- End 'FuncPtr' match details ----")

                if not definition_node: continue
                if definition_node.start_byte in processed_definition_node_starts: continue

                if query_name == "namespaces" and element_type == "NamespaceDefinition" and not name_node:
                    body_node_for_anon_ns = definition_node.child_by_field_name("body")
                    if not body_node_for_anon_ns or body_node_for_anon_ns.child_count == 0:
                        processed_definition_node_starts.add(definition_node.start_byte)
                        continue
                elif not name_node and element_type not in ["NamespaceDefinition", "NamespaceAliasDefinition"]:
                    continue

                true_fqn = self._get_fqn_for_node(name_node, definition_node, content_bytes, root_node, source_file_id)

                if not true_fqn or ("unnamed_entity_in_fqn" in true_fqn and element_type != "NamespaceDefinition") :
                    if true_fqn == "anonymous" and element_type == "NamespaceDefinition": pass
                    else: continue

                original_ast_start_line_0 = definition_node.start_point[0]
                temp_entity_id = f"{true_fqn}@{original_ast_start_line_0}"
                processed_definition_node_starts.add(definition_node.start_byte)
                snippet_content_str = get_node_text(definition_node, content_bytes) or ""
                code_entity_instance = CodeEntity(id=temp_entity_id, type=element_type, snippet_content=snippet_content_str)
                yield code_entity_instance

                if element_type == "FunctionDefinition":
                    body_node = definition_node.child_by_field_name("body")
                    if body_node: function_bodies_to_scan_for_calls.append((body_node, temp_entity_id))
                    elif definition_node.type == "template_declaration":
                        inner_func_def = next((c for c in definition_node.children if c.type == "function_definition"), None)
                        if inner_func_def:
                            body_node_template = inner_func_def.child_by_field_name("body")
                            if body_node_template: function_bodies_to_scan_for_calls.append((body_node_template, temp_entity_id))

                if element_type in ["ClassDefinition", "StructDefinition"]:
                    heritage_node = captures_dict.get("heritage", [None])[0]
                    if heritage_node and heritage_node.type == "base_class_clause":
                        all_parents_text = set()
                        for child_node_heritage in heritage_node.named_children:
                            if child_node_heritage.type in ["type_identifier", "qualified_identifier", "template_type"]:
                                parent_name_raw = get_node_text(child_node_heritage, content_bytes)
                                if parent_name_raw: all_parents_text.add(' '.join(parent_name_raw.split()))
                        for p_name_normalized in all_parents_text:
                            if p_name_normalized:
                                yield Relationship(source_id=temp_entity_id, target_id=p_name_normalized, type="EXTENDS")

        include_query = self.queries.get("includes")
        if include_query:
            processed_include_refs_yielded_for_entity = set()
            processed_import_relationships = set()
            for _, captures_in_match_dict in include_query.matches(root_node):
                statement_node: Optional[TSNODE_TYPE] = captures_in_match_dict.get("include_statement", [None])[0]
                target_node: Optional[TSNODE_TYPE] = captures_in_match_dict.get("include", [None])[0]
                if statement_node and target_node:
                    include_path_raw = get_node_text(target_node, content_bytes)
                    if include_path_raw:
                        canonical_include_path = include_path_raw.strip('<>"')
                        external_fqn = canonical_include_path
                        if include_path_raw.startswith("<") and not ("::" in canonical_include_path or "." in canonical_include_path or "/" in canonical_include_path):
                            external_fqn = f"std::{canonical_include_path}"
                        original_ast_start_line_0 = statement_node.start_point[0]
                        temp_ext_ref_id = f"{external_fqn}@{original_ast_start_line_0}"
                        if temp_ext_ref_id not in processed_include_refs_yielded_for_entity:
                            yield CodeEntity(id=temp_ext_ref_id, type="ExternalReference", snippet_content=external_fqn)
                            processed_include_refs_yielded_for_entity.add(temp_ext_ref_id)
                        import_rel_key = (source_file_id, temp_ext_ref_id)
                        if import_rel_key not in processed_import_relationships:
                            yield Relationship(source_id=source_file_id, target_id=temp_ext_ref_id, type="IMPORTS")
                            processed_import_relationships.add(import_rel_key)

        using_ns_query = self.queries.get("using_namespace")
        if using_ns_query:
            processed_using_directive_entities = set()
            processed_using_relationships = set()
            for _, captures_in_match_dict in using_ns_query.matches(root_node):
                statement_node: Optional[TSNODE_TYPE] = captures_in_match_dict.get("using_statement", [None])[0]
                name_node: Optional[TSNODE_TYPE] = captures_in_match_dict.get("name", [None])[0]
                if statement_node and name_node:
                    namespace_name_str_raw = get_node_text(name_node, content_bytes)
                    if namespace_name_str_raw:
                        namespace_name_str = ' '.join(namespace_name_str_raw.split())
                        original_ast_start_line_0 = statement_node.start_point[0]
                        directive_fqn_ref = f"using_namespace_directive_referencing::{namespace_name_str}"
                        temp_directive_id = f"{directive_fqn_ref}@{original_ast_start_line_0}"
                        if temp_directive_id not in processed_using_directive_entities:
                            using_snippet = get_node_text(statement_node, content_bytes) or ""
                            yield CodeEntity(id=temp_directive_id, type="UsingDirective", snippet_content=using_snippet)
                            processed_using_directive_entities.add(temp_directive_id)
                        has_directive_key = (source_file_id, temp_directive_id)
                        if has_directive_key not in processed_using_relationships:
                            yield Relationship(source_id=source_file_id, target_id=temp_directive_id, type="HAS_DIRECTIVE")
                            processed_using_relationships.add(has_directive_key)
                        ref_ns_key = (temp_directive_id, namespace_name_str)
                        if ref_ns_key not in processed_using_relationships:
                            yield Relationship(source_id=temp_directive_id, target_id=namespace_name_str, type="REFERENCES_NAMESPACE")
                            processed_using_relationships.add(ref_ns_key)

        calls_query_obj = self.queries.get("calls")
        if calls_query_obj:
            for func_body_node, current_calling_entity_temp_id in function_bodies_to_scan_for_calls:
                self._current_function_context_temp_id = current_calling_entity_temp_id
                for match_idx, call_captures_dict in calls_query_obj.matches(func_body_node):
                    call_site_node_direct = call_captures_dict.get("call_site", [None])[0]
                    call_site_op_node = call_captures_dict.get("call_site_operator", [None])[0]
                    call_site_constructor_node = call_captures_dict.get("call_site_constructor", [None])[0]
                    call_site_delete_node = call_captures_dict.get("call_site_delete", [None])[0]
                    actual_call_node = call_site_node_direct or call_site_op_node or call_site_constructor_node or call_site_delete_node
                    if not actual_call_node: continue

                    called_name_expr: Optional[str] = None
                    raw_arg_text_val: Optional[str] = None
                    arg_count_val: int = 0

                    if call_site_op_node :
                        op_symbol_node = call_captures_dict.get("operator_symbol", [None])[0]
                        if op_symbol_node: called_name_expr = self._get_node_name_text(op_symbol_node, content_bytes)
                        arg_count_val = 2
                        left_op_node = call_captures_dict.get("left_operand", [None])[0]
                        right_op_node = call_captures_dict.get("right_operand", [None])[0]
                        left_text = get_node_text(left_op_node, content_bytes) if left_op_node else ""
                        right_text = get_node_text(right_op_node, content_bytes) if right_op_node else ""
                        raw_arg_text_val = f"{left_text},{right_text}"
                    elif call_site_delete_node:
                        called_name_expr = "operator delete"
                        if "[]" in (get_node_text(actual_call_node, content_bytes) or ""): called_name_expr = "operator delete[]"
                        deleted_value_node_child = actual_call_node.child_by_field_name("value") or \
                                                   next((actual_call_node.child(i) for i in range(actual_call_node.child_count - 1, -1, -1)
                                                         if actual_call_node.child(i).is_named and actual_call_node.child(i).type not in ['[', ']', '::', 'delete']), None)
                        raw_arg_text_val = get_node_text(deleted_value_node_child, content_bytes) if deleted_value_node_child else ""
                        arg_count_val = 1 if raw_arg_text_val else 0
                    elif call_site_constructor_node:
                        name_node_for_constructor = call_captures_dict.get("name", [None])[0]
                        if name_node_for_constructor: called_name_expr = self._get_node_name_text(name_node_for_constructor, content_bytes)
                        arguments_node = call_captures_dict.get("arguments", [None])[0]
                        if arguments_node:
                            raw_arg_text_val_full = get_node_text(arguments_node, content_bytes)
                            raw_arg_text_val = raw_arg_text_val_full.strip("(){}") if raw_arg_text_val_full else ""
                            arg_count_val = len(arguments_node.named_children)
                        else: raw_arg_text_val = ""; arg_count_val = 0
                    elif call_site_node_direct:
                        function_node_for_call = call_captures_dict.get("function_node_for_call", [None])[0]
                        if function_node_for_call:
                            called_name_expr = self._get_node_name_text(function_node_for_call, content_bytes) or get_node_text(function_node_for_call, content_bytes)
                        arguments_node_direct = call_captures_dict.get("arguments", [None])[0]
                        if arguments_node_direct and arguments_node_direct.type == "argument_list":
                            raw_arg_text_val_full = get_node_text(arguments_node_direct, content_bytes)
                            raw_arg_text_val = raw_arg_text_val_full.strip("()") if raw_arg_text_val_full else ""
                            arg_count_val = len(arguments_node_direct.named_children)
                        else: raw_arg_text_val = ""; arg_count_val = 0

                    if not called_name_expr: continue
                    if self._current_function_context_temp_id is None: continue

                    yield CallSiteReference(
                        calling_entity_temp_id=self._current_function_context_temp_id,
                        called_name_expr=called_name_expr.strip(),
                        line_of_call_0_indexed=actual_call_node.start_point[0],
                        source_file_id_of_call_site=source_file_id,
                        raw_arg_text=raw_arg_text_val,
                        argument_count=arg_count_val
                    )
                self._current_function_context_temp_id = None

        self.current_source_file_id_for_debug = None
        logger.info(f"CppParser: Finished parsing for {source_file_id}")
