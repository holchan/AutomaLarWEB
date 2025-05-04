# .roo/cognee/tests/parser/test_git_utils.py
import pytest
import git
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY

from src.parser import git_utils
from src.parser.git_utils import TEMP_CLONE_BASE_DIR

@pytest.mark.parametrize("url, expected_name", [
    ("https://github.com/user/my-repo.git", "my-repo"),
    ("http://gitlab.com/group/subgroup/project.git", "project"),
    ("git@github.com:user/another_repo.git", "another_repo"),
    ("https://dev.azure.com/org/proj/_git/repo-name", "repo-name"),
    ("ssh://user@host.xz/path/to/repo.git/", "repo.git"),
    ("file:///path/to/local/repo/.git", ".git"),
    ("just_a_name", "just_a_name"),
])
def test_get_repo_name_from_url(url, expected_name):
    assert git_utils.get_repo_name_from_url(url) == expected_name

@patch('src.parser.git_utils.git.Repo.clone_from')
@patch('src.parser.git_utils.Path.mkdir')
@patch('src.parser.git_utils.Path.exists')
@patch('src.parser.git_utils.shutil.rmtree')
def test_clone_repo_to_temp_success(mock_rmtree, mock_exists, mock_mkdir, mock_clone_from):
    """Test successful cloning."""
    repo_url = "https://github.com/test/success.git"
    expected_repo_name = "success"
    expected_temp_path_obj = TEMP_CLONE_BASE_DIR / expected_repo_name
    expected_temp_path_str = str(expected_temp_path_obj)
    expected_repo_id = "github.com/test/success"

    mock_exists.return_value = False

    result = git_utils.clone_repo_to_temp(repo_url)

    assert result is not None
    assert result[0] == expected_temp_path_str
    assert result[1] == expected_repo_id
    mock_mkdir.assert_has_calls([
        call(parents=True, exist_ok=True),
        call(parents=True)
    ], any_order=True)
    mock_clone_from.assert_called_once_with(repo_url, expected_temp_path_str, depth=1)
    mock_rmtree.assert_not_called()

@patch('src.parser.git_utils.git.Repo.clone_from')
@patch('src.parser.git_utils.Path.mkdir')
@patch('src.parser.git_utils.Path.exists')
@patch('src.parser.git_utils.shutil.rmtree')
def test_clone_repo_to_temp_dir_exists(mock_rmtree, mock_exists, mock_mkdir, mock_clone_from):
    """Test cloning when the temporary directory already exists."""
    repo_url = "https://github.com/test/exists.git"
    expected_repo_name = "exists"
    expected_temp_path_obj = TEMP_CLONE_BASE_DIR / expected_repo_name
    expected_temp_path_str = str(expected_temp_path_obj)
    expected_repo_id = "github.com/test/exists"

    mock_exists.return_value = True

    result = git_utils.clone_repo_to_temp(repo_url)

    assert result is not None
    assert result[0] == expected_temp_path_str
    assert result[1] == expected_repo_id
    mock_exists.assert_called_once()
    mock_rmtree.assert_called_once_with(expected_temp_path_obj)
    mock_mkdir.assert_has_calls([
        call(parents=True, exist_ok=True),
        call(parents=True)
    ], any_order=True)
    mock_clone_from.assert_called_once_with(repo_url, expected_temp_path_str, depth=1)


@patch('src.parser.git_utils.git.Repo.clone_from', side_effect=git.GitCommandError("clone", "failed", "stderr"))
@patch('src.parser.git_utils.Path.mkdir')
@patch('src.parser.git_utils.Path.exists', return_value=False)
@patch('src.parser.git_utils.shutil.rmtree')
@patch('src.parser.git_utils.logger')
def test_clone_repo_to_temp_git_error(mock_logger, mock_rmtree, mock_exists, mock_mkdir, mock_clone_from):
    """Test handling of GitCommandError during clone."""
    repo_url = "https://github.com/test/fail.git"

    result = git_utils.clone_repo_to_temp(repo_url)

    assert result is None
    mock_clone_from.assert_called_once()
    mock_logger.error.assert_called_once()
    assert "Git command failed" in mock_logger.error.call_args[0][0]
    mock_rmtree.assert_called_once()


@patch('src.parser.git_utils.git.Repo.clone_from', side_effect=Exception("Unexpected error"))
@patch('src.parser.git_utils.Path.mkdir')
@patch('src.parser.git_utils.Path.exists', return_value=False)
@patch('src.parser.git_utils.shutil.rmtree')
@patch('src.parser.git_utils.logger')
def test_clone_repo_to_temp_unexpected_error(mock_logger, mock_rmtree, mock_exists, mock_mkdir, mock_clone_from):
    """Test handling of unexpected exceptions during clone."""
    repo_url = "https://github.com/test/unexpected.git"

    result = git_utils.clone_repo_to_temp(repo_url)

    assert result is None
    mock_clone_from.assert_called_once()
    mock_logger.error.assert_called_once()
    assert "Unexpected error cloning" in mock_logger.error.call_args[0][0]
    mock_rmtree.assert_called_once()

@patch('src.parser.git_utils.Path')
@patch('src.parser.git_utils.shutil.rmtree')
@patch('src.parser.git_utils.logger')
def test_cleanup_temp_repo_success(mock_logger, mock_rmtree, mock_path_class):
    """Test successful cleanup of a valid temporary directory."""
    valid_temp_path_str = str(TEMP_CLONE_BASE_DIR / "some_repo")
    mock_path_instance = MagicMock()
    mock_path_instance.is_dir.return_value = True
    mock_path_instance.parents = [TEMP_CLONE_BASE_DIR, Path("/")]
    mock_path_class.return_value = mock_path_instance

    git_utils.cleanup_temp_repo(valid_temp_path_str)

    mock_path_class.assert_called_with(valid_temp_path_str)
    mock_path_instance.is_dir.assert_called_once()
    mock_rmtree.assert_called_once_with(mock_path_instance, ignore_errors=True)
    mock_logger.info.assert_called_once_with(f"Cleaning up temporary repository directory: {valid_temp_path_str}")

@patch('src.parser.git_utils.Path')
@patch('src.parser.git_utils.shutil.rmtree')
@patch('src.parser.git_utils.logger')
def test_cleanup_temp_repo_not_a_directory(mock_logger, mock_rmtree, mock_path_class):
    """Test cleanup attempt on a path that is not a directory."""
    invalid_path_str = str(TEMP_CLONE_BASE_DIR / "not_a_dir")
    mock_path_instance = MagicMock()
    mock_path_instance.is_dir.return_value = False
    mock_path_instance.parents = [TEMP_CLONE_BASE_DIR, Path("/")]
    mock_path_class.return_value = mock_path_instance

    git_utils.cleanup_temp_repo(invalid_path_str)

    mock_path_class.assert_called_with(invalid_path_str)
    mock_path_instance.is_dir.assert_called_once()
    mock_rmtree.assert_not_called()
    mock_logger.warning.assert_called_once_with(f"Skipping cleanup for path '{invalid_path_str}' - not a valid temp repo directory.")

@patch('src.parser.git_utils.Path')
@patch('src.parser.git_utils.shutil.rmtree')
@patch('src.parser.git_utils.logger')
def test_cleanup_temp_repo_outside_base_dir(mock_logger, mock_rmtree, mock_path_class):
    """Test cleanup attempt on a path outside the designated temp base directory."""
    outside_path_str = "/some/other/path"
    mock_path_instance = MagicMock()
    mock_path_instance.is_dir.return_value = True
    mock_path_instance.parents = [Path("/some/other"), Path("/some"), Path("/")]
    mock_path_class.return_value = mock_path_instance

    git_utils.cleanup_temp_repo(outside_path_str)

    mock_path_class.assert_called_with(outside_path_str)
    mock_path_instance.is_dir.assert_called_once()
    mock_rmtree.assert_not_called()
    mock_logger.warning.assert_called_once_with(f"Skipping cleanup for path '{outside_path_str}' - not a valid temp repo directory.")

@patch('src.parser.git_utils.shutil.rmtree')
@patch('src.parser.git_utils.logger')
def test_cleanup_temp_repo_none_path(mock_logger, mock_rmtree):
    """Test cleanup with None path."""
    git_utils.cleanup_temp_repo(None)
    mock_rmtree.assert_not_called()
    mock_logger.warning.assert_called_once_with("Skipping cleanup for path 'None' - not a valid temp repo directory.")
