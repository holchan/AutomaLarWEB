import pytest
from src.parser.chunking import generate_text_chunks_from_slice_lines
from src.parser.entities import TextChunk

pytestmark = pytest.mark.asyncio

def test_generate_chunks_empty_input():
    assert generate_text_chunks_from_slice_lines("file|id", "", [0]) == []
    assert generate_text_chunks_from_slice_lines("file|id", " ", []) == []
    assert generate_text_chunks_from_slice_lines("file|id", "some content", []) == []

def test_generate_chunks_single_chunk():
    content = "line 1\nline 2\nline 3"
    source_file_id = "repo|file.txt"
    chunks = generate_text_chunks_from_slice_lines(source_file_id, content, [0])

    assert len(chunks) == 1
    chunk = chunks[0]
    assert isinstance(chunk, TextChunk)
    assert chunk.id == "repo|file.txt|0@1-3"
    assert chunk.start_line == 1
    assert chunk.end_line == 3
    assert chunk.chunk_content == content

def test_generate_chunks_multiple_chunks():
    content = "line 1\nline 2\nline 3\nline 4\nline 5"
    source_file_id = "repo|file.py"
    slice_lines = [0, 3]

    chunks = generate_text_chunks_from_slice_lines(source_file_id, content, slice_lines)

    assert len(chunks) == 2

    chunk1 = chunks[0]
    assert chunk1.id == "repo|file.py|0@1-3"
    assert chunk1.start_line == 1
    assert chunk1.end_line == 3
    assert chunk1.chunk_content == "line 1\nline 2\nline 3\n"

    chunk2 = chunks[1]
    assert chunk2.id == "repo|file.py|1@4-5"
    assert chunk2.start_line == 4
    assert chunk2.end_line == 5
    assert chunk2.chunk_content == "line 4\nline 5"

def test_generate_chunks_out_of_bounds_slice_lines():
    content = "line 1\nline 2"
    source_file_id = "repo|file.js"
    chunks = generate_text_chunks_from_slice_lines(source_file_id, content, [100])

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.id == "repo|file.js|0@1-2"
    assert chunk.start_line == 1
    assert chunk.end_line == 2
    assert chunk.chunk_content == content

def test_generate_chunks_slice_line_at_end():
    content = "line 1\nline 2\nline 3"
    source_file_id = "repo|file.c"
    slice_lines = [0, 2]
    chunks = generate_text_chunks_from_slice_lines(source_file_id, content, slice_lines)

    assert len(chunks) == 2

    chunk1 = chunks[0]
    assert chunk1.id == "repo|file.c|0@1-2"
    assert chunk1.start_line == 1
    assert chunk1.end_line == 2
    assert chunk1.chunk_content == "line 1\nline 2\n"

    chunk2 = chunks[1]
    assert chunk2.id == "repo|file.c|1@3-3"
    assert chunk2.start_line == 3
    assert chunk2.end_line == 3
    assert chunk2.chunk_content == "line 3"

def test_generate_chunks_with_duplicate_and_unsorted_slice_lines():
    content = "a\nb\nc\nd\ne"
    source_file_id = "repo|file.rs"
    slice_lines = [3, 0, 3]
    chunks = generate_text_chunks_from_slice_lines(source_file_id, content, slice_lines)

    assert len(chunks) == 2
    assert chunks[0].id == "repo|file.rs|0@1-3"
    assert chunks[1].id == "repo|file.rs|1@4-5"
