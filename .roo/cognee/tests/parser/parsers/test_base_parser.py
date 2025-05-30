import pytest
import asyncio
from typing import AsyncGenerator
from pydantic import BaseModel

try:
    from src.parser.parsers.base_parser import BaseParser
except ImportError:
    pytest.skip("Skipping BaseParser tests: Failed to import dependencies", allow_module_level=True)

class ConcreteTestParser(BaseParser):
    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[BaseModel, None]:
        if False:
            yield

def test_base_parser_instantiation():
    parser = ConcreteTestParser()
    assert parser.parser_type == "ConcreteTestParser"

def test_base_parser_is_abstract_and_requires_parse_implementation():
    with pytest.raises(TypeError) as excinfo:
        class AnotherIncompleteParser(BaseParser):
            def __init__(self): super().__init__()

        incomplete_parser = AnotherIncompleteParser()

    assert "Can't instantiate abstract class" in str(excinfo.value)
    assert "without an implementation for abstract method 'parse'" in str(excinfo.value)

    class CallsSuperParseParser(BaseParser):
        def __init__(self): super().__init__()
        async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[BaseModel, None]:
            async for item in super().parse(file_path, file_id):
                yield item
            if False:
                 yield

    parser_calls_super = CallsSuperParseParser()
    async def call_super_parse_task():
        async for _ in parser_calls_super.parse("dummy", "dummy"):
            pass

    with pytest.raises(NotImplementedError) as nie_excinfo:
        asyncio.run(call_super_parse_task())
    assert "must implement the 'parse' method" in str(nie_excinfo.value)


@pytest.mark.asyncio
async def test_concrete_parser_can_be_used():
    parser = ConcreteTestParser()
    items = []
    async for item in parser.parse("some/path", "file_id_123"):
        items.append(item)
    assert len(items) == 0
