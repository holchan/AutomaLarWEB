import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock, call, ANY
from typing import List, Tuple, Dict, Any, AsyncGenerator, Union, Optional
import uuid

from pydantic import BaseModel as PydanticBaseModel, Field

pytestmark = pytest.mark.asyncio

class MockDataPoint(PydanticBaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    type: str
    slug_id: str

class MockRepositoryNode(MockDataPoint):
    path: str

class MockSourceFileNode(MockDataPoint):
    file_path: str

CogneeEdgeTupleMock = Tuple[uuid.UUID, uuid.UUID, str, Dict[str, Any]]

class MockParserRepository(PydanticBaseModel): id: str; path: str; type: str = "Repository"
class MockParserSourceFile(PydanticBaseModel): id: str; file_path: str; type: str = "SourceFile"; timestamp: str = "ts"
class MockParserTextChunk(PydanticBaseModel): id: str; type: str = "TextChunk"; start_line: int = 1; end_line: int = 1; chunk_content: str = "c"
class MockParserCodeEntity(PydanticBaseModel): id: str; type: str = "FunctionDefinition"; snippet_content: str = "s"
class MockParserRelationship(PydanticBaseModel): source_id: str; target_id: str; type: str; properties: Optional[Dict] = None

OrchestratorOutputItemMock = Union[
    MockParserRepository,
    Tuple[MockParserSourceFile, Dict[str, str]],
    MockParserTextChunk, MockParserCodeEntity, MockParserRelationship
]

async def mock_process_repository_stream_generator(items: List[OrchestratorOutputItemMock]) -> AsyncGenerator[OrchestratorOutputItemMock, None]:
    for item in items:
        yield item
        await asyncio.sleep(0)

async def mock_adapter_function(
    stream: AsyncGenerator[OrchestratorOutputItemMock, None]
) -> Tuple[List[MockDataPoint], List[CogneeEdgeTupleMock]]:

    mock_nodes: List[MockDataPoint] = []
    mock_edges: List[CogneeEdgeTupleMock] = []

    async for item in stream:
        if isinstance(item, MockParserRepository):
            mock_nodes.append(MockRepositoryNode(slug_id=item.id, path=item.path, type=item.type))
        elif isinstance(item, tuple) and isinstance(item[0], MockParserSourceFile):
            sf_node = item[0]
            mock_nodes.append(MockSourceFileNode(slug_id=sf_node.id, file_path=sf_node.file_path, type=sf_node.type))

    if len(mock_nodes) > 1:
        mock_edges.append((mock_nodes[0].id, mock_nodes[1].id, "MOCK_CONTAINS", {}))

    return mock_nodes, mock_edges

MAIN_MODULE_PATH = 'src.main'

@patch(f'{MAIN_MODULE_PATH}.process_repository', new_callable=AsyncMock)
@patch(f'{MAIN_MODULE_PATH}.adapt_parser_to_graph_elements', new_callable=AsyncMock)
@patch(f'{MAIN_MODULE_PATH}.get_graph_engine', new_callable=AsyncMock)
@patch(f'{MAIN_MODULE_PATH}.add_data_points', new_callable=AsyncMock)
@patch(f'{MAIN_MODULE_PATH}.index_graph_edges', new_callable=AsyncMock)
@patch(f'{MAIN_MODULE_PATH}.clone_repo_to_temp')
@patch(f'{MAIN_MODULE_PATH}.cleanup_temp_repo')
@patch(f'{MAIN_MODULE_PATH}.logger')
async def test_run_ingestion_local_path(
    mock_main_logger: MagicMock, mock_cleanup: MagicMock, mock_clone: MagicMock,
    mock_index_edges: AsyncMock, mock_add_data_points: AsyncMock,
    mock_get_engine: AsyncMock,
    mock_adapter: AsyncMock, mock_orchestrator: AsyncMock,
    tmp_path: Path
):
    try:
        from src.main import run_ingestion
    except ImportError:
        pytest.skip(f"{MAIN_MODULE_PATH} or run_ingestion function not found.")
        return

    local_repo_path = str(tmp_path / "my_local_project")
    Path(local_repo_path).mkdir()
    repo_id = "my_project_id"

    mock_orchestrator_output: List[OrchestratorOutputItemMock] = [MockParserRepository(id=repo_id, path=local_repo_path)]
    mock_orchestrator.return_value = mock_process_repository_stream_generator(mock_orchestrator_output)

    mock_nodes_out: List[MockDataPoint] = [MockRepositoryNode(slug_id=repo_id, path=local_repo_path, type="Repository")]
    mock_edges_out: List[CogneeEdgeTupleMock] = []
    mock_adapter.return_value = (mock_nodes_out, mock_edges_out)

    mock_engine_instance = AsyncMock()
    mock_get_engine.return_value = mock_engine_instance

    await run_ingestion(repo_url_or_path=local_repo_path, repo_id_override=repo_id)

    mock_orchestrator.assert_called_once_with(repo_path=local_repo_path, repo_id=repo_id, concurrency_limit=ANY)
    mock_adapter.assert_called_once()
    mock_add_data_points.assert_called_once_with(data_points=mock_nodes_out)
    mock_get_engine.assert_not_called()
    mock_engine_instance.add_edges.assert_not_called()
    mock_index_edges.assert_not_called()
    mock_clone.assert_not_called()
    mock_cleanup.assert_not_called()


@patch(f'{MAIN_MODULE_PATH}.process_repository', new_callable=AsyncMock)
@patch(f'{MAIN_MODULE_PATH}.adapt_parser_to_graph_elements', new_callable=AsyncMock)
@patch(f'{MAIN_MODULE_PATH}.get_graph_engine', new_callable=AsyncMock)
@patch(f'{MAIN_MODULE_PATH}.add_data_points', new_callable=AsyncMock)
@patch(f'{MAIN_MODULE_PATH}.index_graph_edges', new_callable=AsyncMock)
@patch(f'{MAIN_MODULE_PATH}.clone_repo_to_temp')
@patch(f'{MAIN_MODULE_PATH}.cleanup_temp_repo')
@patch(f'{MAIN_MODULE_PATH}.logger')
async def test_run_ingestion_git_url(
    mock_main_logger: MagicMock, mock_cleanup: MagicMock, mock_clone: MagicMock,
    mock_index_edges: AsyncMock, mock_add_data_points: AsyncMock,
    mock_get_engine: AsyncMock,
    mock_adapter: AsyncMock, mock_orchestrator: AsyncMock
):
    try:
        from src.main import run_ingestion
    except ImportError:
        pytest.skip(f"{MAIN_MODULE_PATH} or run_ingestion function not found.")
        return

    git_url = "https://github.com/test/myrepo.git"
    cloned_path = "/tmp/cloned_myrepo_xyz"
    cloned_repo_id = "github.com/test/myrepo"
    mock_clone.return_value = (cloned_path, cloned_repo_id)

    mock_orchestrator_output: List[OrchestratorOutputItemMock] = [
        MockParserRepository(id=cloned_repo_id, path=cloned_path)
    ]
    mock_orchestrator.return_value = mock_process_repository_stream_generator(mock_orchestrator_output)

    mock_nodes_out: List[MockDataPoint] = [MockRepositoryNode(slug_id=cloned_repo_id, path=cloned_path, type="Repository")]
    node1_uuid = mock_nodes_out[0].id
    node2_uuid = uuid.uuid4()

    mock_sf_node = MockSourceFileNode(id=f"{cloned_repo_id}:file.py", file_path=f"{cloned_path}/file.py", type="SourceFile")
    mock_nodes_out.append(mock_sf_node)
    node2_uuid = mock_sf_node.id

    mock_edges_out: List[CogneeEdgeTupleMock] = [(node1_uuid, node2_uuid, "CONTAINS_FILE_MOCK", {})]
    mock_adapter.return_value = (mock_nodes_out, mock_edges_out)

    mock_engine_instance = AsyncMock()
    mock_get_engine.return_value = mock_engine_instance

    await run_ingestion(repo_url_or_path=git_url)

    mock_clone.assert_called_once_with(git_url)
    mock_orchestrator.assert_called_once_with(repo_path=cloned_path, repo_id=cloned_repo_id, concurrency_limit=ANY)
    mock_adapter.assert_called_once()
    mock_add_data_points.assert_called_once_with(data_points=mock_nodes_out)

    mock_get_engine.assert_called_once()
    mock_engine_instance.add_edges.assert_called_once_with(edges=mock_edges_out)
    mock_index_edges.assert_called_once_with()
    mock_cleanup.assert_called_once_with(cloned_path)


@patch(f'{MAIN_MODULE_PATH}.clone_repo_to_temp')
@patch(f'{MAIN_MODULE_PATH}.logger')
async def test_run_ingestion_git_clone_fails(
    mock_main_logger: MagicMock, mock_clone: MagicMock
):
    try:
        from src.main import run_ingestion
    except ImportError:
        pytest.skip(f"{MAIN_MODULE_PATH} or run_ingestion function not found.")
        return

    git_url = "https://github.com/test/nonexistent.git"
    mock_clone.return_value = None

    await run_ingestion(repo_url_or_path=git_url)

    mock_clone.assert_called_once_with(git_url)
    mock_main_logger.error.assert_any_call(f"Failed to clone repository: {git_url}")


@patch(f'{MAIN_MODULE_PATH}.process_repository', new_callable=AsyncMock)
@patch(f'{MAIN_MODULE_PATH}.logger')
async def test_run_ingestion_orchestrator_error(
    mock_main_logger: MagicMock, mock_orchestrator: AsyncMock, tmp_path: Path
):
    try:
        from src.main import run_ingestion
    except ImportError:
        pytest.skip(f"{MAIN_MODULE_PATH} or run_ingestion function not found.")
        return

    local_repo_path = str(tmp_path / "error_repo")
    Path(local_repo_path).mkdir()
    repo_id = "error_repo_id"

    mock_orchestrator.side_effect = Exception("Orchestrator boom!")

    await run_ingestion(repo_url_or_path=local_repo_path, repo_id_override=repo_id)

    mock_orchestrator.assert_called_once_with(repo_path=local_repo_path, repo_id=repo_id, concurrency_limit=ANY)
    mock_main_logger.error.assert_any_call(f"An error occurred during the ingestion process for {repo_id}: Orchestrator boom!", exc_info=True)

@patch(f'{MAIN_MODULE_PATH}.process_repository', new_callable=AsyncMock)
@patch(f'{MAIN_MODULE_PATH}.adapt_parser_to_graph_elements', new_callable=AsyncMock)
@patch(f'{MAIN_MODULE_PATH}.add_data_points', new_callable=AsyncMock)
@patch(f'{MAIN_MODULE_PATH}.logger')
async def test_run_ingestion_adapter_error(
    mock_main_logger: MagicMock, mock_add_data_points: AsyncMock,
    mock_adapter: AsyncMock, mock_orchestrator: AsyncMock, tmp_path: Path
):
    try:
        from src.main import run_ingestion
    except ImportError:
        pytest.skip(f"{MAIN_MODULE_PATH} or run_ingestion function not found.")
        return

    local_repo_path = str(tmp_path / "adapter_error_repo")
    Path(local_repo_path).mkdir()
    repo_id = "adapter_error_id"

    mock_orchestrator_output: List[OrchestratorOutputItemMock] = [MockParserRepository(id=repo_id, path=local_repo_path)]
    mock_orchestrator.return_value = mock_process_repository_stream_generator(mock_orchestrator_output)

    mock_adapter.side_effect = Exception("Adapter kaboom!")

    await run_ingestion(repo_url_or_path=local_repo_path, repo_id_override=repo_id)

    mock_orchestrator.assert_called_once()
    mock_adapter.assert_called_once()
    mock_add_data_points.assert_not_called()
    mock_main_logger.error.assert_any_call(f"An error occurred during the ingestion process for {repo_id}: Adapter kaboom!", exc_info=True)
