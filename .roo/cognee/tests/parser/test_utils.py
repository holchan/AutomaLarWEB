# .roo/cognee/tests/parser/test_utils.py
import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, mock_open
import aiofiles
import logging

from src.parser import utils
from src.parser.utils import TSNODE_TYPE, TS_AVAILABLE

pytestmark = pytest.mark.asyncio

async def test_read_file_content_success(tmp_path: Path):
    """Test successfully reading a file."""
    test_content = "Line 1\nLine 2\nUTF-8 char: é"
    test_file = tmp_path / "test.txt"
    test_file.write_text(test_content, encoding="utf-8")

    content = await utils.read_file_content(str(test_file))

    assert content == test_content

async def test_read_file_content_not_found(tmp_path: Path):
    """Test reading a non-existent file."""
    non_existent_file = tmp_path / "not_found.txt"

    with patch('src.parser.utils.logger') as mock_logger:
        content = await utils.read_file_content(str(non_existent_file))

        assert content is None
        mock_logger.error.assert_called_once()
        assert "File not found" in mock_logger.error.call_args[0][0]

@patch('aiofiles.open')
async def test_read_file_content_io_error(mock_aio_open):
    """Test handling IOError during file read."""
    fake_path = "/fake/io_error.txt"
    mock_aio_open.side_effect = IOError("Disk read error")

    with patch('src.parser.utils.logger') as mock_logger:
        content = await utils.read_file_content(fake_path)

        assert content is None
        mock_aio_open.assert_called_once_with(fake_path, "r", encoding="utf-8", errors="ignore")
        mock_logger.error.assert_called_once()
        assert f"IOError reading file {fake_path}" in mock_logger.error.call_args[0][0]

@pytest.mark.skipif(not TS_AVAILABLE, reason="Tree-sitter library not available")
def test_get_node_text_success():
    """Test extracting text from a valid mock node."""
    mock_node = MagicMock(spec=TSNODE_TYPE)
    mock_node.start_byte = 5
    mock_node.end_byte = 15
    mock_node.type = "identifier"
    mock_node.start_point = (0, 5)
    mock_node.end_point = (0, 15)
    content_bytes = b"Hello world example text!"

    text = utils.get_node_text(mock_node, content_bytes)

    assert text == "world exam"

@pytest.mark.skipif(not TS_AVAILABLE, reason="Tree-sitter library not available")
def test_get_node_text_invalid_range():
    """Test extracting text when start_byte >= end_byte."""
    mock_node = MagicMock(spec=TSNODE_TYPE)
    mock_node.start_byte = 10
    mock_node.end_byte = 5
    mock_node.type = "comment"
    mock_node.start_point = (1, 0)
    mock_node.end_point = (0, 5)
    content_bytes = b"Some content bytes"

    with patch('src.parser.utils.logger') as mock_logger:
        text = utils.get_node_text(mock_node, content_bytes)

        assert text == ""
        mock_logger.debug.assert_called_once()
        assert "invalid byte range" in mock_logger.debug.call_args[0][0]


@pytest.mark.skipif(not TS_AVAILABLE, reason="Tree-sitter library not available")
def test_get_node_text_index_error():
    """Test handling IndexError (e.g., end_byte out of bounds)."""
    mock_node = MagicMock(spec=TSNODE_TYPE)
    mock_node.start_byte = 5
    mock_node.end_byte = 30
    mock_node.type = "string_literal"
    mock_node.start_point = (2, 5)
    mock_node.end_point = (2, 30)
    content_bytes = b"Short content"

    with patch('src.parser.utils.logger') as mock_logger:
        text = utils.get_node_text(mock_node, content_bytes)

        assert text is None
        mock_logger.error.assert_called_once()
        assert "IndexError getting text" in mock_logger.error.call_args[0][0]

@patch('src.parser.utils.TS_AVAILABLE', False)
def test_get_node_text_ts_unavailable():
    """Test behavior when Tree-sitter is marked as unavailable."""
    mock_node = MagicMock()
    content_bytes = b"Some content"

    with patch('src.parser.utils.logger') as mock_logger:
        text = utils.get_node_text(mock_node, content_bytes)

        assert text is None
        mock_logger.debug.assert_called_with("Tree-sitter not available or invalid node type passed to get_node_text.")

def test_logger_instance():
    """Verify that the logger obtained is of the expected type (or fallback)."""
    try:
        from cognee.shared.logging_utils import LoggerInterface
        import importlib
        importlib.reload(utils)
        logger_instance = utils.logger
        assert not isinstance(logger_instance, logging.Logger) or logger_instance.name != "parser_dummy_logger"
        assert hasattr(logger_instance, 'info')
        assert hasattr(logger_instance, 'error')
    except ImportError:
        logger_instance = utils.logger
        assert isinstance(logger_instance, logging.Logger)
        assert logger_instance.name == "parser_dummy_logger" or logger_instance.name == "standalone_parser"
