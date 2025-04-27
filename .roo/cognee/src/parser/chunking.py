# src/parser/chunking.py
from typing import List
from .config import CHUNK_SIZE, CHUNK_OVERLAP
from .utils import logger # Use logger from utils

def basic_chunker(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Splits a given text into smaller chunks based on character count with optional overlap.

    This function provides a simple method for breaking down large text content
    into manageable segments. It handles edge cases like empty input, invalid
    size/overlap values, and ensures that progress is made through the text.

    Args:
        text: The text content to be chunked.
        size: The maximum number of characters in each chunk. Defaults to CHUNK_SIZE from config.
        overlap: The number of characters to overlap between consecutive chunks.
                 Defaults to CHUNK_OVERLAP from config. If overlap is negative or
                 greater than or equal to size, it is adjusted.

    Returns:
        A list of strings, where each string is a chunk of the original text.
        Returns an empty list if the input text is empty or contains only whitespace.
    """
    if not text or not text.strip():
        logger.debug("basic_chunker received empty or whitespace-only text.")
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

    # Use a while True loop and break explicitly
    while start < text_len: # Change loop condition
        end = min(start + size, text_len)
        chunk = text[start:end]

        if chunk.strip(): # Only add non-empty chunks
            chunks.append(chunk)

        # Calculate the start of the next chunk
        step = size - overlap
        if step <= 0:
            step = 1 # Ensure progress

        # --- Refined Logic ---
        # If the current chunk reached the end, we are done.
        if end == text_len:
            break
        start += step

    logger.debug(f"basic_chunker created {len(chunks)} chunks from text of length {text_len}.")
    return chunks

# --- Potential Future Enhancements ---
# Could add more sophisticated chunking logic here later:
# - Sentence-based chunking using NLP libraries (like spaCy or NLTK)
# - Structure-aware chunking (e.g., chunking based on Markdown sections or code blocks)
# - RecursiveCharacterTextSplitter pattern from LangChain
