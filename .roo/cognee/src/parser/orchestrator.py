import asyncio
import os
import time
from typing import AsyncGenerator, Dict, Type, Any
from pydantic import BaseModel
from pathlib import Path

from .entities import Repository, SourceFile, Relationship
from .discovery import discover_files
from .utils import logger
from .config import SUPPORTED_EXTENSIONS

from .parsers.base_parser import BaseParser
from .parsers.markdown_parser import MarkdownParser
from .parsers.python_parser import PythonParser
from .parsers.javascript_parser import JavascriptParser
from .parsers.typescript_parser import TypescriptParser
from .parsers.c_parser import CParser
from .parsers.cpp_parser import CppParser
from .parsers.rust_parser import RustParser
from .parsers.dockerfile_parser import DockerfileParser
from .parsers.css_parser import CssParser

PARSER_MAP: Dict[str, Type[BaseParser]] = {
    "markdown": MarkdownParser,
    "python": PythonParser,
    "javascript": JavascriptParser,
    "typescript": TypescriptParser,
    "c": CParser,
    "cpp": CppParser,
    "rust": RustParser,
    "dockerfile": DockerfileParser,
    "css": CssParser,
}

async def _parse_and_yield_file_data(
    parser_instance: BaseParser,
    file_path: str,
    file_id: str
) -> AsyncGenerator[BaseModel, None]:
    """
    Helper coroutine to run a parser and yield its results.

    Handles exceptions during parsing and logs them.
    """
    try:
        logger.debug(f"Starting parsing for file: {os.path.basename(file_path)} using {parser_instance.parser_type}")
        count = 0
        async for dp in parser_instance.parse(file_path, file_id):
            yield dp
            count += 1
        logger.debug(f"Parser {parser_instance.parser_type} finished for {os.path.basename(file_path)}, yielded {count} items.")
    except Exception as e:
        logger.error(f"Error executing parser {parser_instance.parser_type} on file {file_path}: {e}", exc_info=True)


async def process_repository(repo_path: str, repo_id: str, concurrency_limit: int = 50) -> AsyncGenerator[BaseModel, None]:
    """
    Orchestrates the process of discovering and parsing files within a repository.

    Yields Repository, SourceFile, TextChunk, CodeEntity, and Relationship objects
    according to the defined entities.

    Args:
        repo_path: The absolute path to the local repository directory.
        repo_id: The unique identifier for this repository instance, repo name or project name (e.g., "microsoft/graphrag" or "local/AutomaLarWEB").
        concurrency_limit: Max number of files to parse concurrently.

    Yields:
        Pydantic BaseModel objects: Repository, SourceFile, Relationship,
        TextChunk, CodeEntity.
    """
    abs_repo_path = os.path.abspath(repo_path)
    start_time = time.time()
    logger.info(f"Starting repository processing for: {repo_id} ({abs_repo_path})")

    if not os.path.isdir(abs_repo_path):
        logger.error(f"Repository path not found or not a directory: {abs_repo_path}")
        return

    try:
        repo_node = Repository(id=repo_id, path=abs_repo_path)
        yield repo_node
    except Exception as e:
        logger.error(f"Failed to create Repository node for {repo_id}: {e}", exc_info=True)
        return

    parser_instances: Dict[str, BaseParser] = {}
    file_processing_coroutines = []
    file_nodes_to_yield = []

    async for file_path, relative_path, file_type in discover_files(abs_repo_path):
        file_id = f"{repo_id}:{relative_path}"

        try:
            file_node = SourceFile(
                id=file_id,
                file_path=file_path,
                file_type=file_type
            )
            file_rel = Relationship(source_id=repo_id, target_id=file_id, type="CONTAINS_FILE")
            file_nodes_to_yield.append((file_node, file_rel))
            logger.debug(f"Prepared SourceFile node for: {relative_path} (ID: {file_id})")
        except Exception as e:
            logger.error(f"Failed to create SourceFile node/relationship for {relative_path}: {e}", exc_info=True)
            continue

        ParserClass = PARSER_MAP.get(file_type)

        if ParserClass:
            if file_type not in parser_instances:
                try:
                    parser_instances[file_type] = ParserClass()
                    logger.debug(f"Instantiated parser for type: '{file_type}' ({ParserClass.__name__})")
                except Exception as e:
                    logger.error(f"Failed to instantiate parser {ParserClass.__name__} for type '{file_type}': {e}", exc_info=True)
                    continue

            parser_instance = parser_instances[file_type]
            coro = _parse_and_yield_file_data(parser_instance, file_path, file_id)
            file_processing_coroutines.append(coro)
        else:
            logger.warning(f"No parser mapped for supported file type '{file_type}'. Skipping detailed parsing for: {relative_path}")

    logger.info(f"Discovery complete. Found {len(file_nodes_to_yield)} supported files to process.")
    total_yielded = 1
    for file_node, file_rel in file_nodes_to_yield:
        yield file_node
        yield file_rel
        total_yielded += 2

    processed_files_count = 0
    tasks = []
    results_buffer = []

    async def run_and_buffer(coro):
        async for item in coro:
            results_buffer.append(item)

    for i in range(0, len(file_processing_coroutines), concurrency_limit):
        batch_coros = file_processing_coroutines[i:i + concurrency_limit]
        logger.info(f"Processing batch {i//concurrency_limit + 1} ({len(batch_coros)} files)...")

        tasks = [asyncio.create_task(run_and_buffer(coro)) for coro in batch_coros]

        if tasks:
            done, pending = await asyncio.wait(tasks)
            processed_files_count += len(done)

            for task in done:
                if task.exception():
                    pass

            batch_yield_count = 0
            for item in results_buffer:
                yield item
                batch_yield_count += 1
            total_yielded += batch_yield_count
            results_buffer.clear()

            logger.info(f"Finished batch {i//concurrency_limit + 1}. Yielded {batch_yield_count} parser items. Total files processed so far: {processed_files_count}")

    end_time = time.time()
    duration = end_time - start_time
    logger.info(f"Finished processing repository {repo_id}. Total items yielded: {total_yielded} in {duration:.2f} seconds.")


async def _orchestrator_test_main():
    # Replace with the actual path to the repository you want to parse
    # repo_to_parse = "/path/to/your/repository"
    script_dir = Path(__file__).parent.parent.parent # Should be .roo/cognee/
    repo_to_parse = str(script_dir / "tests" / "parser" / "test_data") # Use test data dir
    test_repo_id = "local/test_repo"
    print(f"Starting parsing process via orchestrator for repository: {os.path.abspath(repo_to_parse)} with ID: {test_repo_id}")

    count = 0
    start_time = time.time()
    async for data_point in process_repository(repo_to_parse, test_repo_id, concurrency_limit=10):
        count += 1
        dp_type = getattr(data_point, 'type', 'Unknown')
        dp_id = getattr(data_point, 'id', 'N/A')
        print(f"  Yielded {count}: Type={dp_type}, ID={dp_id}")

        if count % 100 == 0:
            elapsed = time.time() - start_time
            print(f" ... yielded {count} items ({elapsed:.2f}s elapsed) ...")

    end_time = time.time()
    print(f"\nOrchestrator finished. Yielded {count} items in {end_time - start_time:.2f} seconds.")

if __name__ == "__main__":
    # To run this parser standalone for testing: python -m src.parser.orchestrator
    # Run from .roo/cognee/
    asyncio.run(_orchestrator_test_main())
