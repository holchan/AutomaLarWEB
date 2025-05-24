import os
from pathlib import Path
from typing import AsyncGenerator, Tuple, Set, Optional
import asyncio
import fnmatch

from .config import IGNORED_DIRS, IGNORED_FILES, SUPPORTED_EXTENSIONS
from .utils import logger

_IGNORED_DIRS_SET: Set[str] = set(IGNORED_DIRS)

_EXACT_IGNORED_FILES_SET: Set[str] = {f for f in IGNORED_FILES if "*" not in f and "?" not in f and "[" not in f}
_PATTERN_IGNORED_FILES_SET: Set[str] = set(IGNORED_FILES) - _EXACT_IGNORED_FILES_SET


async def _is_path_ignored(path_obj: Path, abs_repo_path: Path) -> bool:
    """
    Checks if a given path (file or directory) should be ignored based on
    IGNORED_DIRS and IGNORED_FILES configurations.
    `path_obj` is the absolute path of the item to check.
    `abs_repo_path` is the absolute path of the repository root.
    """

    if path_obj.is_dir():

        dir_name_to_check = path_obj.name
        for ignored_dir_pattern in _IGNORED_DIRS_SET:
            if fnmatch.fnmatch(dir_name_to_check, ignored_dir_pattern):
                logger.debug(f"Ignoring directory '{path_obj}' because its name '{dir_name_to_check}' matches ignored pattern '{ignored_dir_pattern}'.")
                return True

        if path_obj != abs_repo_path:
            try:
                relative_path_str = str(path_obj.relative_to(abs_repo_path)).replace(os.sep, '/')
                for ignored_path_prefix in _IGNORED_DIRS_SET:
                    normalized_ignored_prefix = ignored_path_prefix.replace(os.sep, '/')
                    if '/' in normalized_ignored_prefix:
                        if relative_path_str == normalized_ignored_prefix or \
                           relative_path_str.startswith(normalized_ignored_prefix + '/'):
                            logger.debug(f"Ignoring path '{path_obj}' because its relative path '{relative_path_str}' starts with ignored path prefix '{ignored_path_prefix}'.")
                            return True
            except ValueError:
                logger.warning(f"Could not get relative path for {path_obj} against {abs_repo_path} in _is_path_ignored.")
                pass

    if path_obj.is_file():
        filename = path_obj.name
        if filename in _EXACT_IGNORED_FILES_SET:
            logger.debug(f"Ignoring file (exact name match): {filename} in {path_obj.parent}")
            return True
        for pattern in _PATTERN_IGNORED_FILES_SET:
            if fnmatch.fnmatch(filename, pattern):
                logger.debug(f"Ignoring file (pattern match '{pattern}'): {filename} in {path_obj.parent}")
                return True

    return False


async def discover_files(repo_path: str) -> AsyncGenerator[Tuple[str, str, str], None]:
    """
    Asynchronously discovers supported files within a given repository path.

    Walks the directory tree, respects IGNORED patterns (from config.py),
    identifies supported files based on SUPPORTED_EXTENSIONS (from config.py),
    and yields file details.

    Args:
        repo_path: The absolute path to the root of the repository directory to scan.

    Yields:
        A tuple for each discovered supported file:
        - absolute_path (str): The full, absolute path to the discovered file.
        - relative_path (str): The path to the file relative to the `repo_path`.
        - file_type_key (str): The key from `config.SUPPORTED_EXTENSIONS` corresponding
                               to the file's type (e.g., 'python', 'markdown').
    """
    try:
        abs_repo_path = Path(repo_path).resolve(strict=True)
        if not abs_repo_path.is_dir():
            logger.error(f"Provided repo_path is not a directory: {repo_path}")
            return
    except FileNotFoundError:
        logger.error(f"Provided repo_path does not exist: {repo_path}")
        return
    except Exception as e:
        logger.error(f"Error resolving repo_path '{repo_path}'", exc_info=e)
        return

    logger.info(f"Starting file discovery in: {abs_repo_path}")
    processed_elements_count = 0
    supported_files_yielded_count = 0

    for root_str, dirs, files in os.walk(abs_repo_path, topdown=True):
        current_root_path = Path(root_str)
        processed_elements_count += 1

        dirs_to_keep = []
        for d_name in dirs:
            processed_elements_count +=1
            dir_path_obj = current_root_path / d_name
            if await _is_path_ignored(dir_path_obj, abs_repo_path):
                pass
            else:
                dirs_to_keep.append(d_name)
        dirs[:] = dirs_to_keep

        for filename in files:
            processed_elements_count += 1
            file_path_obj = current_root_path / filename

            if await _is_path_ignored(file_path_obj, abs_repo_path):
                continue

            file_type_key: Optional[str] = None
            filename_lower = filename.lower()

            if filename_lower in SUPPORTED_EXTENSIONS:
                if '.' not in filename_lower:
                    file_type_key = SUPPORTED_EXTENSIONS[filename_lower]
                    logger.debug(f"Matched exact filename (case-insensitive key): '{filename}' -> type key '{file_type_key}'")
                elif not filename_lower.startswith('.'):
                     pass

            if not file_type_key:
                file_ext_lower = file_path_obj.suffix.lower()
                if file_ext_lower and file_ext_lower in SUPPORTED_EXTENSIONS:
                    file_type_key = SUPPORTED_EXTENSIONS[file_ext_lower]
                    logger.debug(f"Matched file extension: '{filename}' (ext: '{file_ext_lower}') -> type key '{file_type_key}'")

            if file_type_key:
                absolute_path_str = str(file_path_obj)
                try:
                    relative_path_str = str(file_path_obj.relative_to(abs_repo_path))
                except ValueError:
                    logger.error(f"Could not determine relative path for {absolute_path_str} against {abs_repo_path}")
                    continue

                yield absolute_path_str, relative_path_str, file_type_key
                supported_files_yielded_count +=1
                await asyncio.sleep(0)
            else:
                logger.debug(f"Ignoring file (unsupported type/extension): {file_path_obj}")

    logger.info(
        f"File discovery completed for {repo_path}. Inspected approx {processed_elements_count} fs elements. "
        f"Yielded: {supported_files_yielded_count} supported files."
    )
