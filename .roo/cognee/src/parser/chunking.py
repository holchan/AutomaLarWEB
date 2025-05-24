from typing import List
from .config import CHUNK_SIZE, CHUNK_OVERLAP
from .utils import logger

def basic_chunker(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Splits a given text into smaller chunks based on character count with optional overlap.
    Args:
        text: The text content to be chunked.
        size: The maximum number of characters in each chunk. Defaults to CHUNK_SIZE.
        overlap: The number of characters to overlap between consecutive chunks.
                 Defaults to CHUNK_OVERLAP. Adjusted if invalid.
    Returns:
        A list of strings, where each string is a chunk of the original text.
        Returns an empty list if the input text is empty or contains only whitespace.
    """
    if not text or text.isspace():
        return []

    if size <= 0:
        logger.warning(f"Invalid chunk size {size} for text (len {len(text)}). Returning text as a single chunk.")
        return [text]

    original_overlap_for_logging = overlap
    if overlap < 0:
        logger.debug(f"Negative overlap {original_overlap_for_logging} provided. Setting overlap to 0.")
        overlap = 0

    if overlap >= size:
        adjusted_overlap = max(0, size // 4)
        logger.warning(
            f"Overlap {original_overlap_for_logging} was >= size {size}. Adjusted overlap to {adjusted_overlap}."
        )
        overlap = adjusted_overlap

    chunks: List[str] = []
    start = 0
    text_len = len(text)

    if text_len <= size:
        return [text]

    while start < text_len:
        end = min(start + size, text_len)
        chunk = text[start:end]
        chunks.append(chunk)

        step = size - overlap
        if step <= 0:
            logger.error(
                f"Step size in chunker became non-positive ({step}) with size={size}, overlap={overlap}. "
                f"Text length: {text_len}, current start: {start}. Breaking to prevent infinite loop."
            )
            break

        start += step

    return chunks
