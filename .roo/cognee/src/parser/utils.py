import asyncio
import aiofiles
from typing import Optional, Any, List, Dict, Tuple

from cognee.shared.logging_utils import get_logger
logger = get_logger(__name__)

from tree_sitter import Node as TSNODE_TYPE

async def read_file_content(file_path: str) -> Optional[str]:
    """
    Asynchronously reads the content of a file.
    """
    try:
        async with aiofiles.open(file_path, mode="r", encoding="utf-8", errors="ignore") as f:
            content = await f.read()
        return content
    except FileNotFoundError:
        logger.error(f"UTILS: File not found: {file_path}")
        return None
    except IOError as e:
        logger.error(f"UTILS: IOError reading file {file_path}", exc_info=e)
        return None
    except Exception as e:
        logger.error(f"UTILS: Unexpected error reading file {file_path}", exc_info=e)
        return None

def get_node_text(node: Optional[TSNODE_TYPE], content_bytes: bytes) -> Optional[str]:
    """
    Extracts the text represented by a tree-sitter node from the source content bytes.
    """
    if node is None:
        return None
    try:
        start = node.start_byte
        end = node.end_byte

        if start < 0 or end > len(content_bytes) or start > end:
             logger.warning(
                f"UTILS: Node byte range [{start}-{end}] invalid/out of bounds "
                f"for content length {len(content_bytes)}. Node type: {node.type}. "
                f"Attempting to clamp."
            )
             start = max(0, start)
             end = min(len(content_bytes), end)
             if start >= end:
                 logger.warning(f"UTILS: Clamped node byte range [{start}-{end}] is still invalid. Returning empty string.")
                 return ""

        return content_bytes[start:end].decode("utf-8", "ignore")
    except Exception as e:
        node_type_str = node.type if node else "None"
        node_range_str = f"[{node.start_byte}-{node.end_byte}]" if node else "[N/A-N/A]"
        logger.error(
            f"UTILS: Error extracting text from tree-sitter node "
            f"(Type: {node_type_str}, Range: {node_range_str}).",
            exc_info=True
        )
        return None

def format_node_for_debug(
    node: Optional[TSNODE_TYPE],
    content_bytes: Optional[bytes] = None,
    max_text_preview: int = 50
) -> str:
    """
    Creates a concise, readable string representation of a tree-sitter node for logging.
    """
    if not node:
        return "Node:None"

    text_preview_str = ""
    if content_bytes:
        raw_text = get_node_text(node, content_bytes)
        if raw_text is not None:
            stripped_raw_text = raw_text.strip()
            first_line = stripped_raw_text.splitlines()[0] if stripped_raw_text else ""

            if len(first_line) > max_text_preview:
                text_preview_str = "'" + first_line[:max_text_preview] + "...'"
            else:
                text_preview_str = "'" + first_line + "'"
        else:
            text_preview_str = "[Error getting text]"

    return f"Node(Type='{node.type}', Line={node.start_point[0]}-{node.end_point[0]}, Text={text_preview_str})"

def log_ast_node_structure(
    origin_message: str,
    node: Optional[TSNODE_TYPE],
    content_bytes: bytes,
    max_depth: int = 2,
    current_depth: int = 0,
    prefix: str = ""
):
    """
    Logs the structure of an AST node and its children up to a max_depth.
    """
    if not node or current_depth > max_depth:
        if not node and current_depth == 0:
            logger.debug(f"UTILS_AST_DUMP for '{origin_message}': Provided node is None.")
        return

    if current_depth == 0:
        logger.debug(f"UTILS_AST_DUMP for '{origin_message}' (Max Depth: {max_depth}):")

    field_name_str = ""
    if node.parent:
        try:
            for i in range(node.parent.child_count):
                if node.parent.child(i).id == node.id:
                    field_name = node.parent.field_name_for_child(i)
                    field_name_str = f"(FieldInParent: {field_name or 'UnnamedChild'})"
                    break
        except AttributeError:
            field_name_str = "(FieldInParent: ErrorGettingName)"
        except Exception:
            field_name_str = "(FieldInParent: N/A)"

    logger.debug(f"{prefix}{format_node_for_debug(node, content_bytes)} {field_name_str}")

    if current_depth < max_depth:
        for child_node in node.children:
            log_ast_node_structure(origin_message, child_node, content_bytes, max_depth, current_depth + 1, prefix + "  |")

def log_query_match_details(
    parser_name: str,
    source_file_id: str,
    query_name: str,
    match_idx: int,
    captures_dict: Dict[str, List[TSNODE_TYPE]],
    content_bytes: bytes,
    focus_captures: Optional[List[str]] = None
):
    """
    Logs details about a successful query match, including specified captures.
    """
    log_prefix = f"UTILS_QUERY_MATCH ({parser_name} - {source_file_id})"
    logger.debug(f"{log_prefix}: Query='{query_name}', MatchIndex={match_idx}")

    captures_to_log = focus_captures if focus_captures else sorted(list(captures_dict.keys()))

    for cap_name in captures_to_log:
        captured_nodes_list = captures_dict.get(cap_name)
        if captured_nodes_list:
            for i, node_item in enumerate(captured_nodes_list):
                logger.debug(f"{log_prefix}:   @{cap_name}[{i}]: {format_node_for_debug(node_item, content_bytes)}")
        else:
            if focus_captures and cap_name in focus_captures:
                logger.debug(f"{log_prefix}:   @{cap_name}: Not captured in this match.")

def get_ast_node_path_to_root(node: Optional[TSNODE_TYPE]) -> str:
    """
    Generates a string representing the path of node types (and field names if available)
    from the given node up to the root of the AST.
    """
    if not node:
        return "UnknownPath(NoneNode)"

    path_parts = []
    current = node
    depth_limit = 20

    while current and depth_limit > 0:
        field_name_part = ""
        if current.parent:
            try:
                for i in range(current.parent.child_count):
                    if current.parent.child(i).id == current.id:
                        field_name = current.parent.field_name_for_child(i)
                        if field_name: field_name_part = f"[{field_name}]"
                        break
            except Exception: pass

        path_parts.append(f"{current.type}{field_name_part}")
        current = current.parent
        depth_limit -= 1

    if depth_limit == 0 and current:
        path_parts.append("...(path truncated due to depth limit)")

    return " > ".join(reversed(path_parts)) if path_parts else "Node(UnknownPath)"

def parse_temp_code_entity_id(temp_code_entity_id: str) -> Optional[Tuple[str, int]]:
    """
    Parses a temporary CodeEntity ID of the format "Full::Qualified::Name(params)@line_number".
    """
    try:
        parts = temp_code_entity_id.rsplit('@', 1)
        if len(parts) == 2:
            fqn_part = parts[0]
            line_number = int(parts[1])
            return fqn_part, line_number
    except ValueError:
        logger.warning(f"UTILS: Could not parse line_number from temp_code_entity_id: '{temp_code_entity_id}' (ValueError).")
    except Exception as e:
        logger.error(f"UTILS: Error parsing temp_code_entity_id '{temp_code_entity_id}'.", exc_info=e)
    return None
