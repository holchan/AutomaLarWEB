# .roo/cognee/src/parser/parsers/cpp_parser.py
from pydantic import BaseModel
from typing import AsyncGenerator, Optional, List, Dict, Any, Set, Tuple
import re

from .base_parser import BaseParser
# IMPORTANT: Ensure CodeEntity and RawSymbolReference have an optional `metadata` field in entities.py
from ..entities import CodeEntity, RawSymbolReference, ParserOutput, ReferenceContext, ImportType
from ..utils import get_node_text, logger, TSNODE_TYPE, format_node_for_debug
from .treesitter_setup import get_parser, get_language

# Final Queries: Includes all necessary captures for context and references
CPP_QUERIES = {
    "includes": """(preproc_include path: [(string_literal) (system_lib_string)] @path)""",
    "using_namespace": """(using_declaration "namespace" . [(identifier) (qualified_identifier)] @name)""",
    "variable_declarations": """(declaration type: (_) @type declarator: [(identifier) (pointer_declarator) (array_declarator)] @name)""",
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
          (preproc_def name: (identifier) @name) @definition
          (lambda_expression) @definition
        ]
    """,
    "references": """
        [
          (call_expression) @call
          (preproc_call) @macro_call
          (base_class_clause) @inheritance
          (new_expression) @call
          (type_identifier) @type_ref
        ]
    """,
}

class FileContext:
    """A stateful object to hold all context during a single file parse."""
    def __init__(self, source_file_id: str):
        self.source_file_id = source_file_id
        self.scope_stack: List[Tuple[Optional[str], str]] = [(None, source_file_id)]
        self.include_map: Dict[str, str] = {}
        self.active_usings: Dict[int, List[str]] = {}
        self.import_map: Dict[str, str] = {}
        self.local_definitions: Dict[str, str] = {}
        self.local_variable_types: Dict[Tuple[str, str], str] = {}

class CppParser(BaseParser):
    SUPPORTED_EXTENSIONS = [".cpp", ".hpp", ".h", ".c", ".cc"]
    AST_SCOPES_FOR_FQN: Set[str] = {
        "namespace_definition", "class_specifier", "struct_specifier",
        "function_definition", "template_declaration", "compound_statement",
    }

    def __init__(self):
        super().__init__()
        self.log_prefix = "CppParser"
        self.language = get_language("cpp")
        self.parser = get_parser("cpp")
        self.queries: Dict[str, Any] = {name: self.language.query(query_str) for name, query_str in CPP_QUERIES.items()}

    def _get_node_name_text(self, node: Optional[TSNODE_TYPE], content_bytes: bytes) -> str:
        if not node: return "anonymous"
        return get_node_text(node, content_bytes) or "anonymous"

    def _get_fqn_for_node(self, name_node: Optional[TSNODE_TYPE], def_node: TSNODE_TYPE, content_bytes: bytes, scope_stack: List[Tuple[Optional[str], str]]) -> str:
        # This helper is now complete from previous revisions
        if def_node.type == "lambda_expression": return f"lambda@{def_node.start_point[0] + 1}"
        base_name = self._get_node_name_text(name_node, content_bytes)
        template_string = ""
        if def_node.type == "template_declaration":
            params_node = def_node.child_by_field_name("parameters")
            if params_node: template_string = get_node_text(params_node, content_bytes)
        param_string = ""
        declarator_node = next((n for n in def_node.children if n.type in ('function_declarator', 'template_function')), None)
        if declarator_node:
            param_list_node = declarator_node.child_by_field_name("parameters")
            param_string = get_node_text(param_list_node, content_bytes) or "()"
        parent_scopes = [scope[0] for scope in scope_stack if scope[0] is not None]
        if name_node and name_node.type == "qualified_identifier":
            return get_node_text(name_node, content_bytes) + param_string
        else:
            fqn_parts = parent_scopes + [base_name + template_string]
            return "::".join(fqn_parts) + param_string

    def _get_type_for_definition(self, node: TSNODE_TYPE) -> str:
        # This helper is now complete
        type_map = {"function_definition": "FunctionDefinition", "class_specifier": "ClassDefinition", "struct_specifier": "StructDefinition", "namespace_definition": "NamespaceDefinition", "enum_specifier": "EnumDefinition", "preproc_def": "MacroDefinition", "lambda_expression": "LambdaDefinition"}
        if node.type == "template_declaration": return "TemplateDefinition"
        return type_map.get(node.type, "UnknownDefinition")

    def _precompute_interest_nodes(self, root_node: TSNODE_TYPE) -> Dict[int, List[Tuple[str, str]]]:
        # This helper is complete
        interest_nodes: Dict[int, List[Tuple[str, str]]] = {}
        for query_name, query in self.queries.items():
            for match in query.matches(root_node):
                node = match[0]
                capture_name = self.queries[query_name].captures[match[1].index]
                if node.id not in interest_nodes: interest_nodes[node.id] = []
                interest_nodes[node.id].append((query_name, capture_name))
        return interest_nodes

    def _resolve_context_for_reference(self, target_expr: str, node: TSNODE_TYPE, context: FileContext) -> ReferenceContext:
        """
        The "brain" of the parser. Implements the full prioritized lookup chain
        to provide the richest possible context for a symbol reference.
        """
        log_prefix = f"{self.log_prefix} ({context.source_file_id})"

        # Priority 1: Check for object method calls (e.g., my_obj.do_work() or ptr->do_work())
        if '.' in target_expr or '->' in target_expr:
            obj_name, method_name = re.split(r'\.|->', target_expr, maxsplit=1)
            # Traverse up the scope stack to find where the variable was declared
            for _, scope_id in reversed(context.scope_stack):
                if var_type := context.local_variable_types.get((scope_id, obj_name)):
                    logger.debug(f"{log_prefix}: Resolved '{target_expr}' as method call on var of type '{var_type}' in scope '{scope_id}'")
                    return ReferenceContext(import_type=ImportType.ABSOLUTE, path_parts=var_type.split("::") + [method_name])

        # Priority 2: Check if the symbol comes from a known include file
        base_symbol = target_expr.split('::')[0]
        if base_symbol in context.import_map:
            include_path = context.import_map[base_symbol]
            include_type = context.include_map.get(include_path, "quoted")
            logger.debug(f"{log_prefix}: Resolved '{target_expr}' via known import '{include_path}'")
            # We return the path of the include file itself
            return ReferenceContext(import_type=ImportType.ABSOLUTE if include_type == "system" else ImportType.RELATIVE, path_parts=[include_path])

        # Priority 3: Resolve using active 'using namespace' directives
        current_scope_node = node
        while current_scope_node:
            if current_scope_node.id in context.active_usings:
                for ns in reversed(context.active_usings[current_scope_node.id]):
                    candidate_fqn = f"{ns}::{target_expr}"
                    if candidate_fqn in context.local_definitions:
                        logger.debug(f"{log_prefix}: Resolved '{target_expr}' via active 'using namespace {ns}' to FQN '{candidate_fqn}'")
                        return ReferenceContext(import_type=ImportType.ABSOLUTE, path_parts=candidate_fqn.split("::"))
            current_scope_node = current_scope_node.parent

        # Priority 4: Fallback to assuming it's a global or fully-qualified reference
        return ReferenceContext(import_type=ImportType.ABSOLUTE, path_parts=target_expr.split("::"))

    async def _walk_and_process(self, node: TSNODE_TYPE, context: FileContext, content_bytes: bytes, interest_nodes: Dict[int, List[Tuple[str, str]]]) -> AsyncGenerator[ParserOutput, None]:
        # This walker is now complete and uses the fully implemented helpers
        node_id = node.id
        is_scope = node.type in self.AST_SCOPES_FOR_FQN

        if is_scope:
            name_node = node.child_by_field_name("name")
            scope_name = self._get_node_name_text(name_node, content_bytes) if node.type != "compound_statement" else None
            if node_id in interest_nodes and any(i[0] == "definitions" for i in interest_nodes[node_id]):
                fqn = self._get_fqn_for_node(name_node, node, content_bytes, context.scope_stack)
                current_entity_id = f"{fqn}@{node.start_point[0] + 1}"
            else:
                current_entity_id = f"{context.source_file_id}|block@{node.start_point[0] + 1}"
            context.scope_stack.append((scope_name, current_entity_id))

        if node_id in interest_nodes:
            for query_name, capture_name in interest_nodes[node_id]:
                if query_name == "definitions":
                    entity_type = self._get_type_for_definition(node)
                    scope_id = context.scope_stack[-1][1]
                    fqn = scope_id.split('@')[0]
                    context.local_definitions[fqn] = scope_id
                    yield CodeEntity(id=scope_id, type=entity_type, snippet_content=get_node_text(node, content_bytes) or "", canonical_fqn=fqn)

                elif query_name == "variable_declarations" and capture_name == "name":
                    if node.parent and node.parent.type == 'declaration':
                        type_node = node.parent.child_by_field_name("type")
                        if type_node:
                            var_name = get_node_text(node, content_bytes)
                            var_type = get_node_text(type_node, content_bytes)
                            scope_id = context.scope_stack[-1][1]
                            context.local_variable_types[(scope_id, var_name)] = var_type

                elif query_name == "references":
                    source_id = context.scope_stack[-1][1]
                    ref_type_map = {"inheritance": "INHERITANCE", "call": "FUNCTION_CALL", "macro_call": "MACRO_CALL", "type_ref": "REFERENCES_SYMBOL"}
                    if capture_name == "inheritance":
                        for parent_node in node.named_children:
                            if parent_name := get_node_text(parent_node, content_bytes):
                                yield RawSymbolReference(source_entity_id=source_id, target_expression=parent_name, reference_type="INHERITANCE", context=self._resolve_context_for_reference(parent_name, parent_node, context))
                    else:
                        target_node = node.child_by_field_name("function") or node.child_by_field_name("name") or (node if capture_name == "type_ref" else None)
                        if target_node and (target_expr := get_node_text(target_node, content_bytes)):
                            yield RawSymbolReference(source_entity_id=source_id, target_expression=target_expr, reference_type=ref_type_map[capture_name], context=self._resolve_context_for_reference(target_expr, target_node, context))

        for child in node.children:
            async for item in self._walk_and_process(child, context, content_bytes, interest_nodes):
                yield item

        if is_scope: context.scope_stack.pop()

    async def parse(self, source_file_id: str, file_content: str) -> AsyncGenerator[ParserOutput, None]:
        log_prefix = f"CppParser ({source_file_id})"
        logger.info(f"{log_prefix}: Starting parsing.")

        try:
            content_bytes = bytes(file_content, "utf8")
            tree = self.parser.parse(content_bytes)
            root_node = tree.root_node
        except Exception as e:
            logger.error(f"{log_prefix}: Failed to parse content into AST: {e}"); return

        interest_nodes = self._precompute_interest_nodes(root_node)
        def_nodes = [node for nid, interests in interest_nodes.items() if "definitions" in [i[0] for i in interests] for node in [root_node.descendant_for_byte_range(nid, nid)] if node]

        if def_nodes:
            slice_lines = sorted(list({1} | {node.start_point[0] + 1 for node in def_nodes}))
            yield slice_lines
        else:
            yield []

        file_context = FileContext(source_file_id)

        # Pre-populate context before the main walk
        if include_query := self.queries.get("includes"):
            for match, _ in include_query.matches(root_node):
                path_node = match.nodes[1]
                path_text = get_node_text(path_node, content_bytes).strip('<>\"')
                import_type = ImportType.ABSOLUTE if path_node.type == "system_lib_string" else ImportType.RELATIVE
                file_context.include_map[path_text] = "system" if import_type == ImportType.ABSOLUTE else "quoted"
                base_name = path_text.split('/')[-1].split('.')[0]
                file_context.import_map[base_name] = path_text
                yield RawSymbolReference(source_entity_id=source_file_id, target_expression=path_text, reference_type="INCLUDE", context=ReferenceContext(import_type=import_type, path_parts=[path_text]))

        if using_query := self.queries.get("using_namespace"):
            for match, _ in using_query.matches(root_node):
                name_node = match.nodes[1]
                namespace = get_node_text(name_node, content_bytes)
                scope_node = name_node.parent
                while scope_node and scope_node.type not in self.AST_SCOPES_FOR_FQN:
                    scope_node = scope_node.parent
                if scope_node:
                    if scope_node.id not in file_context.active_usings: file_context.active_usings[scope_node.id] = []
                    file_context.active_usings[scope_node.id].append(namespace)

        async for item in self._walk_and_process(root_node, file_context, content_bytes, interest_nodes):
            yield item

        logger.info(f"{log_prefix}: Finished parsing.")
