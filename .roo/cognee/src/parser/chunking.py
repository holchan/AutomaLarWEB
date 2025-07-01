from typing import List
from .entities import TextChunk
from .utils import logger

def generate_text_chunks_from_slice_lines(
    source_file_id: str,
    full_content_string: str,
    slice_lines: List[int]
) -> List[TextChunk]:
    """
    Generates TextChunk objects from a full file string based on 0-indexed slice_lines.
    """
    log_prefix = f"CHUNKER ({source_file_id})"
    logger.debug(f"{log_prefix}: Starting chunk generation. Received {len(slice_lines)} slice lines for content of length {len(full_content_string)}.")

    if not full_content_string.strip() or not slice_lines:
        if slice_lines and full_content_string.strip():
            logger.warning(f"{log_prefix}: Received slice_lines but content is empty/whitespace. This is unusual. Returning no chunks.")
        return []

    lines_in_file = full_content_string.splitlines(keepends=True)
    num_total_lines = len(lines_in_file)
    text_chunks: List[TextChunk] = []
    chunk_index = 0

    valid_slice_starts_0 = sorted([sline for sline in set(slice_lines) if 0 <= sline < num_total_lines])

    if not valid_slice_starts_0:
        logger.warning(f"{log_prefix}: All provided slice_lines were out of bounds for file with {num_total_lines} lines. Creating a single chunk for the whole file.")
        if num_total_lines > 0:
            chunk_content = "".join(lines_in_file)
            chunk_id = f"{source_file_id}|0"
            text_chunks.append(
                TextChunk(
                    id=chunk_id,
                    start_line=1,
                    end_line=num_total_lines,
                    chunk_content=chunk_content
                )
            )
            logger.debug(f"{log_prefix}: Created fallback single TextChunk '{chunk_id}' (Lines 1-{num_total_lines}).")
        return text_chunks

    for i, start_line_0 in enumerate(valid_slice_starts_0):
        if i + 1 < len(valid_slice_starts_0):
            end_line_0 = valid_slice_starts_0[i+1] - 1
        else:
            end_line_0 = num_total_lines - 1

        if end_line_0 < start_line_0:
            logger.warning(f"{log_prefix}: Invalid slice segment. Start line {start_line_0} is after calculated end line {end_line_0}. This can happen with duplicate slice lines. Skipping empty segment.")
            continue

        start_line_1 = start_line_0 + 1
        end_line_1 = end_line_0 + 1

        chunk_id = f"{source_file_id}|{chunk_index}@{start_line_1}-{end_line_1}"
        current_chunk_content = "".join(lines_in_file[start_line_0 : end_line_0 + 1])

        text_chunks.append(
            TextChunk(
                id=chunk_id,
                start_line=start_line_1,
                end_line=end_line_1,
                chunk_content=current_chunk_content
            )
        )
        logger.debug(f"{log_prefix}: Created TextChunk '{chunk_id}'.")
        chunk_index += 1

    logger.info(f"{log_prefix}: Finished. Generated {len(text_chunks)} TextChunk(s).")
    return text_chunks
