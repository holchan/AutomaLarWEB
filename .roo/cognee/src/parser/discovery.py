# src/parser/discovery.py
import os
from typing import AsyncGenerator, Tuple, Set
from .config import IGNORED_DIRS, IGNORED_FILES, SUPPORTED_EXTENSIONS
from .utils import logger

# Pre-compile ignored patterns for potentially faster checks if needed,
# though direct set lookups are usually fast enough.
_IGNORED_DIRS: Set[str] = set(IGNORED_DIRS)
_IGNORED_FILES: Set[str] = set(IGNORED_FILES)

async def discover_files(repo_path: str) -> AsyncGenerator[Tuple[str, str, str], None]:
    """
    Discovers supported files in the repository asynchronously.

    Walks the directory tree, respecting ignore patterns defined in config.py,
    and identifies files based on supported extensions or exact filenames.

    Args:
        repo_path: The absolute path to the root of the repository to scan.

    Yields:
        Tuples containing:
            - absolute_path (str): The full path to the discovered file.
            - relative_path (str): The path relative to the repo_path.
            - file_type (str): The type key assigned in config.SUPPORTED_EXTENSIONS
                               (e.g., 'python', 'markdown', 'dockerfile').
    """
    abs_repo_path = os.path.abspath(repo_path)
    logger.info(f"Starting file discovery in: {abs_repo_path}")

    if not os.path.isdir(abs_repo_path):
        logger.error(f"Provided discovery path is not a valid directory: {abs_repo_path}")
        return

    processed_files_count = 0
    supported_files_count = 0

    for root, dirs, files in os.walk(abs_repo_path, topdown=True, onerror=lambda err: logger.error(f"Error walking directory: {err}")):
        # Filter ignored directories efficiently
        dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS]

        for file in files:
            processed_files_count += 1
            if file in _IGNORED_FILES:
                logger.debug(f"Ignoring file based on IGNORED_FILES: {file}")
                continue

            file_path = os.path.join(root, file)

            # Check if the file path itself contains an ignored directory component
            # This handles cases where os.walk might enter a dir before it's pruned
            # if any(ignored_dir in file_path.split(os.sep) for ignored_dir in _IGNORED_DIRS):
            #     logger.debug(f"Ignoring file within an ignored directory path: {file_path}")
            #     continue

            # Determine file type based on exact name first, then extension
            file_type = SUPPORTED_EXTENSIONS.get(file) # Check exact filename match
            if not file_type:
                _, ext = os.path.splitext(file)
                if not ext and file not in SUPPORTED_EXTENSIONS: # Skip files without extensions unless explicitly mapped by name
                    # logger.debug(f"Skipping file without extension or explicit mapping: {file}")
                    continue
                file_type = SUPPORTED_EXTENSIONS.get(ext.lower()) # Check extension match

            if file_type:
                try:
                    relative_path = os.path.relpath(file_path, abs_repo_path)
                    logger.debug(f"Discovered supported file: {relative_path} (Type: {file_type})")
                    supported_files_count += 1
                    yield file_path, relative_path, file_type
                    # Introduce a small sleep to allow other async tasks to run,
                    # preventing potential blocking on very large directories.
                    if supported_files_count % 500 == 0: # Adjust frequency as needed
                         await asyncio.sleep(0.001)

                except ValueError:
                     logger.error(f"Could not determine relative path for {file_path} against {abs_repo_path}. Skipping.")
                except Exception as e:
                     logger.error(f"Unexpected error processing file path {file_path}: {e}", exc_info=True)
            # else: # Log only if debugging needed, can be very verbose
            #     logger.debug(f"Skipping unsupported file type: {file_path}")

    logger.info(f"File discovery complete. Processed {processed_files_count} total files/links. Found {supported_files_count} supported files.")

# Example usage (for testing standalone)
async def _test_discovery():
    test_path = "." # Discover in current directory
    print(f"Testing discovery in: {os.path.abspath(test_path)}")
    async for abs_p, rel_p, f_type in discover_files(test_path):
        print(f"  - Found: {rel_p} (Type: {f_type})")

if __name__ == "__main__":
    # Run with: python -m src.parser.discovery
    import asyncio
    asyncio.run(_test_discovery())
