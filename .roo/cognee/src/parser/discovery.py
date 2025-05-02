# src/parser/discovery.py
import os
import asyncio
from typing import AsyncGenerator, Tuple, Set
from pathlib import Path
from .config import IGNORED_DIRS, IGNORED_FILES, SUPPORTED_EXTENSIONS
from .utils import logger

_IGNORED_DIRS: Set[str] = set(IGNORED_DIRS)
_IGNORED_FILES: Set[str] = set(IGNORED_FILES)

async def discover_files(repo_path: str) -> AsyncGenerator[Tuple[str, str, str], None]:
    """
    Asynchronously discovers supported files within a given repository path.

    Walks the directory tree, respects IGNORED patterns, identifies supported
    files based on SUPPORTED_EXTENSIONS, and yields file details.

    Args:
        repo_path: The absolute path to the root of the repository directory to scan.

    Yields:
        A tuple for each discovered supported file:
        - absolute_path (str): The full, absolute path to the discovered file.
        - relative_path (str): The path to the file relative to the `repo_path`.
        - file_type (str): The key from `config.SUPPORTED_EXTENSIONS` corresponding
                        to the file's type (e.g., 'python', 'markdown', 'dockerfile').
    """
    abs_repo_path = os.path.abspath(repo_path)
    logger.info(f"Starting file discovery in: {abs_repo_path}")

    if not os.path.isdir(abs_repo_path):
        logger.error(f"Provided discovery path is not a valid directory: {abs_repo_path}")
        return

    processed_files_count = 0
    supported_files_count = 0

    for root, dirs, files in os.walk(abs_repo_path, topdown=True, onerror=lambda err: logger.error(f"Error walking directory: {err}")):
        dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS]

        for file in files:
            processed_files_count += 1
            if file in _IGNORED_FILES:
                logger.debug(f"Ignoring file based on exact match in IGNORED_FILES: {file}")
                continue

            is_ignored_by_pattern = False
            for ignored_pattern in _IGNORED_FILES:
                if ignored_pattern.startswith("*.") and file.endswith(ignored_pattern[1:]):
                    logger.debug(f"Ignoring file based on pattern {ignored_pattern}: {file}")
                    is_ignored_by_pattern = True
                    break
            if is_ignored_by_pattern:
                continue

            file_path = os.path.join(root, file)

            file_type = SUPPORTED_EXTENSIONS.get(file)
            if not file_type:
                _, ext = os.path.splitext(file)
                if not ext and file not in SUPPORTED_EXTENSIONS:
                    logger.debug(f"Skipping file without extension or explicit mapping: {file_path}")
                    continue
                file_type = SUPPORTED_EXTENSIONS.get(ext.lower())

            if file_type:
                try:
                    relative_path = os.path.relpath(file_path, abs_repo_path)
                    relative_path = str(Path(relative_path))

                    logger.debug(f"Discovered supported file: {relative_path} (Type: {file_type})")
                    supported_files_count += 1
                    yield file_path, relative_path, file_type

                    if supported_files_count % 500 == 0:
                        await asyncio.sleep(0.001)

                except ValueError as e:
                    logger.error(f"Could not determine relative path for {file_path} against {abs_repo_path}. Skipping. Error: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error processing file path {file_path}: {e}", exc_info=True)
            else:
                logger.debug(f"Skipping unsupported file type: {file_path}")

    logger.info(f"File discovery complete. Processed {processed_files_count} total files/links. Found {supported_files_count} supported files.")
