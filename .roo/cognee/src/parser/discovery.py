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
    if path_obj.is_dir():
        dir_name_to_check = path_obj.name
        for ignored_dir_pattern in _IGNORED_DIRS_SET:
            if fnmatch.fnmatch(dir_name_to_check, ignored_dir_pattern): return True
        if path_obj != abs_repo_path:
            try:
                relative_path_str = str(path_obj.relative_to(abs_repo_path)).replace(os.sep, '/')
                for ignored_path_prefix in _IGNORED_DIRS_SET:
                    normalized_ignored_prefix = ignored_path_prefix.replace(os.sep, '/')
                    if '/' in normalized_ignored_prefix and (relative_path_str == normalized_ignored_prefix or relative_path_str.startswith(normalized_ignored_prefix + '/')):
                        return True
            except ValueError: pass
    if path_obj.is_file():
        filename = path_obj.name
        if filename in _EXACT_IGNORED_FILES_SET: return True
        for pattern in _PATTERN_IGNORED_FILES_SET:
            if fnmatch.fnmatch(filename, pattern): return True
    return False

async def discover_files(repo_path: str) -> AsyncGenerator[Tuple[str, str, str], None]:
    try:
        abs_repo_path = Path(repo_path).resolve(strict=True)
        if not abs_repo_path.is_dir():
            logger.error(f"Repo path is not a directory: {repo_path}"); return
    except FileNotFoundError: logger.error(f"Repo path does not exist: {repo_path}"); return
    except Exception as e: logger.error(f"Error resolving repo_path '{repo_path}'", exc_info=e); return

    for root_str, dirs, files in os.walk(abs_repo_path, topdown=True):
        current_root_path = Path(root_str)
        dirs_to_keep = [d_name for d_name in dirs if not await _is_path_ignored(current_root_path / d_name, abs_repo_path)]
        dirs[:] = dirs_to_keep
        for filename in files:
            file_path_obj = current_root_path / filename
            if await _is_path_ignored(file_path_obj, abs_repo_path): continue
            file_type_key: Optional[str] = None
            filename_lower = filename.lower()
            if filename_lower in SUPPORTED_EXTENSIONS and '.' not in filename_lower and not filename_lower.startswith('.'):
                file_type_key = SUPPORTED_EXTENSIONS[filename_lower]
            if not file_type_key:
                file_ext_lower = file_path_obj.suffix.lower()
                if file_ext_lower and file_ext_lower in SUPPORTED_EXTENSIONS:
                    file_type_key = SUPPORTED_EXTENSIONS[file_ext_lower]
            if file_type_key:
                absolute_path_str = str(file_path_obj)
                try: relative_path_str = str(file_path_obj.relative_to(abs_repo_path))
                except ValueError: logger.error(f"Could not get relative path for {absolute_path_str} vs {abs_repo_path}"); continue
                yield absolute_path_str, relative_path_str, file_type_key
                await asyncio.sleep(0)
