import pytest
import json
import hashlib
from pathlib import Path
from typing import List, Union, TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser
    from src.parser.entities import Repository, SourceFile, TextChunk, CodeEntity, Relationship
    ParserOutputUnion = Union[Repository, SourceFile, TextChunk, CodeEntity, Relationship]


@pytest.fixture(scope="function")
def run_parser_and_save_output():
    async def _run_parser(
        parser: 'BaseParser',
        test_file_path: Path,
        output_dir: Path,
        file_id_override: str = None
    ) -> List[BaseModel]:
        if not test_file_path.is_file():
            pytest.fail(f"Test input file not found: {test_file_path}")

        if file_id_override:
            file_id_for_parser = file_id_override
        else:
            file_id_base = str(test_file_path.absolute())
            file_id_for_parser = f"test_parser_file_id_{hashlib.sha1(file_id_base.encode()).hexdigest()[:10]}"

        results_pydantic_objects: List[BaseModel] = []
        try:
            async for item in parser.parse(file_path=str(test_file_path), file_id=file_id_for_parser):
                results_pydantic_objects.append(item)
        except Exception as e:
            print(f"\nERROR during parser execution for {test_file_path.name}: {e}")
            pytest.fail(f"Parser execution failed for {test_file_path.name}: {e}", pytrace=True)

        output_filename = output_dir / f"parsed_{test_file_path.stem}_output.json"
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            payloads_to_save = [dp.model_dump(mode='json') for dp in results_pydantic_objects]
            with open(output_filename, "w", encoding="utf-8") as f:
                json.dump(payloads_to_save, f, indent=2, ensure_ascii=False, sort_keys=True, default=str)
            print(f"\n[Test Output] Saved parser results for '{test_file_path.name}' to: {output_filename}")
        except AttributeError:
             print(f"\n[Test Output] WARNING: model_dump() not found for {test_file_path.name}.")
        except Exception as e:
            print(f"\n[Test Output] WARNING: Failed to save test output for {test_file_path.name}: {e}")
        return results_pydantic_objects
    return _run_parser
