# tests/parser/test_discovery.py
import pytest
from src.parser.discovery import discover_files
from src.parser.config import SUPPORTED_EXTENSIONS

@pytest.mark.asyncio
async def test_discover_files_basic():
    """Test basic file discovery in a simple directory."""
    # TODO: Implement test logic
    pass

@pytest.mark.asyncio
async def test_discover_files_ignores():
    """Test that discover_files correctly ignores files and directories."""
    # TODO: Implement test logic
    pass

@pytest.mark.asyncio
async def test_discover_files_extensions():
    """Test that discover_files only finds files with supported extensions."""
    # TODO: Implement test logic
    pass
