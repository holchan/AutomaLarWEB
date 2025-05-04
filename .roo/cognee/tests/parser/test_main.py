# .roo/cognee/tests/parser/test_main.py
import pytest
import asyncio
import argparse
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock, call

pytestmark = pytest.mark.asyncio

from pydantic import BaseModel
class MockEntity(BaseModel):
    id: str
    type: str

async def async_generator_wrapper(items):
    for item in items:
        yield item
        await asyncio.sleep(0)

@patch('src.main.argparse.ArgumentParser')
@patch('src.main.run_parser')
async def test_main_local_path(mock_run_parser, mock_arg_parser):
    """Test main entry point with a local path argument."""
    mock_args = argparse.Namespace(
        target="/fake/local/repo",
        repo_id=None,
        project_name="test_project",
        concurrency=10,
        verbose=False,
        keep_temp=False
    )
    mock_arg_parser.return_value.parse_args.return_value = mock_args
    mock_run_parser.return_value = async_generator_wrapper([MockEntity(id="item1", type="TypeA")])

    with patch('src.main.run_parser', return_value=async_generator_wrapper([MockEntity(id="item1", type="TypeA")])) as mock_rp_in_main:
        from src.main import main as main_func
        await main_func()

        mock_rp_in_main.assert_called_once_with(
            target="/fake/local/repo",
            repo_id_override=None,
            project_name_local="test_project",
            concurrency=10,
            keep_temp=False
        )

@patch('src.main.clone_repo_to_temp')
@patch('src.main.process_repository')
@patch('src.main.cleanup_temp_repo')
async def test_run_parser_git_url(mock_cleanup, mock_process_repo, mock_clone):
    """Test run_parser specifically with a Git URL."""
    git_url = "https://github.com/test/repo.git"
    temp_clone_path = "/tmp/fake_clone_path"
    derived_repo_id = "github.com/test/repo"
    mock_clone.return_value = (temp_clone_path, derived_repo_id)

    mock_repo_node = MockEntity(id=derived_repo_id, type="Repository")
    mock_file_node = MockEntity(id=f"{derived_repo_id}:file.py", type="SourceFile")
    mock_process_repo.return_value = async_generator_wrapper([mock_repo_node, mock_file_node])

    results = []
    from src.main import run_parser
    async for item in run_parser(target=git_url, concurrency=5):
        results.append(item)

    mock_clone.assert_called_once_with(git_url)
    mock_process_repo.assert_called_once_with(temp_clone_path, derived_repo_id, concurrency_limit=5)
    assert len(results) == 2
    assert results[0] == mock_repo_node
    assert results[1] == mock_file_node
    mock_cleanup.assert_called_once_with(temp_clone_path)

@patch('src.main.clone_repo_to_temp')
@patch('src.main.process_repository')
@patch('src.main.cleanup_temp_repo')
async def test_run_parser_git_url_keep_temp(mock_cleanup, mock_process_repo, mock_clone):
    """Test run_parser with Git URL and keep_temp=True."""
    git_url = "https://github.com/test/repo.git"
    temp_clone_path = "/tmp/fake_clone_path"
    derived_repo_id = "github.com/test/repo"
    mock_clone.return_value = (temp_clone_path, derived_repo_id)
    mock_process_repo.return_value = async_generator_wrapper([])

    from src.main import run_parser
    async for _ in run_parser(target=git_url, keep_temp=True):
        pass

    mock_clone.assert_called_once_with(git_url)
    mock_process_repo.assert_called_once_with(temp_clone_path, derived_repo_id, concurrency_limit=50)
    mock_cleanup.assert_not_called()

@patch('src.main.Path')
@patch('src.main.process_repository')
async def test_run_parser_local_path(mock_process_repo, mock_path):
    """Test run_parser specifically with a local directory path."""
    local_target_path = "/fake/local/target"
    project_name = "my_local_proj"
    expected_repo_id = f"local/{project_name}"
    expected_abs_path = "/abs/fake/local/target"

    mock_path_instance = mock_path.return_value
    mock_path_instance.is_dir.return_value = True
    mock_path_instance.absolute.return_value = Path(expected_abs_path)

    mock_repo_node = MockEntity(id=expected_repo_id, type="Repository")
    mock_process_repo.return_value = async_generator_wrapper([mock_repo_node])

    from src.main import run_parser
    results = []
    async for item in run_parser(target=local_target_path, project_name_local=project_name, concurrency=20):
        results.append(item)

    mock_path.assert_called_with(local_target_path)
    mock_path_instance.is_dir.assert_called_once()
    mock_path_instance.absolute.assert_called_once()
    mock_process_repo.assert_called_once_with(expected_abs_path, expected_repo_id, concurrency_limit=20)
    assert len(results) == 1
    assert results[0] == mock_repo_node

@patch('src.main.Path')
@patch('src.main.logger')
async def test_run_parser_local_path_not_dir(mock_logger, mock_path):
    """Test run_parser when local path is not a directory."""
    local_target_path = "/fake/not_a_dir"
    mock_path_instance = mock_path.return_value
    mock_path_instance.is_dir.return_value = False

    from src.main import run_parser
    results = []
    async for item in run_parser(target=local_target_path):
        results.append(item)

    mock_path.assert_called_with(local_target_path)
    mock_path_instance.is_dir.assert_called_once()
    assert len(results) == 0
    mock_logger.error.assert_called_with(f"Local path '{local_target_path}' is not a valid directory.")
