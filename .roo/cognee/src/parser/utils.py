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
        start, end = node.start_byte, node.end_byte
        if start < 0 or end > len(content_bytes) or start > end:
             logger.warning(f"UTILS: Node byte range [{start}-{end}] invalid for content length {len(content_bytes)}. Node type: {node.type}. Clamping.")
             start, end = max(0, start), min(len(content_bytes), end)
             if start >= end: return ""
        return content_bytes[start:end].decode("utf-8", "ignore")
    except Exception as e:
        logger.error(f"UTILS: Error extracting text from node (Type: {node.type}, Range: {node.start_byte}-{node.end_byte}).", exc_info=True)
        return None

def format_node_for_debug(node: Optional[TSNODE_TYPE], content_bytes: Optional[bytes] = None, max_text_preview: int = 60) -> str:
    """Creates a concise, readable string representation of a tree-sitter node for logging."""
    if not node:
        return "Node:None"
    text_preview = ""
    if content_bytes:
        raw_text = get_node_text(node, content_bytes)
        if raw_text is not None:
            first_line = raw_text.strip().splitlines()[0] if raw_text.strip() else ""
            text_preview = f"'{first_line[:max_text_preview]}{'...' if len(first_line) > max_text_preview else ''}'"
        else:
            text_preview = "[Error getting text]"
    return f"Node(Type='{node.type}', Line={node.start_point[0]}, Text={text_preview})"

def get_ast_node_path_to_root(node: Optional[TSNODE_TYPE]) -> str:
    """Generates a string representing the path of node types up to the root of the AST."""
    if not node:
        return "UnknownPath(NoneNode)"
    path_parts = []
    current = node
    for _ in range(20):
        if not current: break
        field_name = ""
        if current.parent:
            try:
                for i in range(current.parent.child_count):
                    if current.parent.child(i).id == current.id:
                        field_name = current.parent.field_name_for_child(i)
                        break
            except Exception: pass
        path_parts.append(f"{current.type}{'[' + field_name + ']' if field_name else ''}")
        current = current.parent
    return " > ".join(reversed(path_parts))

def parse_temp_code_entity_id(temp_code_entity_id: str) -> Optional[Tuple[str, int]]:
    """Parses a temporary CodeEntity ID of the format 'FQN@line_number'."""
    try:
        fqn_part, line_number_str = temp_code_entity_id.rsplit('@', 1)
        return fqn_part, int(line_number_str)
    except (ValueError, IndexError):
        logger.warning(f"UTILS: Could not parse temporary ID format: '{temp_code_entity_id}'.")
        return None
