import asyncio
import os
import time
from pathlib import Path
from typing import AsyncGenerator, Dict, Type, List, Union

from pydantic import BaseModel

from .discovery import discover_files
from .parsers.base_parser import BaseParser
from .utils import logger

from .parsers.c_parser import CParser
from .parsers.cpp_parser import CppParser
from .parsers.python_parser import PythonParser
from .parsers.javascript_parser import JavascriptParser
from .parsers.typescript_parser import TypescriptParser
from .parsers.rust_parser import RustParser
from .parsers.markdown_parser import MarkdownParser
from .parsers.css_parser import CssParser
from .parsers.dockerfile_parser import DockerfileParser
# from .parsers.java_parser import JavaParser
# from .parsers.csharp_parser import CSharpParser
# from .parsers.go_parser import GoParser
# from .parsers.php_parser import PhpParser
# from .parsers.html_parser import HtmlParser
# from .parsers.xml_parser import XmlParser
# from .parsers.json_parser import JsonParser
# from .parsers.yaml_parser import YamlParser
# from .parsers.txt_parser import TxtParser
# from .parsers.sql_parser import SQLParser

from .entities import Repository, SourceFile, TextChunk, CodeEntity, Relationship

PARSER_MAP: Dict[str, Type[BaseParser]] = {
    "python": PythonParser,
    "javascript": JavascriptParser,
    "typescript": TypescriptParser,
    "c": CParser,
    "cpp": CppParser,
    "rust": RustParser,
    "markdown": MarkdownParser,
    "css": CssParser,
    "dockerfile": DockerfileParser,
    # "java": JavaParser,
    # "csharp": CSharpParser,
    # "go": GoParser,
    # "php": PhpParser,
    # "shell": ShellParser,
    # "html": HtmlParser,
    # "xml": XmlParser,
    # "json": JsonParser,
    # "yaml": YamlParser,
    # "txt": TxtParser,
    # "sql": SQLParser,
}

OrchestratorOutput = Union[Repository, SourceFile, TextChunk, CodeEntity, Relationship]


async def _run_parser_for_file(
    parser_instance: BaseParser,
    abs_file_path: str,
    file_id: str,
    language_key: str
) -> List[BaseModel]:
    """
    Helper coroutine to run a single parser and collect all its results.
    Handles exceptions during parsing and logs them.
    """
    logger.debug(f"Starting parsing for {abs_file_path} with {type(parser_instance).__name__}")
    parsed_items: List[BaseModel] = []
    try:
        async for item in parser_instance.parse(abs_file_path, file_id, language_key):
            parsed_items.append(item)
        logger.debug(f"Finished parsing {abs_file_path}. Yielded {len(parsed_items)} items.")
    except Exception as e:
        logger.error(f"Error during parsing file {abs_file_path} with {type(parser_instance).__name__}", exc_info=e)
    return parsed_items


async def process_repository(
    repo_path: str,
    repo_id: str,
    concurrency_limit: int = 10
) -> AsyncGenerator[OrchestratorOutput, None]:
    """
    Orchestrates the process of discovering and parsing files within a repository.
    Yields Pydantic BaseModel objects from src.parser.entities:
    Repository, then SourceFile for each file, then TextChunk, CodeEntity, Relationship from parsers.
    """
    abs_repo_path = Path(repo_path).resolve()
    start_time_repo = time.time()
    logger.info(f"Starting processing for repository: {repo_id} at {abs_repo_path}")

    repository_node = Repository(id=repo_id, path=str(abs_repo_path))
    yield repository_node

    parser_instances_cache: Dict[str, BaseParser] = {}

    file_processing_args_list: List[Tuple[BaseParser, str, str, str]] = []

    files_discovered_count = 0
    async for abs_file_path, rel_file_path, language_key in discover_files(str(abs_repo_path)):
        files_discovered_count += 1
        file_id = f"{repo_id}:{rel_file_path}"

        source_file_node = SourceFile(
            id=file_id,
            file_path=abs_file_path,
            relative_path=rel_file_path,
            language_key=language_key,
            timestamp=time.time()
        )
        yield source_file_node

        ParserClass = PARSER_MAP.get(language_key)
        if ParserClass:
            if language_key not in parser_instances_cache:
                try:
                    parser_instances_cache[language_key] = ParserClass()
                    logger.debug(f"Initialized parser for language key: {language_key}")
                except Exception as e:
                    logger.error(f"Failed to initialize parser for {language_key}", exc_info=e)
                    continue

            parser_instance = parser_instances_cache[language_key]
            file_processing_args_list.append(
                (parser_instance, abs_file_path, file_id, language_key)
            )
        else:
            logger.warning(f"No parser registered for language key '{language_key}' for file {abs_file_path}. Skipping parsing for this file.")

    logger.info(f"Discovered {files_discovered_count} files. Prepared {len(file_processing_args_list)} files for parsing.")

    total_parsed_items_yielded = 0
    for i in range(0, len(file_processing_args_list), concurrency_limit):
        batch_args = file_processing_args_list[i:i + concurrency_limit]
        if not batch_args:
            continue

        logger.info(f"Processing batch {i//concurrency_limit + 1} of {len(batch_args)} files for parsing...")

        tasks = [
            asyncio.create_task(
                _run_parser_for_file(p_instance, p_abs_file_path, p_file_id, p_lang_key)
            ) for p_instance, p_abs_file_path, p_file_id, p_lang_key in batch_args
        ]

        results_for_batch_of_files: List[Union[List[BaseModel], Exception]] = await asyncio.gather(*tasks, return_exceptions=True)

        batch_items_yielded = 0
        for result_list_or_exc in results_for_batch_of_files:
            if isinstance(result_list_or_exc, Exception):
                logger.error(f"A file parsing task in the batch resulted in an exception: {result_list_or_exc}")
            elif isinstance(result_list_or_exc, list):
                for item in result_list_or_exc:
                    yield item
                    batch_items_yielded += 1
            else:
                logger.warning(f"Unexpected result type from parser task: {type(result_list_or_exc)}")

        total_parsed_items_yielded += batch_items_yielded
        logger.info(f"Batch {i//concurrency_limit + 1} processed. Yielded {batch_items_yielded} parser items.")
        await asyncio.sleep(0.01)

    duration_repo = time.time() - start_time_repo
    logger.info(
        f"Finished processing repository {repo_id}. "
        f"Total Pydantic items yielded from parsers: {total_parsed_items_yielded}. "
        f"Total time: {duration_repo:.2f}s"
    )
