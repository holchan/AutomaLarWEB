import pytest
from pydantic import ValidationError
from datetime import datetime, timezone, timedelta

try:
    from src.parser.entities import Repository, SourceFile, TextChunk, CodeEntity, Relationship
except ImportError:
    pytest.skip("Skipping entity tests: Failed to import entities from src.parser.entities", allow_module_level=True)

def test_repository_creation():
    repo_id = "my-company/my-repo"
    repo_path = "/path/to/cloned/my-repo"
    repo = Repository(id=repo_id, path=repo_path)

    assert repo.id == repo_id
    assert repo.path == repo_path
    assert repo.type == "Repository"

def test_repository_id_is_string():
    repo = Repository(id="test-repo", path="/test")
    assert isinstance(repo.id, str)

def test_sourcefile_creation():
    sf_id = "my-repo:src/main.py"
    sf_path = "/path/to/cloned/my-repo/src/main.py"

    sf1 = SourceFile(id=sf_id, file_path=sf_path)
    assert sf1.id == sf_id
    assert sf1.file_path == sf_path
    assert sf1.type == "SourceFile"
    assert isinstance(sf1.timestamp, str)
    try:
        datetime.fromisoformat(sf1.timestamp.replace("Z", "+00:00"))
    except ValueError:
        pytest.fail(f"Default timestamp '{sf1.timestamp}' is not a valid ISO 8601 string.")

    custom_ts = datetime.now(timezone.utc).isoformat()
    sf2 = SourceFile(id=sf_id, file_path=sf_path, timestamp=custom_ts)
    assert sf2.timestamp == custom_ts

def test_sourcefile_requires_fields():
    with pytest.raises(ValidationError):
        SourceFile(id="test-id")
    with pytest.raises(ValidationError):
        SourceFile(file_path="/path")

def test_textchunk_creation():
    tc_id = "my-repo:src/main.py:0"
    tc_start = 10
    tc_end = 25
    tc_content = "This is a line of code.\nAnd another one."

    tc = TextChunk(id=tc_id, start_line=tc_start, end_line=tc_end, chunk_content=tc_content)
    assert tc.id == tc_id
    assert tc.start_line == tc_start
    assert tc.end_line == tc_end
    assert tc.chunk_content == tc_content
    assert tc.type == "TextChunk"

def test_textchunk_requires_fields():
    with pytest.raises(ValidationError):
        TextChunk(id="id", start_line=1, end_line=2)
    with pytest.raises(ValidationError):
        TextChunk(id="id", chunk_content="c")

def test_codeentity_creation():
    ce_id = "my-repo:src/main.py:0:FunctionDefinition:my_func:0"
    ce_type = "FunctionDefinition"
    ce_snippet = "def my_func():\n  pass"

    ce = CodeEntity(id=ce_id, type=ce_type, snippet_content=ce_snippet)
    assert ce.id == ce_id
    assert ce.type == ce_type
    assert ce.snippet_content == ce_snippet

def test_codeentity_requires_fields():
    with pytest.raises(ValidationError):
        CodeEntity(id="id", type="FunctionDefinition")

def test_relationship_creation():
    rel_source = "my-repo:src/main.py:0:FunctionDefinition:my_func:0"
    rel_target = "my-repo:src/utils.py:0:FunctionDefinition:helper:0"
    rel_type = "CALLS"
    rel_props = {"line_number": 42, "async_call": True}

    rel1 = Relationship(source_id=rel_source, target_id=rel_target, type=rel_type)
    assert rel1.source_id == rel_source
    assert rel1.target_id == rel_target
    assert rel1.type == rel_type
    assert rel1.properties is None

    rel2 = Relationship(source_id=rel_source, target_id=rel_target, type=rel_type, properties=rel_props)
    assert rel2.properties == rel_props

def test_relationship_target_can_be_literal():
    rel_source = "my-repo:src/main.py"
    rel_target_literal = "os"
    rel_type = "IMPORTS"

    rel = Relationship(source_id=rel_source, target_id=rel_target_literal, type=rel_type)
    assert rel.target_id == rel_target_literal

def test_relationship_requires_fields():
    with pytest.raises(ValidationError):
        Relationship(source_id="s", target_id="t")
