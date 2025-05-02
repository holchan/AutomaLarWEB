# src/parser/chunking.py
from typing import List
from .config import CHUNK_SIZE, CHUNK_OVERLAP
from .utils import logger

def basic_chunker(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Splits a given text into smaller chunks based on character count with optional overlap.

    Args:
        text: The text content to be chunked.
        size: The maximum number of characters in each chunk. Defaults to CHUNK_SIZE from config.
        overlap: The number of characters to overlap between consecutive chunks.
                Defaults to CHUNK_OVERLAP from config. Adjusted if invalid.

    Returns:
        A list of strings, where each string is a chunk of the original text.
        Returns an empty list if the input text is empty or contains only whitespace.
    """
    if not text or not text.strip():
        logger.debug("basic_chunker received empty or whitespace-only text.")
        return []
    if size <= 0:
        logger.warning(f"basic_chunker received invalid chunk size: {size}. Defaulting to 100.")
        size = 100
    if overlap < 0:
        logger.warning(f"basic_chunker received negative overlap: {overlap}. Setting overlap to 0.")
        overlap = 0
    if overlap >= size:
        logger.warning(f"basic_chunker overlap ({overlap}) >= size ({size}). Setting overlap to size // 4.")
        overlap = max(0, size // 4)

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + size, text_len)
        chunk = text[start:end]

        if chunk.strip():
            chunks.append(chunk)

        step = size - overlap
        if step <= 0:
            logger.warning(f"Chunking step size is non-positive ({step}) with size={size}, overlap={overlap}. Adjusting step to 1 to ensure progress.")
            step = 1

        start += step

        if start >= text_len and len(chunks) > 0 and chunks[-1] == text[start-step:]:
            break

    logger.debug(f"basic_chunker created {len(chunks)} chunks from text of length {text_len}.")
    return chunks
