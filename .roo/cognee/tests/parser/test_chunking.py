import pytest
from src.parser.chunking import basic_chunker, CHUNK_SIZE, CHUNK_OVERLAP

DEFAULT_SIZE = CHUNK_SIZE
DEFAULT_OVERLAP = CHUNK_OVERLAP

TEST_SIZE = 50
TEST_OVERLAP = 10

def test_basic_chunker_empty_string():
    assert basic_chunker("", size=TEST_SIZE, overlap=TEST_OVERLAP) == []

def test_basic_chunker_whitespace_only():
    assert basic_chunker("   \n \t ", size=TEST_SIZE, overlap=TEST_OVERLAP) == []

def test_basic_chunker_short_string():
    text = "This string is shorter."
    chunks = basic_chunker(text, size=TEST_SIZE, overlap=TEST_OVERLAP)
    assert len(chunks) == 1
    assert chunks[0] == text

def test_basic_chunker_exact_size():
    text = "A" * TEST_SIZE
    chunks = basic_chunker(text, size=TEST_SIZE, overlap=TEST_OVERLAP)
    assert len(chunks) == 1
    assert chunks[0] == text

def test_basic_chunker_long_string_no_overlap():
    size = 10
    text = "0123456789ABCDEFGHIJabcdefghij"
    chunks = basic_chunker(text, size=size, overlap=0)
    assert len(chunks) == 3
    assert chunks[0] == "0123456789"
    assert chunks[1] == "ABCDEFGHIJ"
    assert chunks[2] == "abcdefghij"

def test_basic_chunker_long_string_with_overlap():
    text = "0123456789" * 15
    size = 50
    overlap = 10

    chunks = basic_chunker(text, size=size, overlap=overlap)
    assert len(chunks) == 4
    assert chunks[0] == text[0:50]
    assert chunks[1] == text[40:90]
    assert chunks[2] == text[80:130]
    assert chunks[3] == text[120:150]

    assert chunks[0].endswith(text[40:50])
    assert chunks[1].startswith(text[40:50])
    assert chunks[1].endswith(text[80:90])
    assert chunks[2].startswith(text[80:90])
    assert chunks[2].endswith(text[120:130])
    assert chunks[3].startswith(text[120:130])

def test_basic_chunker_invalid_size():
    text = "Some text that should not be split unexpectedly."
    assert basic_chunker(text, size=0, overlap=10) == [text]
    assert basic_chunker(text, size=-5, overlap=10) == [text]

def test_basic_chunker_invalid_overlap():
    text = "0123456789" * 10
    size = 50

    chunks_neg_overlap = basic_chunker(text, size=size, overlap=-10)
    assert len(chunks_neg_overlap) == 2
    assert chunks_neg_overlap[0] == text[0:50]
    assert chunks_neg_overlap[1] == text[50:100]

    chunks_large_overlap = basic_chunker(text, size=size, overlap=60)
    assert len(chunks_large_overlap) == 3
    assert chunks_large_overlap[0] == text[0:50]
    assert chunks_large_overlap[1] == text[38:88]
    assert chunks_large_overlap[2] == text[76:100]

    chunks_equal_overlap = basic_chunker(text, size=size, overlap=size)
    assert len(chunks_equal_overlap) == 3
    assert chunks_equal_overlap[0] == text[0:50]
    assert chunks_equal_overlap[1] == text[38:88]
    assert chunks_equal_overlap[2] == text[76:100]

def test_basic_chunker_prevents_infinite_loop():
    text = "0123456789" * 3
    chunks = basic_chunker(text, size=10, overlap=9)
    assert len(chunks) == 30

    chunks_corrected = basic_chunker(text, size=10, overlap=10)
    assert len(chunks_corrected) == 4
