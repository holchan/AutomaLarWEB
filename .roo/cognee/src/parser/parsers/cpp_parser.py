# .roo/cognee/src/parser/parsers/cpp_parser.py
from pydantic import BaseModel
from typing import AsyncGenerator, Optional, List, Dict, Any, Set, Union, Tuple
import re

from .base_parser import BaseParser
# --- IMPORTANT: Importing our final, standardized data contracts ---
from ..entities import CodeEntity, RawSymbolReference, ParserOutput, ReferenceContext, ImportType
from ..utils import get_node_text, logger, TSNODE_TYPE
from .treesitter_setup import get_parser, get_language

# --- The full, declarative queries that drive the parser ---
CPP_QUERIES = {
    "includes": """(preproc_include path: [(string_literal) (system_lib_string)] @path) @include""",
    "using_namespace": """(using_declaration "namespace" [ (identifier) @name (nested_namespace_specifier) @name (qualified_identifier) @name ])""",
    "macro_definitions": """(preproc_def name: (identifier) @name value: (_) @body) @definition""",
    "definitions": """
        [
          (function_definition) @definition
          (function_declaration) @definition
          (template_declaration) @definition
          (class_specifier) @definition
          (struct_specifier) @definition
          (namespace_definition) @definition
          (enum_specifier) @definition
          (type_definition) @definition
          (alias_declaration) @definition
        ]
    """,
    "references": """
        [
          (call_expression) @call
          (preproc_call) @macro_call
          (base_class_clause) @inheritance
          (new_expression) @call
        ]
    """,
}

# --- A helper class to manage the state of a single file's parse ---
class FileContext:
    """A stateful object to hold all context during a single file parse."""
    def __init__(self, source_file_id: str):
        self.source_file_id = source_file_id
        self.scope_stack: List[str] = []
        # Maps an include path to its type ('system' or 'quoted')
        self.include_map: Dict[str, str] = {}
        # Maps a scope's unique ID to a list of active `using` namespaces
        self.active_usings: Dict[int, List[str]] = {}
        # Maps a raw FQN to its full CodeEntity temp_id
        self.local_definitions: Dict[str, str] = {}

class CppParser(BaseParser):
    SUPPORTED_EXTENSIONS = [".cpp", ".hpp", ".h", ".c", ".cc"]
    AST_SCOPES_FOR_FQN: Set[str] = {
        "namespace_definition", "class_specifier", "struct_specifier",
        "function_definition", "template_declaration",
    }

    def __init__(self):
        super().__init__()
        self.log_prefix = "CppParser"
        self.language = get_language("cpp")
        self.parser = get_parser("cpp")
        self.queries: Dict[str, Any] = {}
        if self.language:
            for name, query_str in CPP_QUERIES.items():
                try:
                    self.queries[name] = self.language.query(query_str)
                except Exception as e:
                    logger.error(f"{self.log_prefix}: FAILED to compile query '{name}'. Error: {e}")
        else:
            logger.error(f"{self.log_prefix}: C++ tree-sitter language not loaded.")

    def _get_node_name_text(self, node: Optional[TSNODE_TYPE], content_bytes: bytes) -> Optional[str]:
        # This is your existing, sophisticated name extraction logic, fully integrated.
        if not node: return None
        name_str = get_node_text(node, content_bytes)
        if not name_str: return None

        if node.type == "template_function":
            name_child_node = node.child_by_field_name("name")
            if not name_child_node:
                 potential_name_children = [c for c in node.children if c.type in ("identifier", "qualified_identifier", "field_identifier", "operator_name", "template_function")]
                 best_name_node = None
                 for p_type in ("identifier", "field_identifier", "operator_name"):
                     found = [c for c in potential_name_children if c.type == p_type]
                     if found: best_name_node = found[0]; break
                 if not best_name_node and potential_name_children: best_name_node = potential_name_children[0]
                 if best_name_node: name_child_node = best_name_node
            if name_child_node:
                name_str = get_node_text(name_child_node, content_bytes) or name_str
            else:
                name_match = re.match(r"([^<]+)(?:<.*>)?", name_str)
                if name_match: name_str = name_match.group(1).strip()

        stripped_name_val = name_str.strip()
        if not stripped_name_val.lower().startswith("operator") and not stripped_name_val.isalnum() and stripped_name_val:
            if stripped_name_val == "()": name_str = "operator()"
            elif stripped_name_val == "[]": name_str = "operator[]"
            elif len(stripped_name_val) <= 2 and stripped_name_val and not stripped_name_val[0].isalnum():
                name_str = f"operator{stripped_name_val}"

        if "operator" in name_str:
            match = re.search(r"((?:[\w:]*::\s*)?operator)\s*(\b(?:new|delete)(?:\[\])?\b|\"\"|\S{1,3}(?:\[\])?|\b\w+\b)", name_str)
            if match:
                op_keyword_part, op_symbol_part = match.group(1).strip(), match.group(2).strip()
                if op_symbol_part.startswith("new") or op_symbol_part.startswith("delete"):
                    name_str = f"{op_keyword_part} {op_symbol_part}"
                else: name_str = f"{op_keyword_part}{op_symbol_part}"
        return name_str

    def _get_fqn_for_node(self, name_node: Optional[TSNODE_TYPE], def_node: TSNODE_TYPE, content_bytes: bytes, scope_stack: List[str]) -> str:
        base_name_text = self._get_node_name_text(name_node, content_bytes) or "anonymous"

        param_string = ""
        is_function_like = def_node.type in ["function_definition", "function_declaration", "field_declaration", "type_definition"] or \
                           (def_node.type == "template_declaration" and any(c.type in ["function_definition", "function_declaration"] for c in def_node.children))

        if is_function_like:
            function_declarator_node = next((n for n in def_node.children if n.type == 'function_declarator'), None)
            if not function_declarator_node and def_node.type == "template_declaration":
                inner_def = next((n for n in def_node.children if n.type in ["function_definition", "function_declaration"]), None)
                if inner_def:
                    function_declarator_node = next((n for n in inner_def.children if n.type == 'function_declarator'), None)

            if function_declarator_node:
                param_list_node = function_declarator_node.child_by_field_name("parameters")
                if param_list_node:
                    param_type_texts = []
                    for param_decl in param_list_node.named_children:
                        type_node = param_decl.child_by_field_name("type")
                        param_type_texts.append(get_node_text(type_node, content_bytes) or "void")
                    param_string = f"({','.join(param_type_texts)})"
                else: param_string = "()"

        fqn_parts = scope_stack[:]
        if name_node and name_node.type == "qualified_identifier":
            qualified_parts = base_name_text.split("::")
            if fqn_parts and fqn_parts[-1] == qualified_parts[0]: fqn_parts.extend(qualified_parts[1:])
            else: fqn_parts.extend(qualified_parts)
        else:
            fqn_parts.append(base_name_text)

        return "::".join(fqn_parts) + param_string

    def _resolve_context_for_reference(self, target_expr: str, node: TSNODE_TYPE, context: FileContext) -> ReferenceContext:
        """The V2 resolver. Uses the file-local context to determine the best possible context for a given reference."""
        path_parts = target_expr.split("::")
        base_symbol = path_parts[0]

        if base_symbol in context.include_map:
            include_type = context.include_map[base_symbol]
            return ReferenceContext(
                import_type=ImportType.ABSOLUTE if include_type == 'system' else ImportType.RELATIVE,
                path_parts=path_parts
            )

        if target_expr in context.local_definitions:
            return ReferenceContext(import_type=ImportType.RELATIVE, path_parts=path_parts)

        return ReferenceContext(import_type=ImportType.ABSOLUTE, path_parts=path_parts)

    def _get_type_for_definition(self, node: TSNODE_TYPE) -> str:
        type_map = {
            "function_definition": "FunctionDefinition", "function_declaration": "FunctionDeclaration",
            "class_specifier": "ClassDefinition", "struct_specifier": "StructDefinition",
            "namespace_definition": "NamespaceDefinition", "enum_specifier": "EnumDefinition",
            "type_definition": "TypeAlias", "alias_declaration": "TypeAlias", "preproc_def": "MacroDefinition",
        }
        if node.type == "template_declaration":
            def_child = next((c for c in node.children if c.type in type_map), None)
            if def_child: return type_map.get(def_child.type, "UnknownDefinition")
        return type_map.get(node.type, "UnknownDefinition")

    async def _walk_and_process(self, node: TSNODE_TYPE, context: FileContext, content_bytes: bytes, interest_nodes: Dict[int, List[Tuple[str, str]]]) -> AsyncGenerator[ParserOutput, None]:
        """The single-pass recursive walk. It's now an async generator."""
        is_scope = node.type in self.AST_SCOPES_FOR_FQN

        if is_scope:
            name_node = node.child_by_field_name("name")
            scope_name = self._get_node_name_text(name_node, content_bytes) if name_node else "anonymous"
            context.scope_stack.append(scope_name)

        if node.id in interest_nodes:
            for interest_type, capture_name in interest_nodes[node.id]:
                if interest_type == "definition":
                    entity_type = self._get_type_for_definition(node)
                    name_node = node.child_by_field_name("name") or node.child_by_field_name("declarator")
                    fqn = self._get_fqn_for_node(name_node, node, content_bytes, context.scope_stack)
                    temp_id = f"{fqn}@{node.start_point[0]}"
                    yield CodeEntity(id=temp_id, type=entity_type, snippet_content=get_node_text(node, content_bytes) or "")
                    context.local_definitions[fqn] = temp_id

                elif interest_type == "reference":
                    calling_entity_id = "::".join(context.scope_stack) + f"@{node.start_point[0]}"
                    if capture_name == "inheritance":
                        for parent_node in node.named_children:
                            if parent_name := get_node_text(parent_node, content_bytes):
                                yield RawSymbolReference(source_entity_id=calling_entity_id, target_expression=parent_name, reference_type="INHERITANCE", context=self._resolve_context_for_reference(parent_name, parent_node, context))
                    elif capture_name == "call":
                        func_node = node.child_by_field_name("function")
                        if func_node and (called_expr := get_node_text(func_node, content_bytes)):
                             yield RawSymbolReference(source_entity_id=calling_entity_id, target_expression=called_expr, reference_type="FUNCTION_CALL", context=self._resolve_context_for_reference(called_expr, node, context))
                    elif capture_name == "macro_call":
                        name_node = node.child_by_field_name("name")
                        if name_node and (macro_name := get_node_text(name_node, content_bytes)):
                             yield RawSymbolReference(source_entity_id=calling_entity_id, target_expression=macro_name, reference_type="MACRO_CALL", context=self._resolve_context_for_reference(macro_name, node, context))

        for child in node.children:
            async for item in self._walk_and_process(child, context, content_bytes, interest_nodes):
                yield item

        if is_scope:
            context.scope_stack.pop()

    async def parse(self, source_file_id: str, file_content: str) -> AsyncGenerator[ParserOutput, None]:
        log_prefix = f"CppParser ({source_file_id})"
        logger.debug(f"{log_prefix}: Starting V2 full implementation parsing.")

        try:
            content_bytes = bytes(file_content, "utf8")
            tree = self.parser.parse(content_bytes)
            root_node = tree.root_node
        except Exception as e:
            logger.error(f"{log_prefix}: Failed to parse content: {e}", exc_info=True)
            yield []
            return

        # STEP 1: Pre-computation - Run all queries once to find nodes of interest
        points_of_interest: Dict[int, List[Tuple[str, str]]] = {}
        for query_name, query in self.queries.items():
            interest_type = "definition" if "def" in query_name else "reference"
            for match, capture_name in query.captures:
                points_of_interest.setdefault(match.id, []).append((interest_type, capture_name))

        # STEP 2: Yield Slice Lines
        def_nodes = [node for node_id, interests in points_of_interest.items() if interests[0][0] == 'definition' and (node := root_node.descendant_for_byte_range(node_id, node_id))]
        slice_lines = sorted(list({0} | {node.start_point[0] for node in def_nodes}))
        yield slice_lines

        # STEP 3: The Single, Context-Building Walk and Yield
        file_context = FileContext(source_file_id)

        include_query = self.queries.get("includes")
        if include_query:
            for match, _ in include_query.matches(root_node):
                path_node = match.nodes[0]
                path_text = get_node_text(path_node, content_bytes).strip('<>\"')
                import_type_str = "system" if path_node.type == "system_lib_string" else "quoted"
                file_context.include_map[path_text] = import_type_str

        async for item in self._walk_and_process(root_node, file_context, content_bytes, points_of_interest):
            yield item

        logger.info(f"{log_prefix}: Finished parsing.")
