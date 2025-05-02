# src/parser/utils.py
import aiofiles
import logging
from typing import Optional, Any

try:
    from cognee.shared.logging_utils import get_logger
    logger = get_logger(__name__)
    logger.info("Using Cognee logger for parser module.")
except ImportError:
    logger = logging.getLogger("standalone_parser")
    if not logger.hasHandlers():
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        if os.environ.get("PARSER_LOG_LEVEL", "").lower() == "debug":
            logger.setLevel(logging.DEBUG)
        logger.propagate = False
    logger.info(f"Cognee logger not found. Using standard Python logging for parser module (Level: {logger.getLevelName(logger.level)}).")

try:
    from tree_sitter import Node as TSNODE_TYPE
    TS_AVAILABLE = True
    logger.debug("Tree-sitter Node type imported successfully.")
except ImportError:
    logger.debug("Tree-sitter library not found, using 'Any' for TSNODE_TYPE hint.")
    TSNODE_TYPE = Any
    TS_AVAILABLE = False

async def read_file_content(file_path: str) -> Optional[str]:
    """
    Safely reads file content asynchronously with UTF-8 encoding, ignoring errors.

    Args:
        file_path: The absolute path to the file.

    Returns:
        The file content as a string, or None if an error occurs.
    """

    try:
        async with aiofiles.open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = await f.read()
            logger.debug(f"Successfully read {len(content)} characters from {file_path} using aiofiles.")
            return content
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        return None
    except IOError as e:
        logger.error(f"IOError reading file {file_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error reading file {file_path}: {e}", exc_info=True)
        return None

def get_node_text(node: TSNODE_TYPE, content_bytes: bytes) -> Optional[str]:
    """
    Extracts text from a tree-sitter node safely.

    Args:
        node: The tree_sitter.Node object (or Any if library not present).
        content_bytes: The byte representation of the source file content.

    Returns:
        The decoded text of the node, or None if an error occurs or tree-sitter is unavailable.
    """

    if not TS_AVAILABLE or not hasattr(node, 'start_byte') or not hasattr(node, 'end_byte'):
        logger.debug("Tree-sitter not available or invalid node type passed to get_node_text.")
        return None
    try:
        start = max(0, node.start_byte)
        end = min(len(content_bytes), node.end_byte)
        if start >= end:
            logger.warning(f"Node {node.type} at {node.start_point}-{node.end_point} has invalid byte range: start={start}, end={end}. Returning empty string.")
            return ""

        text = content_bytes[start:end].decode("utf-8", "ignore")
        return text
    except IndexError as e:
        logger.error(f"IndexError getting text for node type {getattr(node, 'type', 'unknown')} at {getattr(node, 'start_point', '?')}-{getattr(node, 'end_point', '?')}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error getting node text for node type {getattr(node, 'type', 'unknown')}: {e}", exc_info=True)
        return None
