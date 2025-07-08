# .roo/cognee/tests/conftest.py
from dataclasses import dataclass
import pytest
# IMPORTANT: Import the new, correct entities
from src.parser.entities import CodeEntity, RawSymbolReference, ParserOutput

@dataclass
class ParserTestOutput:
    slice_lines: List[int]
    code_entities: List[CodeEntity]
    raw_symbol_references: List[RawSymbolReference] # <-- CHANGED

@pytest.fixture
def parse_file_and_collect_output():
    async def _parse_and_collect(parser, source_id, content):
        output = ParserTestOutput(slice_lines=[], code_entities=[], raw_symbol_references=[]) # <-- CHANGED
        async for item in parser.parse(source_id, content):
            if isinstance(item, list):
                output.slice_lines.extend(item)
            elif isinstance(item, CodeEntity):
                output.code_entities.append(item)
            elif isinstance(item, RawSymbolReference): # <-- CHANGED
                output.raw_symbol_references.append(item)
        return output
    return _parse_and_collect
