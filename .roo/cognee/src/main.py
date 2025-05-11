# src/main.py
import asyncio
import os
import sys
from pathlib import Path
from typing import AsyncGenerator, Optional
from pydantic import BaseModel
import argparse
import shutil

from parser.orchestrator import process_repository
from parser.git_utils import clone_repo_to_temp, cleanup_temp_repo
from parser.utils import logger

def setup_arg_parser():
    parser = argparse.ArgumentParser(
        description="Standalone Code Parser: Processes local or remote Git repositories."
    )
    parser.add_argument(
        "target",
        help="Path to the local repository directory OR URL of the Git repository."
    )
    parser.add_argument(
        "--repo-id",
        help="Optional specific ID for the repository (e.g., 'my_project'). Defaults to derived name.",
        default=None
    )
    parser.add_argument(
        "--project-name",
        help="Project name used for 'local/' prefix if target is local path and --repo-id is not set.",
        default=os.environ.get("WEB_COGNEE_PROJECT", "default_project")
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=50,
        help="Maximum number of files to parse concurrently."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable DEBUG logging."
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Do not delete the temporary directory after cloning a remote repository."
    )
    return parser

async def run_parser(
    target: str,
    repo_id_override: Optional[str] = None,
    project_name_local: str = "default_project",
    concurrency: int = 50,
    keep_temp: bool = False
) -> AsyncGenerator[BaseModel, None]:
    """
    Main async function to handle repository processing and yield results.
    """
    repo_path: Optional[str] = None
    repo_id: Optional[str] = None
    is_temp_clone = False

    if target.startswith(("http://", "https://", "git@")):
        logger.info(f"Target '{target}' identified as a remote Git URL.")
        cloned_info = clone_repo_to_temp(target)
        if cloned_info:
            repo_path, derived_repo_id = cloned_info
            repo_id = repo_id_override or derived_repo_id
            is_temp_clone = True
            logger.info(f"Using derived Repo ID: '{repo_id}' (Override was: {repo_id_override})")
        else:
            logger.error(f"Failed to clone remote repository: {target}")
            return
    else:
        logger.info(f"Target '{target}' identified as a local path.")
        local_path = Path(target)
        if not local_path.is_dir():
            logger.error(f"Local path '{target}' is not a valid directory.")
            return
        repo_path = str(local_path.absolute())
        repo_id = repo_id_override or f"local/{project_name_local}"
        logger.info(f"Using Repo ID: '{repo_id}' (Override was: {repo_id_override})")

    if repo_path is None or repo_id is None:
        logger.error("Could not determine valid repository path and ID. Aborting.")
        return

    try:
        logger.info(f"Starting processing for Repo ID: {repo_id}, Path: {repo_path}")
        async for data_point in process_repository(repo_path, repo_id, concurrency_limit=concurrency):
            yield data_point
        logger.info(f"Finished yielding items for Repo ID: {repo_id}")

    except Exception as e:
        logger.error(f"An unexpected error occurred during repository processing for {repo_id}: {e}", exc_info=True)
    finally:
        if is_temp_clone and repo_path and not keep_temp:
            cleanup_temp_repo(repo_path)

async def main():
    parser = setup_arg_parser()
    args = parser.parse_args()

    if args.verbose:
        log_instance = logging.getLogger("standalone_parser")
        if not log_instance:
            log_instance = logging.getLogger()
        log_instance.setLevel(logging.DEBUG)
        logger.info("DEBUG logging enabled.")

    logger.info(f"Running parser with target: {args.target}, Repo ID Override: {args.repo_id}, Local Project: {args.project_name}")

    yield_count = 0
    try:
        async for item in run_parser(
            target=args.target,
            repo_id_override=args.repo_id,
            project_name_local=args.project_name,
            concurrency=args.concurrency,
            keep_temp=args.keep_temp
        ):
            yield_count += 1
            item_type = getattr(item, 'type', 'Unknown')
            item_id = getattr(item, 'id', 'N/A')
            print(f"Yielded {yield_count}: Type={item_type}, ID={item_id}")

    except Exception as e:
        logger.error(f"Script execution failed: {e}", exc_info=True)
        sys.exit(1)

    logger.info(f"Parser finished. Total items yielded: {yield_count}")

if __name__ == "__main__":
    # Example usage from command line:
    # python -m src.main https://github.com/someuser/somerepo.git --verbose
    # python -m src.main /path/to/local/repo --repo-id my_local_project
    # python -m src.main /path/to/local/repo # Uses WEB_COGNEE_PROJECT env var or default
    asyncio.run(main())
