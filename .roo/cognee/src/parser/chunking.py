from typing import List
from .config import CHUNK_SIZE, CHUNK_OVERLAP
from .utils import logger

def basic_chunker(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    if not text or text.isspace(): return []
    if size <= 0: return [text]

    actual_overlap = overlap
    if actual_overlap < 0: actual_overlap = 0
    if actual_overlap >= size: actual_overlap = max(0, size // 4)

    chunks: List[str] = []
    start = 0
    text_len = len(text)
    if text_len <= size: return [text]

    while start < text_len:
        end = min(start + size, text_len)
        chunks.append(text[start:end])
        step = size - actual_overlap
        if step <= 0:
            logger.error(f"Chunker step became non-positive ({step}). Breaking.")
            break
        start += step
    return chunks
