import pytest
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Union, Tuple, AsyncGenerator
from unittest.mock import patch, AsyncMock, call, ANY

from pydantic import BaseModel

pytestmark = pytest.mark.asyncio

try:
    from src.parser.orchestrator import process_repository, PARSER_MAP, OrchestratorOutputItem
    from src.parser.entities import Repository, SourceFile, TextChunk, CodeEntity, Relationship
    from src.parser.parsers.base_parser import BaseParser
except ImportError as e:
    pytest.skip(f"Skipping orchestrator tests: Failed to import dependencies - {e}", allow_module_level=True)

MOCK_REPO_ID = "test-repo"
MOCK_FILE_CONTEXT_1 = {"relative_path": "src/main.py", "language_key": "python"}
MOCK_FILE_CONTEXT_2 = {"relative_path": "README.md", "language_key": "markdown"}
MOCK_FILE_CONTEXT_UNSUPPORTED = {"relative_path": "config.xml", "language_key": "xml"}

def _create_parser_entity(entity_type: str, slug_id_suffix: str, file_slug_id: str, **kwargs) -> BaseModel:
    base_id = f"{file_slug_id}:{slug_id_suffix}"
    if entity_type == "TextChunk":
        return TextChunk(id=base_id, type="TextChunk", start_line=kwargs.get("start_line", 1), end_line=kwargs.get("end_line", 1), chunk_content=kwargs.get("chunk_content", "content"))
    elif entity_type == "CodeEntity":
        return CodeEntity(id=base_id, type=kwargs.get("code_type", "FunctionDefinition"), snippet_content=kwargs.get("snippet_content", "snippet"))
    elif entity_type == "Relationship":
        return Relationship(source_id=kwargs.get("source_id", file_slug_id), target_id=kwargs.get("target_id", "target"), type=kwargs.get("rel_type", "LINKS_TO"))
    raise ValueError(f"Unknown mock entity type: {entity_type}")

MOCK_PYTHON_PARSER_OUTPUT = [
    _create_parser_entity("TextChunk", "chunk:0", f"{MOCK_REPO_ID}:{MOCK_FILE_CONTEXT_1['relative_path']}", chunk_content="python chunk 1"),
    _create_parser_entity("CodeEntity", "FunctionDefinition:my_func:0", f"{MOCK_REPO_ID}:{MOCK_FILE_CONTEXT_1['relative_path']}:chunk:0", code_type="FunctionDefinition", snippet_content="def my_func(): pass"),
    _create_parser_entity("Relationship", "rel:0", f"{MOCK_REPO_ID}:{MOCK_FILE_CONTEXT_1['relative_path']}", target_id="os", rel_type="IMPORTS")
]
MOCK_MARKDOWN_PARSER_OUTPUT = [
    _create_parser_entity("TextChunk", "chunk:0", f"{MOCK_REPO_ID}:{MOCK_FILE_CONTEXT_2['relative_path']}", chunk_content="markdown chunk 1"),
]


@pytest.fixture
def mock_tmp_path(tmp_path: Path) -> Path:
    repo_dir = tmp_path / MOCK_REPO_ID
    repo_dir.mkdir()
    (repo_dir / MOCK_FILE_CONTEXT_1["relative_path"]).parent.mkdir(parents=True, exist_ok=True)
    (repo_dir / MOCK_FILE_CONTEXT_1["relative_path"]).touch()
    (repo_dir / MOCK_FILE_CONTEXT_2["relative_path"]).parent.mkdir(parents=True, exist_ok=True)
    (repo_dir / MOCK_FILE_CONTEXT_2["relative_path"]).touch()
    (repo_dir / MOCK_FILE_CONTEXT_UNSUPPORTED["relative_path"]).parent.mkdir(parents=True, exist_ok=True)
    (repo_dir / MOCK_FILE_CONTEXT_UNSUPPORTED["relative_path"]).touch()
    return repo_dir

@patch("src.parser.orchestrator.discover_files")
async def test_process_repository_happy_path(mock_discover_files: AsyncMock, mock_tmp_path: Path):
    abs_repo_path = mock_tmp_path.resolve()
    mock_discovery_results = [
        (str(abs_repo_path / MOCK_FILE_CONTEXT_1["relative_path"]), MOCK_FILE_CONTEXT_1["relative_path"], MOCK_FILE_CONTEXT_1["language_key"]),
        (str(abs_repo_path / MOCK_FILE_CONTEXT_2["relative_path"]), MOCK_FILE_CONTEXT_2["relative_path"], MOCK_FILE_CONTEXT_2["language_key"]),
        (str(abs_repo_path / MOCK_FILE_CONTEXT_UNSUPPORTED["relative_path"]), MOCK_FILE_CONTEXT_UNSUPPORTED["relative_path"], MOCK_FILE_CONTEXT_UNSUPPORTED["language_key"]),
    ]
    mock_discover_files.return_value = asyncio.as_completed(mock_discovery_results).__aiter__()

    mock_python_parser_instance = AsyncMock(spec=BaseParser)
    mock_python_parser_instance.parse.return_value = asyncio.as_completed(MOCK_PYTHON_PARSER_OUTPUT).__aiter__()

    mock_markdown_parser_instance = AsyncMock(spec=BaseParser)
    mock_markdown_parser_instance.parse.return_value = asyncio.as_completed(MOCK_MARKDOWN_PARSER_OUTPUT).__aiter__()

    original_parser_map = PARSER_MAP.copy()
    PARSER_MAP.clear()
    PARSER_MAP["python"] = lambda: mock_python_parser_instance
    PARSER_MAP["markdown"] = lambda: mock_markdown_parser_instance

    results = []
    async for item in process_repository(str(mock_tmp_path), MOCK_REPO_ID):
        results.append(item)

    PARSER_MAP.update(original_parser_map)

    assert len(results) == 1 + len(mock_discovery_results) + len(MOCK_PYTHON_PARSER_OUTPUT) + len(MOCK_MARKDOWN_PARSER_OUTPUT)

    assert isinstance(results[0], Repository)
    assert results[0].id == MOCK_REPO_ID
    assert results[0].path == str(abs_repo_path)

    sf_item_1 = results[1]
    assert isinstance(sf_item_1, tuple) and len(sf_item_1) == 2
    assert isinstance(sf_item_1[0], SourceFile)
    assert sf_item_1[0].id == f"{MOCK_REPO_ID}:{MOCK_FILE_CONTEXT_1['relative_path']}"
    assert sf_item_1[1] == MOCK_FILE_CONTEXT_1

    sf_item_2 = results[2]
    assert isinstance(sf_item_2, tuple) and len(sf_item_2) == 2
    assert isinstance(sf_item_2[0], SourceFile)
    assert sf_item_2[0].id == f"{MOCK_REPO_ID}:{MOCK_FILE_CONTEXT_2['relative_path']}"
    assert sf_item_2[1] == MOCK_FILE_CONTEXT_2

    sf_item_unsupported = results[3]
    assert isinstance(sf_item_unsupported, tuple) and len(sf_item_unsupported) == 2
    assert isinstance(sf_item_unsupported[0], SourceFile)
    assert sf_item_unsupported[0].id == f"{MOCK_REPO_ID}:{MOCK_FILE_CONTEXT_UNSUPPORTED['relative_path']}"
    assert sf_item_unsupported[1] == MOCK_FILE_CONTEXT_UNSUPPORTED

    parser_outputs_yielded = results[1 + len(mock_discovery_results):]

    assert MOCK_PYTHON_PARSER_OUTPUT[0] in parser_outputs_yielded
    assert MOCK_PYTHON_PARSER_OUTPUT[1] in parser_outputs_yielded
    assert MOCK_PYTHON_PARSER_OUTPUT[2] in parser_outputs_yielded
    assert MOCK_MARKDOWN_PARSER_OUTPUT[0] in parser_outputs_yielded

    mock_python_parser_instance.parse.assert_called_once_with(
        str(abs_repo_path / MOCK_FILE_CONTEXT_1["relative_path"]),
        f"{MOCK_REPO_ID}:{MOCK_FILE_CONTEXT_1['relative_path']}"
    )
    mock_markdown_parser_instance.parse.assert_called_once_with(
        str(abs_repo_path / MOCK_FILE_CONTEXT_2["relative_path"]),
        f"{MOCK_REPO_ID}:{MOCK_FILE_CONTEXT_2['relative_path']}"
    )


@patch("src.parser.orchestrator.discover_files")
@patch("src.parser.orchestrator.logger")
async def test_process_repository_no_parser_found(mock_logger: MagicMock, mock_discover_files: AsyncMock, mock_tmp_path: Path):
    abs_repo_path = mock_tmp_path.resolve()
    mock_discovery_results = [
        (str(abs_repo_path / MOCK_FILE_CONTEXT_UNSUPPORTED["relative_path"]), MOCK_FILE_CONTEXT_UNSUPPORTED["relative_path"], MOCK_FILE_CONTEXT_UNSUPPORTED["language_key"]),
    ]
    mock_discover_files.return_value = asyncio.as_completed(mock_discovery_results).__aiter__()
    original_parser_map = PARSER_MAP.copy()
    PARSER_MAP.clear()

    results = []
    async for item in process_repository(str(mock_tmp_path), MOCK_REPO_ID):
        results.append(item)

    PARSER_MAP.update(original_parser_map)

    assert len(results) == 1 + 1
    assert isinstance(results[0], Repository)
    assert isinstance(results[1], tuple) and isinstance(results[1][0], SourceFile)

    mock_logger.warning.assert_any_call(f"No parser for lang '{MOCK_FILE_CONTEXT_UNSUPPORTED['language_key']}' of file {abs_repo_path / MOCK_FILE_CONTEXT_UNSUPPORTED['relative_path']}")


@patch("src.parser.orchestrator.discover_files")
@patch("src.parser.orchestrator.logger")
async def test_process_repository_parser_instantiation_error(mock_logger: MagicMock, mock_discover_files: AsyncMock, mock_tmp_path: Path):
    abs_repo_path = mock_tmp_path.resolve()
    mock_discovery_results = [
        (str(abs_repo_path / MOCK_FILE_CONTEXT_1["relative_path"]), MOCK_FILE_CONTEXT_1["relative_path"], MOCK_FILE_CONTEXT_1["language_key"]),
    ]
    mock_discover_files.return_value = asyncio.as_completed(mock_discovery_results).__aiter__()

    class FailingParser(BaseParser):
        def __init__(self): raise ValueError("Init failed")
        async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[BaseModel, None]: yield

    original_parser_map = PARSER_MAP.copy()
    PARSER_MAP.clear()
    PARSER_MAP["python"] = FailingParser

    results = []
    async for item in process_repository(str(mock_tmp_path), MOCK_REPO_ID):
        results.append(item)

    PARSER_MAP.update(original_parser_map)

    assert len(results) == 1 + 1
    mock_logger.error.assert_any_call(f"Failed to init parser for {MOCK_FILE_CONTEXT_1['language_key']}: Init failed", exc_info=ANY)


@patch("src.parser.orchestrator.discover_files")
@patch("src.parser.orchestrator._run_parser_for_file_task", new_callable=AsyncMock)
@patch("src.parser.orchestrator.logger")
async def test_process_repository_parser_execution_error(mock_logger: MagicMock, mock_run_task: AsyncMock, mock_discover_files: AsyncMock, mock_tmp_path: Path):
    abs_repo_path = mock_tmp_path.resolve()
    mock_discovery_results = [
        (str(abs_repo_path / MOCK_FILE_CONTEXT_1["relative_path"]), MOCK_FILE_CONTEXT_1["relative_path"], MOCK_FILE_CONTEXT_1["language_key"]),
    ]
    mock_discover_files.return_value = asyncio.as_completed(mock_discovery_results).__aiter__()

    simulated_exception = ValueError("Parsing execution error")
    mock_run_task.side_effect = simulated_exception

    original_parser_map = PARSER_MAP.copy()
    PARSER_MAP.clear()
    class DummyParser(BaseParser):
        async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[BaseModel, None]: yield
    PARSER_MAP["python"] = DummyParser

    results = []
    async for item in process_repository(str(mock_tmp_path), MOCK_REPO_ID, concurrency_limit=1):
        results.append(item)

    PARSER_MAP.update(original_parser_map)

    assert len(results) == 1 + 1
    mock_run_task.assert_called_once()

    logged_gather_error = False
    for call_args, call_kwargs in mock_logger.error.call_args_list:
        if "Parser task failed" in call_args[0] and "Parsing execution error" in str(call_args[1]):
            logged_gather_error = True
            break
    assert logged_gather_error, "Error from _run_parser_for_file_task was not logged by process_repository"
