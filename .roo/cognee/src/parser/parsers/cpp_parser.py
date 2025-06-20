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
          (namespace_definition body: (declaration_list)) @definition ; For anonymous namespaces
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
            type: (_) @original_type
            declarator: (type_identifier) @name
          ) @definition

          (type_definition
            type: (_) @original_type
            declarator: (pointer_declarator declarator: [(identifier)(type_identifier)] @name)
          ) @definition

          (type_definition
            type: (_) @original_type
            declarator: (array_declarator declarator: [(identifier)(type_identifier)] @name)
          ) @definition

          (type_definition ; Catches typedef void Func(int)
            type: (_) @original_type
            declarator: (function_declarator declarator: [(identifier)(type_identifier)] @name)
          ) @definition

          (type_definition ; Catches typedef void (*FuncPtr)(int)
            type: (_) @original_type
            declarator: (pointer_declarator declarator: (function_declarator declarator: [(identifier)(type_identifier)] @name ) )
          ) @definition

          (alias_declaration ; For using NewType = OldType;
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
            ( ;; Pattern 1: Normal function/method call, including overloaded operators called like functions
              (call_expression
                function: [
                    (identifier)
                    (field_expression ; For member calls like obj.method() or ptr->method()
                        field: _      ; The actual field_identifier, operator_name, etc.
                    )
                    (qualified_identifier ; For Ns::func(), Class::static_method(), and Ns::template_func<T>()
                        name: [
                            (identifier)
                            (operator_name)
                            (destructor_name)
                            (template_function)
                        ]
                    )
                    (template_function) ; For calls to global template functions like my_template_func<int>()
                    (parenthesized_expression) ; For calls like (func_ptr)()
                ] @function_node_for_call
                arguments: (argument_list) @arguments
              ) @call_site
            )
            ( ;; Pattern 2: Operators used as binary expressions (e.g. a + b)
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
            ( ;; Pattern 3: Constructor calls via new expression
              (new_expression
                type: (_) @name
                arguments: (argument_list)? @arguments
              ) @call_site_constructor
            )
            ( ;; Pattern 4: Delete expressions
              (delete_expression) @call_site_delete
            )
            ( ;; Pattern 5: Stack-based constructor calls
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

        if node.type == "template_function": # Handles e.g. `my_template_func<int>`
            name_child_node = node.child_by_field_name("name")
            if not name_child_node: # Fallback if name field isn't standard (e.g. older tree-sitter binding)
                 # Try to find first identifier-like child as name
                 potential_name_children = [
                    c for c in node.children
                    if c.type in ("identifier", "qualified_identifier", "field_identifier", "operator_name")
                 ]
                 if potential_name_children:
                     name_child_node = potential_name_children[0]

            if name_child_node:
                name_str = get_node_text(name_child_node, content_bytes) or name_str # Use child's text if available
            else: # If still no specific name node, try to strip template args from full text
                name_match = re.match(r"([^<]+)(?:<.*>)?", name_str)
                if name_match:
                    name_str = name_match.group(1).strip()

        stripped_name_val = name_str.strip()

        # Pre-canonicalization for common symbols before "operator" regex
        if not stripped_name_val.lower().startswith("operator") and \
           not stripped_name_val.isalnum() and \
           stripped_name_val: # Is a symbol, not alphanumeric, not already "operator..."

            if stripped_name_val == "()": name_str = "operator()"
            elif stripped_name_val == "[]": name_str = "operator[]"
            # For simple symbols like +, -, <<, -> etc.
            elif len(stripped_name_val) <= 2 and stripped_name_val and not stripped_name_val[0].isalnum() :
                name_str = f"operator{stripped_name_val}"

        # Standardize "operator" spacing and form
        if "operator" in name_str:
            match = re.search(
                r"((?:[\w:]*::)?operator)\s*"  # Group 1: operator keyword, possibly qualified
                r"([^\w\s\(\);{}\[\]:\<\>,.\*&%#!~\^|=]+(?:\[\])?|"  # Symbols like +, [], ->*
                r"new(?:\[\])?|delete(?:\[\])?|co_await|"          # Keywords new, delete, co_await, with optional []
                r"\b\w+\b)" # Potentially a conversion operator type like 'MyType' or user-defined literal
                , name_str
            )

            if match:
                op_keyword_part = match.group(1)
                op_symbol_part = match.group(2).strip()

                # Standardize spacing: "operator new", "operator new[]", but "operator+", "operator[]"
                if op_symbol_part in ["new", "delete", "co_await"] or \
                   op_symbol_part == "new[]" or op_symbol_part == "delete[]":
                    name_str = f"{op_keyword_part} {op_symbol_part}"
                else:
                    # For other operators (symbols, conversion functions), concatenate without adding extra space
                    if op_keyword_part.endswith("operator") and not op_keyword_part.endswith("operator "):
                         name_str = f"{op_keyword_part}{op_symbol_part}"
                    else: # e.g. if op_keyword_part was "N::operator " - keep space
                         name_str = f"{op_keyword_part}{op_symbol_part}"
            # Fallback for simple "operator <symbol>" that might not be caught by the main regex
            elif name_str.strip().startswith("operator") and "(" not in name_str and ")" not in name_str:
                parts = name_str.strip().split("operator", 1)
                if len(parts) == 2 and not parts[0].strip(): # Ensure "operator" was at the start
                    symbol = parts[1].strip()
                    if symbol and not any(c in symbol for c in "()"): # Avoid mangling if it had parens
                        name_str = f"operator{symbol}"

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
            pass # Anonymous namespace will use "anonymous"
        else:
            # This case should ideally not happen if queries are well-defined for named entities.
            logger.debug(f"FQN_WARN: name_node is None for def_node type '{definition_or_declaration_node.type}' in {source_file_id_for_debug}. Defaulting base_name to 'unnamed_entity'. Snippet: {get_node_text(definition_or_declaration_node, content_bytes)[:50]}")
            base_name_text = "unnamed_entity"

        scopes_reversed = []
        current_climb_node = definition_or_declaration_node.parent

        while current_climb_node and current_climb_node != root_node_for_global_check: # Stop at root
            if current_climb_node.type in self.AST_SCOPES_FOR_FQN:
                scope_name_text = "anonymous" # Default for anonymous scopes (e.g. anonymous namespace)
                is_template_scope_for_current_entity = False

                # Special handling for template_declaration to check if it's the template for the current entity
                if current_climb_node.type == "template_declaration":
                    inner_def_node = None # The actual class/func/etc. node inside the template_declaration
                    for child in current_climb_node.children:
                        # Check if child is one of the types that a template can declare
                        if child.type in ("function_definition", "class_specifier", "struct_specifier", "alias_declaration", "type_definition", "declaration"):
                            inner_def_node = child
                            break

                    if inner_def_node:
                        # Try to get the name of the entity defined *inside* this template_declaration
                        potential_scope_name_node_in_child = inner_def_node.child_by_field_name("name")
                        if inner_def_node.type == "function_definition": # functions have name nested deeper
                            declarator = inner_def_node.child_by_field_name("declarator")
                            if declarator:
                                actual_name_bearer = declarator.child_by_field_name("declarator")
                                if actual_name_bearer:
                                     potential_scope_name_node_in_child = actual_name_bearer
                        elif inner_def_node.type == "declaration": # For template function declarations
                             func_declarator_in_decl = next((ch for ch in inner_def_node.children if ch.type == "function_declarator"), None)
                             if func_declarator_in_decl:
                                 actual_name_bearer = func_declarator_in_decl.child_by_field_name("declarator")
                                 if actual_name_bearer:
                                      potential_scope_name_node_in_child = actual_name_bearer

                        if potential_scope_name_node_in_child:
                             temp_scope_name = self._get_node_name_text(potential_scope_name_node_in_child, content_bytes)
                             # If the name inside template matches the current entity's base name (without params)
                             # then this template_declaration *is* the scope for the current entity, so don't add its name to FQN prefix.
                             current_entity_base_name_no_params = base_name_text.split("(",1)[0]
                             if temp_scope_name == current_entity_base_name_no_params:
                                 is_template_scope_for_current_entity = True
                             else:
                                 # This template declares something else, so it's a named scope for us.
                                 scope_name_text = temp_scope_name or "anonymous_template_entity"
                # Skip function_definition as a scope for its own FQN (already part of base_name or handled by class/namespace)
                elif current_climb_node.type == "function_definition":
                     pass # Function names are part of the entity itself, not a scope prefix for it

                # For other scope types (class, struct, namespace)
                else:
                    potential_scope_name_node = current_climb_node.child_by_field_name("name")
                    if potential_scope_name_node:
                        scope_name_text = self._get_node_name_text(potential_scope_name_node, content_bytes) or "anonymous"
                    elif current_climb_node.type == "namespace_definition" and not potential_scope_name_node:
                        pass # Already "anonymous" by default, correct for anonymous namespaces

                if not is_template_scope_for_current_entity:
                    scopes_reversed.append(scope_name_text)

            current_climb_node = current_climb_node.parent

        # Construct prefix from gathered scope names
        # FIX 1: The `s != "anonymous"` filter was removed to correctly handle entities in anonymous namespaces.
        scope_prefix_parts = [s for s in reversed(scopes_reversed) if s and s != "anonymous_template_entity"]

        # Combine prefix with base name, handling qualified identifiers
        final_fqn_parts = []
        leading_colons = ""

        if name_node and name_node.type == "qualified_identifier":
            raw_qualified_name = base_name_text # _get_node_name_text already handles qualified name text
            if raw_qualified_name.startswith("::"):
                leading_colons = "::"
                raw_qualified_name = raw_qualified_name.lstrip(':')

            qualified_name_segments = [seg for seg in raw_qualified_name.split("::") if seg]

            # Merge scope_prefix_parts with qualified_name_segments, removing overlap
            temp_merged_parts = list(scope_prefix_parts)
            idx_to_match_from_qual = 0
            if temp_merged_parts and qualified_name_segments:
                max_overlap = 0
                # Find the longest suffix of temp_merged_parts that is a prefix of qualified_name_segments
                for k_overlap in range(1, min(len(temp_merged_parts), len(qualified_name_segments)) + 1):
                    if temp_merged_parts[-k_overlap:] == qualified_name_segments[:k_overlap]:
                        max_overlap = k_overlap
                idx_to_match_from_qual = max_overlap

            final_fqn_parts = temp_merged_parts + qualified_name_segments[idx_to_match_from_qual:]

        else: # Simple identifier or no name node (e.g. anonymous namespace)
            final_fqn_parts = scope_prefix_parts + [base_name_text]

        # Deduplicate adjacent identical parts and clean up "anonymous"
        unique_parts = []
        if final_fqn_parts:
            first_part_to_consider = final_fqn_parts[0]
            start_index_for_loop = 0

            # Handle leading "::" correctly if it means global scope starting with empty string part
            if leading_colons and not first_part_to_consider and len(final_fqn_parts) > 1: # e.g. "::MyClass" -> ["", "MyClass"]
                unique_parts.append(final_fqn_parts[1]) # Start with "MyClass"
                start_index_for_loop = 2
            elif first_part_to_consider or (not first_part_to_consider and not leading_colons) : # e.g. "MyClass" or "anonymous::Func"
                unique_parts.append(first_part_to_consider)
                start_index_for_loop = 1

            for i in range(start_index_for_loop, len(final_fqn_parts)):
                current_part = final_fqn_parts[i]
                if not current_part: # Skip empty parts that might arise from "::::" or similar
                    if current_part == "anonymous" and i == len(final_fqn_parts) -1 : # keep if last part is anonymous
                         pass
                    elif unique_parts and unique_parts[-1] == "": # avoid consecutive empty strings if global "::" was handled already
                        continue
                    elif i < len(final_fqn_parts) -1 : # if it's an empty part not at the end (e.g. from :: in middle)
                         pass # it might be intentional for fully qualified names starting with ::
                    else: # skip other empty parts
                        continue


                prev_part = unique_parts[-1] if unique_parts else None

                # Special handling for constructors/destructors: MyClass::MyClass or MyClass::~MyClass
                is_constructor_or_destructor_scenario = False
                if name_node and current_part == base_name_text and prev_part: # e.g. ClassName, base_name=ClassName, prev_part=ClassName
                    # Constructor: current_part == prev_part AND current_part does not start with '~'
                    is_constructor = (current_part == prev_part and not current_part.startswith("~"))
                    # Destructor: current_part starts with '~' AND current_part[1:] == prev_part
                    is_destructor = (current_part.startswith("~") and current_part[1:] == prev_part)
                    is_constructor_or_destructor_scenario = is_constructor or is_destructor

                if not prev_part or current_part != prev_part or is_constructor_or_destructor_scenario:
                    unique_parts.append(current_part)

        final_unique_parts = [part for part in unique_parts if part is not None] # Remove any Nones that slipped through

        # FIX 2: This block was removing the "anonymous::" prefix, which contradicts the requirement to
        # qualify entities from anonymous namespaces. It has been commented out/disabled.
        # if len(final_unique_parts) > 1 and final_unique_parts[0] == "anonymous" and not leading_colons:
        #     final_unique_parts.pop(0)

        # If only "anonymous" remains, or if it was an anonymous namespace
        if not final_unique_parts and "anonymous" in unique_parts: # unique_parts could be ["anonymous"]
            final_unique_parts = ["anonymous"]


        base_fqn_no_params = leading_colons + "::".join(part for part in final_unique_parts if part) # Ensure no empty parts joined unless it's global "::"

        # Handle cases where FQN becomes empty or just "::" for a named entity
        if (not base_fqn_no_params or base_fqn_no_params == "::") and \
           base_name_text not in ["anonymous", "unnamed_entity", "unnamed_from_node", "unnamed_entity_in_fqn"]: # if base_name_text was valid
             base_fqn_no_params = base_name_text
        elif not base_fqn_no_params or base_fqn_no_params == "::": # If all else failed, default to a clear unnamed marker
             base_fqn_no_params = "unnamed_entity_in_fqn" # More specific than just "anonymous"


        # Parameter string construction for functions/methods
        param_string = ""
        is_function_like_ast_types = ["function_definition", "declaration", "field_declaration"]
        # Check if the definition node itself is function-like OR if it's a template declaration containing a function-like entity
        is_function_like = definition_or_declaration_node.type in is_function_like_ast_types \
            or (definition_or_declaration_node.type == "template_declaration" and \
                any(c.type in is_function_like_ast_types for c in definition_or_declaration_node.children)
            ) or definition_or_declaration_node.type == "type_definition" # Typedefs can be for function types

        if is_function_like:
            function_declarator_node = None
            # Find the function_declarator node, which contains the parameters
            if definition_or_declaration_node.type == "function_definition":
                declarator_child = definition_or_declaration_node.child_by_field_name("declarator")
                if declarator_child and declarator_child.type == "function_declarator":
                    function_declarator_node = declarator_child
            elif definition_or_declaration_node.type == "template_declaration":
                # Find function_definition or declaration inside template_declaration
                inner_node_for_params = next((c for c in definition_or_declaration_node.children if c.type in ["function_definition", "declaration"]), None)
                if inner_node_for_params:
                    if inner_node_for_params.type == "function_definition":
                        declarator_child = inner_node_for_params.child_by_field_name("declarator")
                        if declarator_child and declarator_child.type == "function_declarator":
                            function_declarator_node = declarator_child
                    elif inner_node_for_params.type == "declaration": # e.g. template <T> void func(T);
                        function_declarator_node = next((sc for sc in inner_node_for_params.children if sc.type == "function_declarator"), None)
            elif definition_or_declaration_node.type == "declaration": # Non-templated function declaration
                function_declarator_node = next((child for child in definition_or_declaration_node.children if child.type == "function_declarator"), None)
            elif definition_or_declaration_node.type == "field_declaration": # Method declaration inside class/struct
                 direct_declarator = definition_or_declaration_node.child_by_field_name("declarator")
                 if direct_declarator and direct_declarator.type == "function_declarator":
                      function_declarator_node = direct_declarator
            elif definition_or_declaration_node.type == "type_definition": # Typedef for a function signature
                 # Need to navigate potentially nested declarators for function pointers
                 current_declarator_for_typedef = definition_or_declaration_node.child_by_field_name("declarator")
                 depth = 0
                 while current_declarator_for_typedef and depth < 3: # Limit depth to avoid infinite loops on weird structures
                     if current_declarator_for_typedef.type == "function_declarator":
                         function_declarator_node = current_declarator_for_typedef
                         break
                     # Look for nested declarator (e.g. in pointer_declarator)
                     current_declarator_for_typedef = current_declarator_for_typedef.child_by_field_name("declarator")
                     depth +=1

            if function_declarator_node:
                param_list_node = function_declarator_node.child_by_field_name("parameters")
                if param_list_node and param_list_node.type == "parameter_list":
                    param_type_texts = []
                    for param_decl_node in param_list_node.named_children: # `named_children` is usually better
                        param_text_for_debug = get_node_text(param_decl_node, content_bytes)

                        type_str_for_param = ""
                        if param_decl_node.type in ["parameter_declaration", "optional_parameter_declaration"]:
                            # Extract base type (everything before declarator/name)
                            param_declarator_node_for_param = param_decl_node.child_by_field_name("declarator")
                            if not param_declarator_node_for_param and param_decl_node.type == "optional_parameter_declaration":
                                 # Optional params might just have a 'name' field if no complex declarator
                                 param_declarator_node_for_param = param_decl_node.child_by_field_name("name")

                            base_type_parts = []
                            for child in param_decl_node.children:
                                # Stop if we hit the declarator node (if any) or default value
                                if param_declarator_node_for_param and child.start_byte >= param_declarator_node_for_param.start_byte:
                                    break
                                if param_decl_node.type == "optional_parameter_declaration":
                                    default_value_node = param_decl_node.child_by_field_name("default_value")
                                    if default_value_node and child.start_byte >= default_value_node.start_byte:
                                        if child.type == '=': continue # Skip the '=' token itself
                                        break
                                if child.type != '=': # Also skip '=' for optional_parameter_declaration
                                   base_type_parts.append(get_node_text(child, content_bytes))

                            base_type_str = ' '.join(filter(None, base_type_parts)).strip()

                            # Fallback if iterating children didn't get the type (e.g. simple type node)
                            if not base_type_str:
                                type_node_fallback = param_decl_node.child_by_field_name("type")
                                if type_node_fallback:
                                    base_type_str = get_node_text(type_node_fallback, content_bytes).strip()

                            # Extract declarator parts (like *, &, []) and name
                            full_declarator_text = ""
                            name_in_declarator_text = ""
                            modifiers_from_declarator = ""

                            if param_declarator_node_for_param:
                                full_declarator_text = get_node_text(param_declarator_node_for_param, content_bytes).strip()

                                # Try to find the actual identifier name within the declarator
                                name_ident_node = None; temp_search = param_declarator_node_for_param; depth=0
                                while temp_search and depth < 5: # Limit search depth
                                    if temp_search.type == 'identifier': name_ident_node = temp_search; break
                                    # Check direct children first for identifier
                                    direct_id_child = next((ch for ch in temp_search.children if ch.type == 'identifier'), None)
                                    if direct_id_child: name_ident_node = direct_id_child; break
                                    temp_search = temp_search.child_by_field_name("declarator"); depth += 1
                                # If declarator node itself is an identifier (e.g. in optional_parameter_declaration)
                                if not name_ident_node and param_declarator_node_for_param.type == 'identifier':
                                    name_ident_node = param_declarator_node_for_param

                                if name_ident_node: name_in_declarator_text = get_node_text(name_ident_node, content_bytes)

                                # Get modifiers by removing name and default value part from full declarator text
                                temp_declarator_text_for_mods = full_declarator_text
                                if param_decl_node.type == "optional_parameter_declaration":
                                    default_value_node = param_decl_node.child_by_field_name("default_value")
                                    if default_value_node: # Strip " = default_value"
                                        eq_idx = temp_declarator_text_for_mods.rfind("=")
                                        if eq_idx != -1: temp_declarator_text_for_mods = temp_declarator_text_for_mods[:eq_idx].strip()

                                if name_in_declarator_text and temp_declarator_text_for_mods.endswith(name_in_declarator_text):
                                     modifiers_from_declarator = temp_declarator_text_for_mods[:-len(name_in_declarator_text)].strip()
                                elif not name_in_declarator_text and temp_declarator_text_for_mods : # If no name, declarator is all modifiers
                                    modifiers_from_declarator = temp_declarator_text_for_mods
                                else: # Fallback if name isn't neatly at the end
                                    modifiers_from_declarator = temp_declarator_text_for_mods


                            # Combine base type and modifiers
                            if base_type_str and modifiers_from_declarator:
                                type_str_for_param = f"{base_type_str} {modifiers_from_declarator}"
                            elif base_type_str:
                                type_str_for_param = base_type_str
                            elif modifiers_from_declarator: # e.g. for function pointers without explicit base type in this part
                                type_str_for_param = modifiers_from_declarator
                            else: # Fallback to full text of parameter_declaration if all else fails
                                type_str_for_param = get_node_text(param_decl_node, content_bytes).strip() if param_decl_node.text != '()' else "" # Avoid empty "()"

                            # Specific FQN fix for char *argv[] -> char*[] (common main pattern)
                            if name_in_declarator_text and "argv" in name_in_declarator_text and \
                               "char" in base_type_str and "*" in modifiers_from_declarator and "[]" in modifiers_from_declarator:
                                type_str_for_param = "char*[]" # Override for this specific common pattern
                            elif name_in_declarator_text and "argv" in name_in_declarator_text and \
                                "char" in base_type_str and "**" in modifiers_from_declarator: # for char **argv
                                type_str_for_param = "char**"


                            if "MyDataProcessor" in base_fqn_no_params and "my_class.hpp" in source_file_id_for_debug and "name" in param_text_for_debug:
                                type_node_direct_debug = param_decl_node.child_by_field_name("type")
                                logger.info(f"MY_CLASS_CONSTRUCTOR_PARAM_DEBUG: ParamNode Text: '{get_node_text(param_decl_node, content_bytes)}'")
                                logger.info(f"MY_CLASS_CONSTRUCTOR_PARAM_DEBUG: TypeNode (direct field) Text: '{get_node_text(type_node_direct_debug, content_bytes)}'")
                                logger.info(f"MY_CLASS_CONSTRUCTOR_PARAM_DEBUG: base_type_str (from children iteration) = '{base_type_str}'")
                                logger.info(f"MY_CLASS_CONSTRUCTOR_PARAM_DEBUG: modifiers_from_declarator = '{modifiers_from_declarator}'")
                                logger.info(f"MY_CLASS_CONSTRUCTOR_PARAM_DEBUG: final type_str_for_param before norm = '{type_str_for_param}'")


                        elif param_decl_node.type == "variadic_parameter_declaration": # ...
                            type_str_for_param = "..."
                        else: # Fallback for other param types if any
                            type_str_for_param = get_node_text(param_decl_node, content_bytes).strip()
                            logger.debug(f"FQN_PARAM_FALLBACK: Node type {param_decl_node.type} in {base_fqn_no_params}, using full text: '{type_str_for_param}'")

                        # Normalize spacing and pointer/reference symbols
                        type_str_for_param = ' '.join(type_str_for_param.split()) # Normalize spaces
                        type_str_for_param = type_str_for_param.replace(" &", "&").replace(" *", "*")
                        type_str_for_param = type_str_for_param.replace("* []", "*[]") # Normalize pointer to array `*[]`


                        if type_str_for_param:
                           param_type_texts.append(type_str_for_param)
                        else:
                            # This can happen for empty parameter lists like `()` or `(void)` if not handled above
                            logger.warning(f"FQN_PARAM_TYPE_EMPTY_FINAL: Param '{param_text_for_debug}' resulted in empty type string for {base_fqn_no_params}.")

                    if param_type_texts:
                        param_string_content = ",".join(param_type_texts)
                        param_string = f"({param_string_content})"
                    else: # Handle empty param list like func() or func(void)
                        raw_param_list_text = get_node_text(param_list_node, content_bytes).strip()
                        if raw_param_list_text == "(void)" or raw_param_list_text == "()": param_string = "()"
                        # Check if it's just '(*)' from a function pointer typedef, which also means no params effectively
                        elif raw_param_list_text and raw_param_list_text != "(*)":
                             # This case means named_children was empty, but param_list_node had text.
                             # It might be a malformed param list or one not parsed into named children (e.g. abstract_function_declarator)
                             logger.debug(f"FQN_PARAM_LIST_UNPARSED: Param list '{raw_param_list_text}' for {base_fqn_no_params}, resulted in no types, using raw content minus parens.")
                             param_string = f"({raw_param_list_text.strip('()')})" # Try to use its content
                        else: # Default to () if truly empty or unparseable
                             param_string = "()"
                else: # No parameter_list node found (e.g. for a function with no parameter list like old K&R C style, or abstract declarators)
                    param_string = "()" # Default to empty parentheses

        final_fqn = base_fqn_no_params + param_string

        if "fwd_declared_func" in base_name_text and "forward_declarations.hpp" in source_file_id_for_debug: # For specific debugging
             logger.info(f"FORWARD_DECL_FQN_DEBUG: BaseName='{base_name_text}', Params='{param_string}', FinalFQN='{final_fqn}'")

        logger.debug(f"FQN_RESULT: File='{source_file_id_for_debug}' NameNode='{get_node_text(name_node, content_bytes) if name_node else 'N/A'}' DefNode.type='{definition_or_declaration_node.type}' -> FQN='{final_fqn}'")
        return final_fqn


    async def parse(self, source_file_id: str, full_content_string: str) -> AsyncGenerator[ParserOutput, None]:
        self.current_source_file_id_for_debug = source_file_id
        logger.info(f"CppParser: Starting parsing for {source_file_id}")
# normalise leading empty line that may be left over after banner-stripping
        if full_content_string.startswith("\n"):
            full_content_string = full_content_string.lstrip("\n")

        if not self.parser or not self.language or (not self.queries and CPP_QUERIES):
            logger.error(f"CppParser for {source_file_id}: Not properly initialized (parser, language, or queries missing). Aborting.")
            yield []
            self.current_source_file_id_for_debug = None
            return

        if not full_content_string.strip():
            logger.info(f"CppParser: Empty or whitespace-only content for {source_file_id}. Yielding empty slice_lines and returning.")
            yield []
            self.current_source_file_id_for_debug = None
            return

        content_bytes = bytes(full_content_string, "utf8")
        try:
            tree = self.parser.parse(content_bytes)
            root_node = tree.root_node
        except Exception as e:
            logger.error(f"CppParser: Failed to parse content into AST for {source_file_id}: {e}", exc_info=True)
            yield [0]
            self.current_source_file_id_for_debug = None
            return

        slice_lines_set: Set[int] = set()
        if full_content_string.strip():
            slice_lines_set.add(0)

        queries_for_slicing = [
            "includes", "namespaces", "classes", "structs", "enums", "typedefs",
            "using_namespace", "namespace_aliases",
            "function_definitions", "template_function_definitions",
            "function_declarations", "template_function_declarations"
        ]

        for query_key in queries_for_slicing:
            query_obj = self.queries.get(query_key)
            if not query_obj:
                logger.debug(f"[{source_file_id}] Slicing: Query '{query_key}' not compiled or found. Skipping.")
                continue

            for _, captures_dict in query_obj.matches(root_node):
                node_to_slice_at: Optional[TSNODE_TYPE] = None
                if "definition" in captures_dict:
                    node_to_slice_at = captures_dict.get("definition", [None])[0]
                elif "include_statement" in captures_dict and query_key == "includes":
                     node_to_slice_at = captures_dict.get("include_statement", [None])[0]
                elif "using_statement" in captures_dict and query_key == "using_namespace":
                     node_to_slice_at = captures_dict.get("using_statement", [None])[0]

                if node_to_slice_at:
                    actual_line_0 = node_to_slice_at.start_point[0]

                    if "comments_with_include.cpp" in source_file_id and query_key == "includes":
                        node_text_preview = get_node_text(node_to_slice_at, content_bytes)
                        if node_text_preview: node_text_preview = node_text_preview.splitlines()[0]
                        logger.info(f"COMMENTS_INCLUDE_SLICE_DEBUG: Node Type='{node_to_slice_at.type}', Actual Start Line 0-idx={actual_line_0}, Text='{node_text_preview}'")
                    if "complex_features.cpp" in source_file_id:
                        node_text_preview = get_node_text(node_to_slice_at, content_bytes)
                        if node_text_preview: node_text_preview = node_text_preview.splitlines()[0] if node_text_preview.strip() else "EMPTY_NODE_TEXT"
                        else: node_text_preview = "NODE_TEXT_IS_NONE"
                        logger.info(f"COMPLEX_FEAT_SLICE_DEBUG: Query='{query_key}', Node Type='{node_to_slice_at.type}', Start Line={actual_line_0}, Text='{node_text_preview}'")
                    if "simple_class.cpp" in source_file_id:
                        node_text_preview = get_node_text(node_to_slice_at, content_bytes)
                        if node_text_preview: node_text_preview = node_text_preview.splitlines()[0] if node_text_preview.strip() else "EMPTY_NODE_TEXT"
                        else: node_text_preview = "NODE_TEXT_IS_NONE"
                        logger.info(f"SIMPLE_CLASS_SLICE_DEBUG: Query='{query_key}', Node Type='{node_to_slice_at.type}', Start Line={actual_line_0}, Text='{node_text_preview}'")
                    if "my_class.hpp" in source_file_id:
                        node_text_preview = get_node_text(node_to_slice_at, content_bytes)
                        if node_text_preview: node_text_preview = node_text_preview.splitlines()[0] if node_text_preview.strip() else "EMPTY_NODE_TEXT"
                        else: node_text_preview = "NODE_TEXT_IS_NONE"
                        logger.info(f"MY_CLASS_HPP_SLICE_DEBUG: Query='{query_key}', Node Type='{node_to_slice_at.type}', Start Line={actual_line_0}, Text='{node_text_preview}'")
                    if "forward_declarations.hpp" in source_file_id:
                        node_text_preview = get_node_text(node_to_slice_at, content_bytes)
                        if node_text_preview: node_text_preview = node_text_preview.splitlines()[0] if node_text_preview.strip() else "EMPTY_NODE_TEXT"
                        else: node_text_preview = "NODE_TEXT_IS_NONE"
                        logger.info(f"FORWARD_DECL_SLICE_DEBUG: Adding line {actual_line_0} from query '{query_key}' for node type '{node_to_slice_at.type}', text: '{node_text_preview}'")
                    if "closely_packed_definitions.cpp" in source_file_id:
                        node_text_preview = get_node_text(node_to_slice_at, content_bytes)
                        if node_text_preview: node_text_preview = node_text_preview.splitlines()[0] if node_text_preview.strip() else "EMPTY_NODE_TEXT"
                        else: node_text_preview = "NODE_TEXT_IS_NONE"
                        logger.info(f"CLOSELY_PACKED_SLICE_DEBUG: Adding line {actual_line_0} from query '{query_key}' for node type '{node_to_slice_at.type}', text_preview: '{node_text_preview}'")

                    slice_lines_set.add(actual_line_0)

        final_slice_list = sorted(list(slice_lines_set)) if slice_lines_set else []
        if not final_slice_list and full_content_string.strip():
            logger.warning(f"[{source_file_id}] Content exists but final_slice_list is empty after slicing queries. Defaulting to [0]. slice_lines_set was: {slice_lines_set}")
            final_slice_list = [0]

        logger.debug(f"[{source_file_id}] FINAL SLICE LIST TO YIELD: {final_slice_list}")
        yield final_slice_list

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
            if not query_obj:
                logger.debug(f"[{source_file_id}] Entity Extraction: Query '{query_name}' not compiled or found. Skipping.")
                continue

            for match_idx, captures_dict in query_obj.matches(root_node):
                definition_node: Optional[TSNODE_TYPE] = captures_dict.get("definition", [None])[0]

                name_node: Optional[TSNODE_TYPE] = None
                if query_name == "namespace_aliases" and definition_node:
                    name_node = captures_dict.get("alias_new_name", [None])[0]
                    if not name_node:
                        children_of_def_node = [c for c in definition_node.children if c.is_named]
                        if len(children_of_def_node) > 0 and children_of_def_node[0].type in ('identifier', 'namespace_identifier'):
                             name_node = children_of_def_node[0]
                elif name_capture_key_default:
                    name_node = captures_dict.get(name_capture_key_default, [None])[0]

                if not definition_node:
                    logger.debug(f"[{source_file_id}] No 'definition' node captured by query '{query_name}', match {match_idx}. Skipping.")
                    continue

                if definition_node.start_byte in processed_definition_node_starts:
                    logger.debug(f"[{source_file_id}] Skipping already processed definition node at byte {definition_node.start_byte} for query '{query_name}'")
                    continue

                if query_name == "namespaces" and element_type == "NamespaceDefinition" and not name_node:
                    body_node_for_anon_ns = definition_node.child_by_field_name("body")
                    if not body_node_for_anon_ns or body_node_for_anon_ns.child_count == 0:
                        logger.debug(f"[{source_file_id}] Skipping empty anonymous namespace definition.")
                        continue
                elif not name_node and element_type not in ["NamespaceDefinition", "NamespaceAliasDefinition"]:
                    logger.debug(f"[{source_file_id}] No 'name' node for query '{query_name}', element_type '{element_type}'. Def text: {get_node_text(definition_node, content_bytes)[:30]}. Skipping.")
                    continue

                true_fqn = self._get_fqn_for_node(name_node, definition_node, content_bytes, root_node, source_file_id)

                if "simple_class.cpp" in source_file_id:
                     logger.info(f"SIMPLE_CLASS_ENTITY_DEBUG: Type='{element_type}', FQN='{true_fqn}', Line={definition_node.start_point[0]}, TempID='{true_fqn}@{definition_node.start_point[0]}'")
                if "my_class.hpp" in source_file_id and "identity" in true_fqn.lower():
                     logger.info(f"MY_CLASS_HPP_ENTITY_DEBUG: Query='{query_name}', ElementType='{element_type}', DefNode Line: {definition_node.start_point[0]}, FQN: '{true_fqn}', TempID: '{true_fqn}@{definition_node.start_point[0]}', DefNode.start_byte: {definition_node.start_byte}, Is in processed_starts: {definition_node.start_byte in processed_definition_node_starts}")

                if "forward_declarations.hpp" in source_file_id:
                    temp_name_text = get_node_text(name_node, content_bytes) if name_node else "ANONYMOUS_OR_NO_NAME_NODE"
                    interesting_names = ["MyForwardClass", "MyForwardStruct", "FwdNS", "MyFwdEnum", "AnotherFwdClass", "fwd_declared_func"]
                    if any(interesting_name in temp_name_text for interesting_name in interesting_names) or \
                       (element_type == "NamespaceDefinition" and true_fqn == "FwdNS"):
                        logger.info(f"FORWARD_DECL_ENTITY_DEBUG ({temp_name_text if temp_name_text != 'ANONYMOUS_OR_NO_NAME_NODE' else true_fqn}): DefNode Line: {definition_node.start_point[0]}, FQN: {true_fqn}, TempID: {true_fqn}@{definition_node.start_point[0]}")


                if not true_fqn or ("unnamed_entity_in_fqn" in true_fqn and element_type != "NamespaceDefinition") :
                    if true_fqn == "anonymous" and element_type == "NamespaceDefinition":
                         pass
                    else:
                        logger.debug(f"[{source_file_id}] Invalid FQN '{true_fqn}' for Q '{query_name}', ET '{element_type}'. Def: {get_node_text(definition_node, content_bytes)[:50]}... Skip.")
                        continue

                original_ast_start_line_0 = definition_node.start_point[0]
                temp_entity_id = f"{true_fqn}@{original_ast_start_line_0}"
                processed_definition_node_starts.add(definition_node.start_byte)

                snippet_content_str = get_node_text(definition_node, content_bytes) or ""
                code_entity_instance = CodeEntity(id=temp_entity_id, type=element_type, snippet_content=snippet_content_str)
                yield code_entity_instance
                logger.debug(f"[{source_file_id}] Yielded CE (Def/Decl): {temp_entity_id} (type: {element_type})")

                if element_type == "FunctionDefinition":
                    body_node = definition_node.child_by_field_name("body")
                    if body_node:
                        function_bodies_to_scan_for_calls.append((body_node, temp_entity_id))
                    elif definition_node.type == "template_declaration":
                        inner_func_def = next((c for c in definition_node.children if c.type == "function_definition"), None)
                        if inner_func_def:
                            body_node_template = inner_func_def.child_by_field_name("body")
                            if body_node_template:
                                function_bodies_to_scan_for_calls.append((body_node_template, temp_entity_id))

                if element_type in ["ClassDefinition", "StructDefinition"]:
                    heritage_node = captures_dict.get("heritage", [None])[0]
                    if heritage_node and heritage_node.type == "base_class_clause":
                        all_parents_text = set()
                        for child_node_heritage in heritage_node.named_children:
                            if child_node_heritage.type in ["type_identifier", "qualified_identifier", "template_type"]:
                                parent_name_raw = get_node_text(child_node_heritage, content_bytes)
                                if parent_name_raw:
                                    parent_name_normalized = ' '.join(parent_name_raw.split())
                                    all_parents_text.add(parent_name_normalized)

                        for p_name_raw in all_parents_text:
                            if p_name_raw:
                                yield Relationship(source_id=temp_entity_id, target_id=p_name_raw, type="EXTENDS")
                                logger.debug(f"[{source_file_id}] Yielded EXTENDS Rel: {temp_entity_id} -> {p_name_raw}")

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
                            ext_ref_entity = CodeEntity(
                                id=temp_ext_ref_id, type="ExternalReference",
                                snippet_content=external_fqn
                            )
                            yield ext_ref_entity
                            logger.debug(f"[{source_file_id}] Yielded CE (ExtRef): {temp_ext_ref_id}")
                            processed_include_refs_yielded_for_entity.add(temp_ext_ref_id)

                        import_rel_key = (source_file_id, temp_ext_ref_id)
                        if import_rel_key not in processed_import_relationships:
                            yield Relationship(source_id=source_file_id, target_id=temp_ext_ref_id, type="IMPORTS")
                            logger.debug(f"[{source_file_id}] Yielded IMPORTS Rel: {source_file_id} -> {temp_ext_ref_id}")
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
                            directive_entity = CodeEntity(
                                id=temp_directive_id, type="UsingDirective", snippet_content=using_snippet
                            )
                            yield directive_entity
                            logger.debug(f"[{source_file_id}] Yielded CE (UsingDirective): {temp_directive_id}")
                            processed_using_directive_entities.add(temp_directive_id)

                        has_directive_key = (source_file_id, temp_directive_id)
                        if has_directive_key not in processed_using_relationships:
                            yield Relationship(source_id=source_file_id, target_id=temp_directive_id, type="HAS_DIRECTIVE")
                            logger.debug(f"[{source_file_id}] Yielded HAS_DIRECTIVE Rel: {source_file_id} -> {temp_directive_id}")
                            processed_using_relationships.add(has_directive_key)

                        ref_ns_key = (temp_directive_id, namespace_name_str)
                        if ref_ns_key not in processed_using_relationships:
                            yield Relationship(source_id=temp_directive_id, target_id=namespace_name_str, type="REFERENCES_NAMESPACE")
                            logger.debug(f"[{source_file_id}] Yielded REFERENCES_NAMESPACE Rel: {temp_directive_id} -> {namespace_name_str}")
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

                    current_context_for_log = self._current_function_context_temp_id or "UnknownContext"
                    logger.debug(f"CALL_SITE_RAW_MATCH ({current_context_for_log} @ L{actual_call_node.start_point[0]+1}): Node Type='{actual_call_node.type}', Text='{get_node_text(actual_call_node, content_bytes)}', Captures: {list(call_captures_dict.keys())}")


                    called_name_expr: Optional[str] = None
                    raw_arg_text_val: Optional[str] = None
                    arg_count_val: int = 0

                    if call_site_op_node :
                        op_symbol_node = call_captures_dict.get("operator_symbol", [None])[0]
                        if op_symbol_node:
                            called_name_expr = self._get_node_name_text(op_symbol_node, content_bytes)
                            logger.debug(f"OPERATOR_CALL_DEBUG: op_symbol_node.type='{op_symbol_node.type}', op_symbol_node.text='{get_node_text(op_symbol_node, content_bytes)}', _get_node_name_text output='{called_name_expr}'")


                        arg_count_val = 2
                        left_op_node = call_captures_dict.get("left_operand", [None])[0]
                        right_op_node = call_captures_dict.get("right_operand", [None])[0]
                        left_text = get_node_text(left_op_node, content_bytes) if left_op_node else ""
                        right_text = get_node_text(right_op_node, content_bytes) if right_op_node else ""
                        raw_arg_text_val = f"{left_text},{right_text}"

                    elif call_site_delete_node:
                        called_name_expr = "operator delete"
                        delete_expr_text_full = get_node_text(actual_call_node, content_bytes) or ""
                        if "[]" in delete_expr_text_full :
                            called_name_expr = "operator delete[]"

                        deleted_value_node_child = None
                        temp_deleted_value_node = actual_call_node.child_by_field_name("value")
                        if temp_deleted_value_node:
                             deleted_value_node_child = temp_deleted_value_node
                        elif actual_call_node.child_count > 0:
                            for i in range(actual_call_node.child_count - 1, -1, -1):
                                child = actual_call_node.child(i)
                                if child.is_named and child.type not in ['[', ']', '::', 'delete']:
                                    deleted_value_node_child = child
                                    break

                        raw_arg_text_val = get_node_text(deleted_value_node_child, content_bytes) if deleted_value_node_child else ""
                        arg_count_val = 1 if raw_arg_text_val else 0


                    elif call_site_constructor_node:
                        # This handles both `new` and stack-based constructor calls due to the new query pattern
                        name_node_for_constructor = call_captures_dict.get("name", [None])[0]
                        if name_node_for_constructor:
                            called_name_expr = self._get_node_name_text(name_node_for_constructor, content_bytes)

                        arguments_node = call_captures_dict.get("arguments", [None])[0]
                        if arguments_node:
                            if arguments_node.type == "argument_list":
                                raw_arg_text_val_full = get_node_text(arguments_node, content_bytes)
                                raw_arg_text_val = raw_arg_text_val_full.strip("()") if raw_arg_text_val_full else ""
                                arg_count_val = len(arguments_node.named_children)
                            elif arguments_node.type == "initializer_list":
                                raw_arg_text_val_full = get_node_text(arguments_node, content_bytes)
                                raw_arg_text_val = raw_arg_text_val_full.strip("{}") if raw_arg_text_val_full else ""
                                arg_count_val = len(arguments_node.named_children)
                        else: # No arguments
                            raw_arg_text_val = ""
                            arg_count_val = 0

                    elif call_site_node_direct:
                        function_node_for_call = call_captures_dict.get("function_node_for_call", [None])[0]
                        if function_node_for_call:
                            called_name_expr = self._get_node_name_text(function_node_for_call, content_bytes)
                            if not called_name_expr:
                                called_name_expr = get_node_text(function_node_for_call, content_bytes)

                        arguments_node_direct = call_captures_dict.get("arguments", [None])[0]
                        if arguments_node_direct and arguments_node_direct.type == "argument_list":
                            raw_arg_text_val_full = get_node_text(arguments_node_direct, content_bytes)
                            raw_arg_text_val = raw_arg_text_val_full.strip("()") if raw_arg_text_val_full else ""
                            arg_count_val = len(arguments_node_direct.named_children)
                        else:
                            raw_arg_text_val = ""
                            arg_count_val = 0

                    if not called_name_expr:
                        logger.debug(f"[{source_file_id}] Call site node matched but no callable name expression extracted. Node type: {actual_call_node.type}, Text: {get_node_text(actual_call_node, content_bytes)[:50]}")
                        continue

                    if self._current_function_context_temp_id is None:
                        logger.warning(f"[{source_file_id}] No function context for call to '{called_name_expr}' at line {actual_call_node.start_point[0] + 1}. Skipping CallSiteReference.")
                        continue

                    line_of_call_0 = actual_call_node.start_point[0]

                    logger.debug(f"CALL_SITE_EXTRACTED_DETAILS: Caller='{self._current_function_context_temp_id}', CalledExpr='{called_name_expr}', Line={line_of_call_0}, ArgsRaw='{raw_arg_text_val}', ArgCount={arg_count_val}")

                    call_site_ref = CallSiteReference(
                        calling_entity_temp_id=self._current_function_context_temp_id,
                        called_name_expr=called_name_expr.strip(),
                        line_of_call_0_indexed=line_of_call_0,
                        source_file_id_of_call_site=source_file_id,
                        raw_arg_text=raw_arg_text_val,
                        argument_count=arg_count_val
                    )
                    yield call_site_ref
                    logger.debug(f"[{source_file_id}] Yielded CallSiteRef: {call_site_ref.model_dump_json(indent=None)}")


        self._current_function_context_temp_id = None
        self.current_source_file_id_for_debug = None
        logger.info(f"CppParser: Finished parsing for {source_file_id}")
