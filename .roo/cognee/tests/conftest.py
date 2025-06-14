import pytest
import asyncio
from pathlib import Path
from typing import List, Union, Optional, Dict, Any, TYPE_CHECKING, AsyncGenerator
from pydantic import BaseModel

from src.parser.entities import CodeEntity, Relationship, CallSiteReference, ParserOutput
if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser

class ParserTestOutput(BaseModel):
    """
    Aggregates all distinct types of outputs a parser might yield during a single file parse.
    Used by the test helper fixture to return a structured result to test functions.
    """
    slice_lines: List[int] = []
    code_entities: List[CodeEntity] = []
    relationships: List[Relationship] = []
    call_site_references: List[CallSiteReference] = []

@pytest.fixture(scope="function")
def parse_file_and_collect_output():
    """
    Provides an async function to run a parser instance against specific file content
    and collect all its yielded outputs into a structured ParserTestOutput object.
    It also performs common checks (e.g., slice_lines yielded once and correctly).
    """
    async def _execute_parser_and_collect(
        parser_instance: 'BaseParser',
        source_file_id: str,
        file_content: str,
        test_file_path_for_debug: Path
    ) -> ParserTestOutput:
        collected_slice_lines: List[int] = []
        slice_lines_yielded_count = 0
        collected_code_entities: List[CodeEntity] = []
        collected_relationships: List[Relationship] = []
        collected_call_sites: List[CallSiteReference] = []

        parser_stream: AsyncGenerator[ParserOutput, None] = parser_instance.parse(source_file_id, file_content)

        async for item in parser_stream:
            if isinstance(item, list) and all(isinstance(i, int) for i in item):
                slice_lines_yielded_count += 1
                if slice_lines_yielded_count > 1:
                    if collected_slice_lines is not None and collected_slice_lines != []:
                         pytest.fail(
                            f"Parser for '{test_file_path_for_debug.name}' (ID: {source_file_id}) "
                            f"yielded slice_lines more than once. "
                            f"Previous: {collected_slice_lines}, New: {item}"
                         )
                collected_slice_lines = item
            elif isinstance(item, CodeEntity):
                collected_code_entities.append(item)
            elif isinstance(item, Relationship):
                collected_relationships.append(item)
            elif isinstance(item, CallSiteReference):
                collected_call_sites.append(item)
            else:
                pytest.fail(
                    f"Parser for '{test_file_path_for_debug.name}' (ID: {source_file_id}) "
                    f"yielded an unexpected item type: {type(item)}. Item: {item}"
                )

        if not file_content.strip():
            if slice_lines_yielded_count > 0 and collected_slice_lines:
                pytest.fail(
                    f"Parser for empty/blank file '{test_file_path_for_debug.name}' (ID: {source_file_id}) "
                    f"yielded non-empty slice_lines: {collected_slice_lines}. Expected an empty list [] or no slice_lines yield."
                )
        else:
            if not slice_lines_yielded_count and not collected_slice_lines:
                pytest.fail(
                    f"Parser for non-empty file '{test_file_path_for_debug.name}' (ID: {source_file_id}) "
                    f"did not yield slice_lines."
                )
            elif slice_lines_yielded_count > 0 and not collected_slice_lines :
                 pytest.fail(
                    f"Parser for non-empty file '{test_file_path_for_debug.name}' (ID: {source_file_id}) "
                    f"yielded an empty list for slice_lines."
                )
            elif collected_slice_lines and 0 not in collected_slice_lines:
                pytest.fail(
                    f"Parser slice_lines for non-empty file '{test_file_path_for_debug.name}' (ID: {source_file_id}) "
                    f"must contain 0. Got: {collected_slice_lines}"
                )

        return ParserTestOutput(
            slice_lines=collected_slice_lines,
            code_entities=collected_code_entities,
            relationships=collected_relationships,
            call_site_references=collected_call_sites
        )
    return _execute_parser_and_collect
