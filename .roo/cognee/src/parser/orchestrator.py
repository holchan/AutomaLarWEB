import asyncio
import time
from pathlib import Path
from typing import AsyncGenerator, Dict, Type, List, Union, Tuple
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
    "python": PythonParser, "javascript": JavascriptParser, "typescript": TypescriptParser,
    "c": CParser, "cpp": CppParser, "rust": RustParser, "markdown": MarkdownParser,
    "css": CssParser, "dockerfile": DockerfileParser,
}

OrchestratorOutputItem = Union[
    Repository,
    Tuple[SourceFile, Dict[str, str]],
    TextChunk, CodeEntity, Relationship
]

async def _run_parser_for_file_task(
    parser_instance: BaseParser, abs_file_path: str, file_id: str
) -> List[Union[TextChunk, CodeEntity, Relationship]]:
    collected_items = []
    try:
        async for item in parser_instance.parse(abs_file_path, file_id):
            collected_items.append(item)
    except Exception as e:
        logger.error(f"Error in parser task for {abs_file_path}: {e}", exc_info=True)
    return collected_items

async def process_repository(
    repo_path: str, repo_id: str, concurrency_limit: int = 25
) -> AsyncGenerator[OrchestratorOutputItem, None]:
    abs_repo_path = Path(repo_path).resolve()
    start_time_repo = time.time()
    logger.info(f"Orchestrator: Starting for {repo_id} at {abs_repo_path}")

    yield Repository(id=repo_id, path=str(abs_repo_path))

    parser_instances_cache: Dict[str, BaseParser] = {}
    file_processing_tasks_args: List[Tuple[BaseParser, str, str]] = []
    source_files_to_yield_with_context: List[Tuple[SourceFile, Dict[str,str]]] = []

    async for abs_f_path, rel_f_path, lang_key in discover_files(str(abs_repo_path)):
        sf_slug_id = f"{repo_id}:{rel_f_path}"
        source_file_node_from_parser = SourceFile(
            id=sf_slug_id, file_path=abs_f_path
        )
        source_files_to_yield_with_context.append(
            (source_file_node_from_parser, {"relative_path": rel_f_path, "language_key": lang_key})
        )
        ParserClass = PARSER_MAP.get(lang_key)
        if ParserClass:
            if lang_key not in parser_instances_cache:
                try:
                    parser_instances_cache[lang_key] = ParserClass()
                except Exception as e:
                    logger.error(f"Failed to init parser for {lang_key}: {e}", exc_info=True)
                    continue
            parser_instance = parser_instances_cache[lang_key]
            file_processing_tasks_args.append((parser_instance, abs_f_path, sf_slug_id))
        else:
            logger.warning(f"No parser for lang '{lang_key}' of file {abs_f_path}")

    for sf_node, sf_context in source_files_to_yield_with_context:
        yield (sf_node, sf_context)

    total_parsed_items_yielded = 0
    for i in range(0, len(file_processing_tasks_args), concurrency_limit):
        batch_args = file_processing_tasks_args[i:i + concurrency_limit]
        if not batch_args: continue
        tasks = [
            asyncio.create_task(
                _run_parser_for_file_task(p_inst, abs_p, f_id)
            ) for p_inst, abs_p, f_id in batch_args
        ]
        results_for_batch = await asyncio.gather(*tasks, return_exceptions=True)
        for result_list_or_exc in results_for_batch:
            if isinstance(result_list_or_exc, Exception):
                logger.error(f"Parser task failed: {result_list_or_exc}", exc_info=True)
            elif isinstance(result_list_or_exc, list):
                for item in result_list_or_exc:
                    yield item
                    total_parsed_items_yielded += 1
    duration_repo = time.time() - start_time_repo
    logger.info(f"Orchestrator: Finished {repo_id}. Yielded {total_parsed_items_yielded} parser items. Time: {duration_repo:.2f}s")
