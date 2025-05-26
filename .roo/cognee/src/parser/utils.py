import asyncio
import aiofiles
from typing import Optional, Any

try:
    from cognee.shared.logging_utils import get_logger
    logger = get_logger(__name__)
except ImportError:
    class PrintLogger:
        def error(self, msg, exc_info=None): print(f"ERROR: {msg}" + (f" | Exception: {exc_info}" if exc_info else ""))
        def warning(self, msg): print(f"WARNING: {msg}")
        def info(self, msg): print(f"INFO: {msg}")
        def debug(self, msg): print(f"DEBUG: {msg}")
    logger = PrintLogger()

TS_AVAILABLE = True
TSNODE_TYPE = Any
try:
    from tree_sitter import Node as TSNODE_TYPE_REAL
    TSNODE_TYPE = TSNODE_TYPE_REAL
except ImportError:
    logger.warning("Tree-sitter library not found. AST-based parsing will be unavailable for some languages.")
    TS_AVAILABLE = False

async def read_file_content(file_path: str) -> Optional[str]:
    try:
        async with aiofiles.open(file_path, mode="r", encoding="utf-8", errors="ignore") as f:
            content = await f.read()
        return content
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        return None
    except IOError as e:
        logger.error(f"IOError reading file {file_path}", exc_info=e)
        return None
    except Exception as e:
        logger.error(f"Unexpected error reading file {file_path}", exc_info=e)
        return None

def get_node_text(node: TSNODE_TYPE, content_bytes: bytes) -> Optional[str]:
    if not TS_AVAILABLE or node is None:
        return None
    try:
        start = max(0, node.start_byte)
        end = min(len(content_bytes), node.end_byte)
        if start >= end: return ""
        text = content_bytes[start:end].decode("utf-8", "ignore")
        return text
    except Exception as e:
        logger.error(f"Error extracting text from tree-sitter node.", exc_info=True)
        return None

def parse_text_chunk_id(text_chunk_id: str) -> Optional[tuple[str, int]]:
    try:
        parts = text_chunk_id.rsplit(':', 1)
        if len(parts) == 2:
            return parts[0], int(parts[1])
    except ValueError:
        logger.error(f"Could not parse chunk_index (int) from text_chunk_id: {text_chunk_id}")
    except Exception as e:
        logger.error(f"Error parsing text_chunk_id '{text_chunk_id}'.", exc_info=e)
    return None

def parse_code_entity_id(code_entity_id: str) -> Optional[tuple[str, str, str, int]]:
    try:
        parts = code_entity_id.rsplit(':', 3)
        if len(parts) == 4:
            return parts[0], parts[1], parts[2], int(parts[3])
    except ValueError:
        logger.error(f"Could not parse index (int) from code_entity_id: {code_entity_id}")
    except Exception as e:
        logger.error(f"Error parsing code_entity_id '{code_entity_id}'.", exc_info=e)
    return None
