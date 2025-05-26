import pytest
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import subprocess
import os
from datetime import datetime

from src.parser import git_utils
from src.parser.git_utils import TEMP_CLONE_BASE_DIR

@pytest.mark.parametrize("url, expected_name", [
    ("https://github.com/user/my-repo.git", "my-repo"),
    ("http://gitlab.com/group/subgroup/project.git", "project"),
    ("git@github.com:user/another_repo.git", "another_repo"),
])
def test_get_repo_name_from_url(url, expected_name):
    assert git_utils.get_repo_name_from_url(url) == expected_name

@patch('src.parser.git_utils.subprocess.run')
@patch('src.parser.git_utils.Path.mkdir')
@patch('src.parser.git_utils.shutil.rmtree')
@patch('src.parser.git_utils.datetime')
def test_clone_repo_to_temp_success(mock_datetime, mock_rmtree, mock_mkdir, mock_subprocess_run):
    repo_url = "https://github.com/test/success.git"
    mock_datetime.now.return_value.strftime.return_value = "testtimestamp"

    expected_sanitized_name = "success"
    unique_dir_name = f"{expected_sanitized_name}_testtimestamp"
    expected_temp_path_obj = TEMP_CLONE_BASE_DIR / unique_dir_name
    expected_temp_path_str = str(expected_temp_path_obj.resolve())
    expected_repo_id = "github.com/test/success"

    mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

    result = git_utils.clone_repo_to_temp(repo_url)

    assert result is not None
    assert result[0] == expected_temp_path_str
    assert result[1] == expected_repo_id

    mock_mkdir.assert_any_call(parents=True, exist_ok=True)
    mock_mkdir.assert_any_call(parents=True, exist_ok=True)

    mock_subprocess_run.assert_called_once_with(
        ["git", "clone", "--depth", "1", repo_url, expected_temp_path_str],
        capture_output=True, text=True, check=False, encoding='utf-8', errors='ignore'
    )
    mock_rmtree.assert_not_called()


@patch('src.parser.git_utils.subprocess.run')
@patch('src.parser.git_utils.Path.mkdir')
@patch('src.parser.git_utils.Path.exists')
@patch('src.parser.git_utils.shutil.rmtree')
@patch('src.parser.git_utils.logger')
@patch('src.parser.git_utils.datetime')
def test_clone_repo_to_temp_git_error(mock_datetime, mock_logger, mock_rmtree, mock_path_exists, mock_mkdir, mock_subprocess_run):
    repo_url = "https://github.com/test/fail.git"
    mock_datetime.now.return_value.strftime.return_value = "testerrorstamp"
    mock_subprocess_run.return_value = MagicMock(returncode=1, stdout="some output", stderr="git clone error")

    expected_sanitized_name = "fail"
    unique_dir_name = f"{expected_sanitized_name}_testerrorstamp"
    temp_dir_for_failure = TEMP_CLONE_BASE_DIR / unique_dir_name

    mock_path_exists.return_value = True

    result = git_utils.clone_repo_to_temp(repo_url)

    assert result is None
    mock_subprocess_run.assert_called_once()
    mock_logger.error.assert_any_call(f"Failed to clone repository: {repo_url}. Git output: git clone error")
    mock_rmtree.assert_called_once_with(str(temp_dir_for_failure.resolve()))


@patch('src.parser.git_utils.shutil.rmtree')
@patch('src.parser.git_utils.logger')
def test_cleanup_temp_repo_success(mock_logger, mock_rmtree):
    valid_temp_path_str = str(TEMP_CLONE_BASE_DIR / "some_repo_toclean")

    with patch('src.parser.git_utils.Path') as mock_path_class:
        mock_path_instance = MagicMock()
        mock_path_instance.resolve.return_value = Path(valid_temp_path_str)
        mock_path_instance.exists.return_value = True
        mock_path_instance.is_dir.return_value = True
        mock_path_instance.parents = [TEMP_CLONE_BASE_DIR.resolve()]
        mock_path_class.return_value = mock_path_instance

        with patch.object(TEMP_CLONE_BASE_DIR, 'resolve', return_value=TEMP_CLONE_BASE_DIR.resolve()):
            git_utils.cleanup_temp_repo(valid_temp_path_str)

    mock_rmtree.assert_called_once_with(valid_temp_path_str)
    mock_logger.info.assert_any_call(f"Cleaning up temporary repository: {valid_temp_path_str}")


@patch('src.parser.git_utils.shutil.rmtree')
@patch('src.parser.git_utils.logger')
def test_cleanup_temp_repo_none_path(mock_logger, mock_rmtree):
    git_utils.cleanup_temp_repo(None)
    mock_rmtree.assert_not_called()
    assert not any("Skipping cleanup" in call_args[0][0] for call_args in mock_logger.warning.call_args_list if call_args[0])

@patch('src.parser.git_utils.Path')
@patch('src.parser.git_utils.shutil.rmtree')
@patch('src.parser.git_utils.logger')
def test_cleanup_temp_repo_outside_base_dir(mock_logger, mock_rmtree, mock_path_class):
    outside_path_str = "/some/other/path/to/repo"

    mock_path_instance = MagicMock()
    mock_path_instance.resolve.return_value = Path(outside_path_str)
    mock_path_instance.exists.return_value = True
    mock_path_instance.is_dir.return_value = True
    mock_path_instance.parents = [Path("/some/other/path"), Path("/some/other"), Path("/some")]
    mock_path_class.return_value = mock_path_instance

    with patch.object(TEMP_CLONE_BASE_DIR, 'resolve', return_value=TEMP_CLONE_BASE_DIR.resolve()):
      git_utils.cleanup_temp_repo(outside_path_str)

    mock_rmtree.assert_not_called()
    mock_logger.warning.assert_any_call(
        f"Skipping cleanup: Path {outside_path_str} (resolved: {Path(outside_path_str)}) is not within the designated temp base directory {TEMP_CLONE_BASE_DIR.resolve()}"
    )
