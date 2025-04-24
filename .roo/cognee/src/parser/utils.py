# src/parser/utils.py
import aiofiles
import logging
from typing import Optional

# --- Logger Setup ---
# Attempt to use Cognee's logger if available, otherwise use standard logging
try:
    from cognee.shared.logging_utils import get_logger
    # Assuming get_logger configures the logger appropriately
    logger = get_logger(__name__)
    logger.info("Using Cognee logger for parser module.")
except ImportError:
    logger = logging.getLogger("cognee_parser") # Use a specific name
    # Basic config if running standalone or Cognee logger isn't setup
    if not logger.hasHandlers():
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO) # Default level, can be configured
        logger.propagate = False # Prevent duplicate logs if root logger is configured
    logger.info("Cognee logger not found. Using standard Python logging for parser module.")


# --- Tree-sitter Node Type Hint ---
# Define a placeholder type for tree_sitter.Node if the library isn't installed
# This helps with type hinting without making tree-sitter a hard dependency for basic checks
try:
    from tree_sitter import Node as TSNODE_TYPE
    TS_AVAILABLE = True
except ImportError:
    TSNODE_TYPE = type(None) # type: ignore
    TS_AVAILABLE = False

# --- Helper Functions ---

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
            logger.debug(f"Successfully read {len(content)} characters from {file_path}")
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
        node: The tree_sitter.Node object.
        content_bytes: The byte representation of the source file content.

    Returns:
        The decoded text of the node, or None if an error occurs or tree-sitter is unavailable.
    """
    if not TS_AVAILABLE or not isinstance(node, TSNODE_TYPE):
        logger.debug("Tree-sitter not available or invalid node type passed to get_node_text.")
        return None
    try:
        text = content_bytes[node.start_byte:node.end_byte].decode("utf-8", "ignore")
        return text
    except IndexError:
        logger.error(f"IndexError getting text for node type {node.type} at {node.start_point}-{node.end_point}")
        return None
    except Exception as e:
        logger.error(f"Error getting node text for node type {node.type}: {e}", exc_info=True)
        return None
