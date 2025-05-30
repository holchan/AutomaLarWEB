import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import aiofiles
from typing import Optional, Any

from src.parser import utils
from src.parser.utils import TSNODE_TYPE, TS_AVAILABLE

pytestmark = pytest.mark.asyncio

async def test_read_file_content_success(tmp_path: Path):
    test_content = "Line 1\nLine 2\nUTF-8 char: é"
    test_file = tmp_path / "test.txt"
    test_file.write_text(test_content, encoding="utf-8")
    content = await utils.read_file_content(str(test_file))
    assert content == test_content

async def test_read_file_content_not_found(tmp_path: Path):
    non_existent_file = tmp_path / "not_found.txt"
    with patch('src.parser.utils.logger') as mock_logger:
        content = await utils.read_file_content(str(non_existent_file))
        assert content is None
        mock_logger.error.assert_called_once_with(f"File not found: {non_existent_file}")

@patch('aiofiles.open')
async def test_read_file_content_io_error(mock_aio_open):
    fake_path = "/fake/io_error.txt"
    mock_aio_open.side_effect = IOError("Disk read error")
    with patch('src.parser.utils.logger') as mock_logger:
        content = await utils.read_file_content(fake_path)
        assert content is None
        mock_aio_open.assert_called_once_with(fake_path, mode="r", encoding="utf-8", errors="ignore")
        mock_logger.error.assert_called_once_with(f"IOError reading file {fake_path}", exc_info=ANY)

@pytest.mark.skipif(not TS_AVAILABLE, reason="Tree-sitter library not available")
def test_get_node_text_success():
    mock_node = MagicMock(spec=TSNODE_TYPE)
    mock_node.start_byte = 6
    mock_node.end_byte = 15
    content_bytes = b"Hello world example text!"
    text = utils.get_node_text(mock_node, content_bytes)
    assert text == "world exa"

@pytest.mark.skipif(not TS_AVAILABLE, reason="Tree-sitter library not available")
def test_get_node_text_invalid_range():
    mock_node = MagicMock(spec=TSNODE_TYPE)
    mock_node.start_byte = 10
    mock_node.end_byte = 5
    content_bytes = b"Some content bytes"
    with patch('src.parser.utils.logger') as mock_logger:
        text = utils.get_node_text(mock_node, content_bytes)
        assert text == ""

@pytest.mark.skipif(not TS_AVAILABLE, reason="Tree-sitter library not available")
def test_get_node_text_index_error():
    mock_node = MagicMock(spec=TSNODE_TYPE)
    mock_node.start_byte = 0
    mock_node.end_byte = 30
    content_bytes = b"Short"
    with patch('src.parser.utils.logger') as mock_logger:
        text = utils.get_node_text(mock_node, content_bytes)
        assert text == "Short"
        mock_logger.error.assert_called_once()
        assert "Error extracting text" in mock_logger.error.call_args[0][0]


@patch('src.parser.utils.TS_AVAILABLE', False)
def test_get_node_text_ts_unavailable():
    mock_node = MagicMock()
    content_bytes = b"Some content"
    with patch('src.parser.utils.logger') as mock_logger:
        text = utils.get_node_text(mock_node, content_bytes)
        assert text is None


def test_logger_instance():
    try:
        from cognee.shared.logging_utils import get_logger as get_cognee_logger
        actual_logger = utils.logger
        assert hasattr(actual_logger, 'info')
    except ImportError:
        assert isinstance(utils.logger, utils.PrintLogger)
