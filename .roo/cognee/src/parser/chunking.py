# src/parser/chunking.py
from typing import List
from .config import CHUNK_SIZE, CHUNK_OVERLAP
from .utils import logger # Use logger from utils

def basic_chunker(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Simple text chunker based on character count.

    Args:
        text: The text content to chunk.
        size: The desired maximum size of each chunk (in characters).
        overlap: The desired overlap between consecutive chunks (in characters).

    Returns:
        A list of text chunks.
    """
    if not text:
        logger.debug("basic_chunker received empty text.")
        return []
    if size <= 0:
        logger.error(f"basic_chunker received invalid chunk size: {size}. Returning single chunk.")
        return [text]
    if overlap < 0:
        logger.warning(f"basic_chunker received negative overlap: {overlap}. Setting overlap to 0.")
        overlap = 0
    if overlap >= size:
        logger.warning(f"basic_chunker overlap ({overlap}) >= size ({size}). Setting overlap to size // 4.")
        overlap = size // 4 # Prevent excessive overlap or no progress

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + size, text_len)
        chunk = text[start:end]
        if chunk.strip(): # Only add non-empty chunks
            chunks.append(chunk)

        next_start = start + size - overlap
        # Ensure progress is made, especially if overlap is large or size is small
        if next_start <= start:
             next_start = start + 1 # Force at least one character progress

        start = next_start

    logger.debug(f"basic_chunker created {len(chunks)} chunks from text of length {text_len}.")
    return chunks

# --- Potential Future Enhancements ---
# Could add more sophisticated chunking logic here later:
# - Sentence-based chunking using NLP libraries (like spaCy or NLTK)
# - Structure-aware chunking (e.g., chunking based on Markdown sections or code blocks)
# - RecursiveCharacterTextSplitter pattern from LangChain
