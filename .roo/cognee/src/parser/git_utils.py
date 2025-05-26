import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple
import os
from datetime import datetime

from .utils import logger

try:
    APP_DATA_DIR = Path(os.getenv("COGNEE_APP_DATA_DIR", Path.home() / ".cognee_mcp" / "data"))
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_CLONE_BASE_DIR = APP_DATA_DIR / "tmp_repos"
    TEMP_CLONE_BASE_DIR.mkdir(parents=True, exist_ok=True)
except Exception as e:
    fallback_dir = Path(__file__).resolve().parent.parent.parent / "data" / "tmp_repos"
    logger.warning(
        f"Could not create/access temp repo dir: {e}. Using fallback: {fallback_dir}"
    )
    TEMP_CLONE_BASE_DIR = fallback_dir
    TEMP_CLONE_BASE_DIR.mkdir(parents=True, exist_ok=True)


def get_repo_name_from_url(url: str) -> str:
    name_part = url.split('/')[-1]
    if name_part.endswith(".git"):
        name_part = name_part[:-4]
    return name_part

def sanitize_for_path(name: str) -> str:
    return "".join(c if c.isalnum() or c in ['-', '_', '.'] else '_' for c in name)

def clone_repo_to_temp(repo_url: str) -> Optional[Tuple[str, str]]:
    temp_dir_path_obj = None
    try:
        repo_name_from_url = get_repo_name_from_url(repo_url)
        sanitized_repo_name = sanitize_for_path(repo_name_from_url)
        timestamp_suffix = datetime.now().strftime('%Y%m%d%H%M%S%f')
        unique_repo_dir_name = f"{sanitized_repo_name}_{timestamp_suffix}"
        temp_dir_path_obj = TEMP_CLONE_BASE_DIR / unique_repo_dir_name
        clone_path_str = str(temp_dir_path_obj.resolve())
        temp_dir_path_obj.mkdir(parents=True, exist_ok=True)
        process = subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, clone_path_str],
            capture_output=True, text=True, check=False, encoding='utf-8', errors='ignore'
        )
        if process.returncode != 0:
            error_message = process.stderr.strip() if process.stderr else process.stdout.strip()
            logger.error(f"Failed to clone {repo_url}. Git output: {error_message}")
            if temp_dir_path_obj.exists():
                try: shutil.rmtree(clone_path_str)
                except Exception as e_clean: logger.error(f"Failed to cleanup {clone_path_str}", exc_info=e_clean)
            return None
        repo_id_base = repo_url.split('://')[-1].split('@')[-1].replace(':', '/')
        if repo_id_base.endswith(".git"): repo_id_base = repo_id_base[:-4]
        repo_id = repo_id_base.strip('/')
        return clone_path_str, repo_id
    except Exception as e:
        logger.error(f"Error cloning {repo_url}.", exc_info=e)
        if temp_dir_path_obj and temp_dir_path_obj.exists():
            try: shutil.rmtree(temp_dir_path_obj)
            except Exception as e_clean: logger.error(f"Error cleaning temp dir {temp_dir_path_obj}.", exc_info=e_clean)
        return None

def cleanup_temp_repo(temp_repo_path_str: Optional[str]):
    if not temp_repo_path_str: return
    try:
        temp_repo_path = Path(temp_repo_path_str).resolve()
        base_dir_resolved = TEMP_CLONE_BASE_DIR.resolve()
        if base_dir_resolved == temp_repo_path or base_dir_resolved in temp_repo_path.parents:
            if temp_repo_path.exists() and temp_repo_path.is_dir():
                shutil.rmtree(temp_repo_path_str)
            elif temp_repo_path.exists():
                 logger.warning(f"Path to clean is not a directory: {temp_repo_path_str}")
        else:
            logger.warning(f"Skipping cleanup: {temp_repo_path_str} not in {base_dir_resolved}")
    except Exception as e:
        logger.error(f"Error cleaning temp repo {temp_repo_path_str}.", exc_info=e)
