import pytest
# Import the function to test and config values if needed
from src.parser.chunking import basic_chunker, CHUNK_SIZE, CHUNK_OVERLAP

# Define some constants for clarity in tests, can use defaults too
DEFAULT_SIZE = CHUNK_SIZE # Use value from config
DEFAULT_OVERLAP = CHUNK_OVERLAP # Use value from config

# Define custom size/overlap for specific tests
TEST_SIZE = 50
TEST_OVERLAP = 10

def test_basic_chunker_empty_string():
    """Test chunking an empty string."""
    assert basic_chunker("", size=TEST_SIZE, overlap=TEST_OVERLAP) == []

def test_basic_chunker_whitespace_only():
    """Test chunking a string with only whitespace."""
    assert basic_chunker("   \n \t ", size=TEST_SIZE, overlap=TEST_OVERLAP) == []

def test_basic_chunker_short_string():
    """Test chunking a string shorter than the chunk size."""
    text = "This string is shorter."
    chunks = basic_chunker(text, size=TEST_SIZE, overlap=TEST_OVERLAP)
    # Expect a single chunk containing the original text
    assert len(chunks) == 1
    assert chunks[0] == text

def test_basic_chunker_exact_size():
    """Test chunking a string exactly the chunk size."""
    text = "A" * TEST_SIZE
    chunks = basic_chunker(text, size=TEST_SIZE, overlap=TEST_OVERLAP)
    # Expect a single chunk containing the original text
    assert len(chunks) == 1
    assert chunks[0] == text

def test_basic_chunker_long_string_no_overlap():
    """Test chunking a long string with zero overlap."""
    size = 30 # Use a smaller size for easier calculation
    text = "Chunk1Content..." * size + "Chunk2MoreContent" * size + "End"
    expected_chunk1_content = "Chunk1Content..." * size
    expected_chunk2_content = "Chunk2MoreContent" * size

    # Use a chunk size large enough to capture the repeated sections
    test_chunk_size = size * len("Chunk1Content...")
    chunks = basic_chunker(text, size=test_chunk_size, overlap=0)

    # Expect 3 chunks: first full, second full, remaining "End"
    assert len(chunks) == 3
    assert chunks[0] == expected_chunk1_content
    assert chunks[1] == expected_chunk2_content
    assert chunks[2] == "End"

def test_basic_chunker_long_string_with_overlap():
    """Test chunking with overlap calculation."""
    text = "0123456789" * 15 # 150 chars
    size = 50
    overlap = 10
    step = size - overlap # 40

    chunks = basic_chunker(text, size=size, overlap=overlap)

    # Expected chunks based on size 50, overlap 10 (step 40):
    # Chunk 1: text[0 : 50]   (Indices 0-49)
    # Chunk 2: text[40 : 90]  (Indices 40-89)
    # Chunk 3: text[80 : 130] (Indices 80-129)
    # Chunk 4: text[120 : 150] (Indices 120-149, length 30)

    assert len(chunks) == 4, f"Expected 4 chunks, got {len(chunks)}"
    assert chunks[0] == text[0:50]
    assert chunks[1] == text[40:90]
    assert chunks[2] == text[80:130]
    assert chunks[3] == text[120:150]

    # Verify overlap content between consecutive chunks
    assert chunks[0].endswith(text[40:50]), "Overlap mismatch between chunk 0 and 1"
    assert chunks[1].startswith(text[40:50]), "Overlap mismatch between chunk 0 and 1"
    assert chunks[1].endswith(text[80:90]), "Overlap mismatch between chunk 1 and 2"
    assert chunks[2].startswith(text[80:90]), "Overlap mismatch between chunk 1 and 2"
    assert chunks[2].endswith(text[120:130]), "Overlap mismatch between chunk 2 and 3"
    assert chunks[3].startswith(text[120:130]), "Overlap mismatch between chunk 2 and 3"

def test_basic_chunker_invalid_size():
    """Test behavior with invalid chunk size (<= 0)."""
    text = "Some text that should not be split unexpectedly."
    # Expect the chunker to return the whole text as a single chunk
    assert basic_chunker(text, size=0, overlap=10) == [text]
    assert basic_chunker(text, size=-5, overlap=10) == [text]

def test_basic_chunker_invalid_overlap():
    """Test behavior with invalid overlap values."""
    text = "0123456789" * 10 # 100 chars
    size = 50

    # Negative overlap should be treated as 0
    chunks_neg_overlap = basic_chunker(text, size=size, overlap=-10)
    assert len(chunks_neg_overlap) == 2, "Negative overlap should act like zero overlap"
    assert chunks_neg_overlap[0] == text[0:50]
    assert chunks_neg_overlap[1] == text[50:100]

    # Overlap >= size should default to size // 4 (50 // 4 = 12)
    # Step becomes size - overlap = 50 - 12 = 38
    chunks_large_overlap = basic_chunker(text, size=size, overlap=60)
    # Expected:
    # C1: 0-49
    # C2: 38-87 (start = 0 + 38 = 38, end = 38 + 50 = 88)
    # C3: 76-100 (start = 38 + 38 = 76, end = 76 + 50 = 126 -> clipped to 100)
    assert len(chunks_large_overlap) == 3, "Overlap >= size should default overlap"
    assert chunks_large_overlap[0] == text[0:50]
    assert chunks_large_overlap[1] == text[38:88]
    assert chunks_large_overlap[2] == text[76:100]

    # Overlap exactly equal to size, should also default to size // 4
    chunks_equal_overlap = basic_chunker(text, size=size, overlap=size)
    assert len(chunks_equal_overlap) == 3, "Overlap == size should default overlap"
    assert chunks_equal_overlap[0] == text[0:50]
    assert chunks_equal_overlap[1] == text[38:88]
    assert chunks_equal_overlap[2] == text[76:100]

def test_basic_chunker_prevents_infinite_loop():
    """Test edge case where step size might become non-positive without correction."""
    # Size 10, Overlap 9 -> Step 1 (should work)
    text = "0123456789" * 3 # 30 chars
    chunks = basic_chunker(text, size=10, overlap=9)
    # Expected: 0-9, 1-10, 2-11, ..., 20-29
    assert len(chunks) == 21 # Should progress character by character effectively

    # Size 10, Overlap 10 (corrected to overlap 2, step 8)
    chunks_corrected = basic_chunker(text, size=10, overlap=10)
    # Expected: 0-9, 8-17, 16-25, 24-29
    assert len(chunks_corrected) == 4 # It should progress with corrected overlap
