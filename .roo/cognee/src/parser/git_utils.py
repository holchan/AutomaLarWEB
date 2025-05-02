# src/parser/git_utils.py
import os
import git
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Tuple
from .utils import logger

TEMP_CLONE_BASE_DIR = Path(__file__).parent.parent.parent / "data" / "tmp_repos"

def get_repo_name_from_url(url: str) -> str:
    """Extracts a likely repository name from a Git URL."""
    try:
        name = Path(url).name
        if name.endswith(".git"):
            name = name[:-4]
        return name.replace(" ", "_")
    except Exception:
        return url.split('/')[-1].replace(".git", "").replace(" ", "_")

def clone_repo_to_temp(repo_url: str) -> Optional[Tuple[str, str]]:
    """
    Clones a remote Git repository to a temporary local directory.

    Args:
        repo_url: The URL of the Git repository to clone.

    Returns:
        A tuple containing (absolute_path_to_cloned_repo, repo_id)
        if successful, otherwise None. The repo_id is derived from the URL.
    """
    try:
        TEMP_CLONE_BASE_DIR.mkdir(parents=True, exist_ok=True)

        repo_name_part = get_repo_name_from_url(repo_url).replace("/", "_")
        temp_dir_path = TEMP_CLONE_BASE_DIR / repo_name_part

        if temp_dir_path.exists():
            logger.warning(f"Temporary directory {temp_dir_path} already exists. Removing for fresh clone.")
            shutil.rmtree(temp_dir_path)

        temp_dir_path.mkdir(parents=True)
        clone_path = str(temp_dir_path)

        logger.info(f"Cloning Git repository '{repo_url}' into temporary directory: {clone_path}")
        git.Repo.clone_from(repo_url, clone_path, depth=1)
        logger.info(f"Successfully cloned '{repo_url}'.")

        repo_id_base = repo_url.split('://')[-1]
        repo_id_base = repo_id_base.split('@')[-1]
        repo_id_base = repo_id_base.replace(':', '/')
        if repo_id_base.endswith('.git'):
            repo_id_base = repo_id_base[:-4]
        repo_id = repo_id_base

        return clone_path, repo_id

    except git.GitCommandError as e:
        logger.error(f"Git command failed during clone of '{repo_url}': {e}", exc_info=True)
        if 'temp_dir_path' in locals() and temp_dir_path.exists():
            shutil.rmtree(temp_dir_path, ignore_errors=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error cloning repository '{repo_url}': {e}", exc_info=True)
        if 'temp_dir_path' in locals() and temp_dir_path.exists():
            shutil.rmtree(temp_dir_path, ignore_errors=True)
        return None

def cleanup_temp_repo(temp_repo_path: str):
    """Removes the temporary repository directory."""
    if temp_repo_path and Path(temp_repo_path).is_dir() and TEMP_CLONE_BASE_DIR in Path(temp_repo_path).parents:
        logger.info(f"Cleaning up temporary repository directory: {temp_repo_path}")
        shutil.rmtree(temp_repo_path, ignore_errors=True)
    else:
        logger.warning(f"Skipping cleanup for path '{temp_repo_path}' - not a valid temp repo directory.")
