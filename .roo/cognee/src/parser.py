# .roo/cognee/src/parser.py

import os
import asyncio
import math
import uuid
from typing import List, AsyncGenerator, Dict, Any, Optional, Type
from uuid import uuid5, NAMESPACE_OID

# --- Cognee Imports ---
try:
    from cognee.modules.pipelines.tasks.task import Task
    from cognee.modules.pipelines.operations.pipeline import run_tasks
    from cognee.infrastructure.databases.graph import get_graph_engine
    from cognee.modules.users.models import User
    from cognee.shared.data_models import DataPoint, Document
    from cognee.shared.CodeGraphEntities import (
        Repository,
        CodeFile,
        FunctionDefinition,
        ClassDefinition,
        ImportStatement,
    )
    from cognee.tasks.repo_processor.get_repo_file_dependencies import get_source_code_files
    from cognee.modules.ingestion.classify import classify_file_type
    from cognee.infrastructure.entities.registry import get_entity_extractor
    from cognee.infrastructure.entities.BaseEntityExtractor import BaseEntityExtractor
    from cognee.tasks.storage import add_data_points
    from cognee.shared.logging_utils import get_logger
    from cognee.shared.utils import read_file_content

except ImportError as e:
    print(f"CRITICAL Error importing Cognee components for parser.py: {e}")
    print("Ensure Cognee environment is correctly set up.")
    print("Check paths for: Task, run_tasks, get_graph_engine, User, DataPoint, Document, CodeGraphEntities,")
    print("  *get_source_code_files*, *classify_file_type*, *get_entity_extractor*, BaseEntityExtractor, add_data_points, read_file_content")
    raise

logger = get_logger(__name__)

# Define a consistent UUID namespace for code/data elements
DATA_NAMESPACE = uuid.UUID('f0df4ff1-9c6f-4e1a-9e1a-1a5d7f3b4b5f') # Can be same as before

# --- Helper: Process a Single File Dynamically ---

async def _process_single_file(
    file_path: str,
    repo_node: Repository,
    dataset_id: str,
    user: User,
    detailed_extraction: bool,
) -> AsyncGenerator[DataPoint, None]:
    """
    Processes a single file: classifies, gets extractor, extracts entities, yields DataPoints.
    """
    relative_path = os.path.relpath(file_path, repo_node.path)
    file_id = str(uuid5(DATA_NAMESPACE, f"{repo_node.path}:{relative_path}"))
    filename = os.path.basename(file_path)
    logger.debug(f"Processing file: {relative_path}")

    try:
        # 1. Classify File Type (Using Cognee's utility)
        file_type = await classify_file_type(file_path) # e.g., returns 'python', 'markdown', 'pdf', 'unknown'
        logger.debug(f"File {relative_path} classified as: {file_type}")

        if file_type == 'unknown':
            logger.warning(f"Skipping file {relative_path}: Unknown or unsupported file type.")
            return

        # 2. Get the Appropriate Entity Extractor (Using Cognee's registry)
        # This function should return an instance of a BaseEntityExtractor subclass or None
        extractor: Optional[BaseEntityExtractor] = await get_entity_extractor(file_type)

        if not extractor:
            logger.warning(f"Skipping file {relative_path}: No registered extractor for type '{file_type}'.")
            return

        # 3. Read File Content (Safely)
        content = await read_file_content(file_path)
        if content is None:
            logger.error(f"Could not read content for file: {relative_path}")
            return

        # 4. Create the primary File/Document Node
        # Use CodeFile specifically for code, maybe a generic Document for others? Adapt as needed.
        # This depends on how your retriever and CodeGraphEntities are set up.
        if file_type == "python": # Or other recognized code types
            file_node = CodeFile(
                id=file_id,
                name=filename,
                file_path=relative_path,
                repository_id=repo_node.id,
                language=file_type,
                dataset_id=dataset_id,
                part_of=repo_node, # Explicit relationship
                # user_id=user.id,
                # content_hash=str(uuid5(DATA_NAMESPACE, content)), # Optional hash
            )
            # Optionally add source_code if needed directly on CodeFile by retriever
            # file_node.source_code = content # Careful with large files
        else:
            # Generic Document node for non-code files (if your schema supports it)
            file_node = Document(
                id=file_id,
                name=filename,
                path=relative_path, # Use 'path' or consistent field
                document_type=file_type,
                dataset_id=dataset_id,
                part_of=repo_node, # Link back to repo
                # user_id=user.id,
            )
            # file_node.text_content = content # Store text if needed

        logger.debug(f"Yielding File/Document node: {type(file_node).__name__} ({file_node.id})")
        yield file_node

        # 5. Extract detailed entities using the selected extractor
        if detailed_extraction:
            # The extractor should return a list of DataPoint instances (Functions, Classes, Sections, etc.)
            extracted_entities = await extractor.extract_entities(content, source_identifier=relative_path)

            for entity in extracted_entities:
                # Ensure entity has necessary context/links
                entity_base_id_str = f"{repo_node.path}:{relative_path}:{type(entity).__name__}:{getattr(entity, 'name', uuid.uuid4())}"
                entity.id = str(uuid5(DATA_NAMESPACE, entity_base_id_str))
                entity.defined_in = file_node # Link back to the parent file/document node
                entity.dataset_id = dataset_id # Propagate dataset ID
                # entity.user_id = user.id

                # **** Granular Detail Check ****
                # TODO: Verify that the specific 'extractor' used captures required details
                # like docstrings, comments, code snippets if they are needed by the retriever.
                # The BaseEntityExtractor interface or specific implementations might need adjustments.
                # Example: Ensure FunctionDefinition includes 'docstring' field if needed.
                # if isinstance(entity, FunctionDefinition):
                #    assert hasattr(entity, 'docstring'), "Extractor needs to provide docstrings!"

                logger.debug(f"Yielding Extracted Entity: {type(entity).__name__} ({entity.id}) from {relative_path}")
                yield entity

    except Exception as e:
        logger.error(f"Error processing file {relative_path}: {e}", exc_info=True)

# --- Task 1: Code & Data Extraction (Revised with Chunking & Dynamic Dispatch) ---

async def discover_and_extract_entities_chunked(
    repo_path: str,
    dataset_id: str,
    user: User,
    target_languages: Optional[List[str]] = None, # Might be less needed if classify_file_type handles all
    detailed_extraction: bool = True,
    chunk_size: int = 50, # Configurable chunk size for processing
) -> AsyncGenerator[DataPoint, None]:
    """
    Walks a repository using Cognee utils, chunks files, processes them dynamically,
    and yields DataPoint objects.
    """
    logger.info(f"Starting entity extraction for repo: {repo_path}, dataset: {dataset_id}, chunk_size: {chunk_size}")

    # 1. Create and yield the Repository node
    repo_id = str(uuid5(DATA_NAMESPACE, repo_path))
    repo_node = Repository(
        id=repo_id,
        path=repo_path,
        name=os.path.basename(repo_path),
        dataset_id=dataset_id,
        # user_id=user.id
    )
    logger.debug(f"Yielding Repository node: {repo_node.id}")
    yield repo_node

    # 2. Get Relevant Files using Cognee's Centralized Utility
    try:
        # Replace with the actual function signature and filtering logic from Cognee
        # This should handle ignores (.git, venv, test patterns, etc.)
        # It might take language hints or rely purely on classification later
        all_files = await get_source_code_files(repo_path) # Adapt if it only gets .py, or use a more generic file lister
        logger.info(f"Discovered {len(all_files)} potential files using Cognee utility.")
        # Optional filtering if target_languages is still relevant:
        # relevant_files = [f for f in all_files if any(f.endswith(ext) for ext in target_languages or [])]
        relevant_files = all_files # Assume for now classification handles types

    except Exception as e:
        logger.error(f"Failed to discover files using Cognee utility: {e}", exc_info=True)
        return # Stop if file discovery fails

    if not relevant_files:
        logger.warning(f"No relevant files found in {repo_path} after filtering.")
        return

    # 3. Implement Chunking
    num_files = len(relevant_files)
    num_chunks = math.ceil(num_files / chunk_size)
    logger.info(f"Processing {num_files} files in {num_chunks} chunks of size {chunk_size}.")

    for i in range(num_chunks):
        start_index = i * chunk_size
        end_index = start_index + chunk_size
        file_chunk = relevant_files[start_index:end_index]
        logger.debug(f"Processing chunk {i+1}/{num_chunks} ({len(file_chunk)} files)")

        # 4. Process Chunk Concurrently using the dynamic helper
        process_tasks = [
            _process_single_file(
                file_path=file_path,
                repo_node=repo_node,
                dataset_id=dataset_id,
                user=user,
                detailed_extraction=detailed_extraction
            ) for file_path in file_chunk
        ]

        # Gather results from all async generators in the chunk
        # Note: asyncio.gather works on awaitables. We need to consume the async generators.
        async def consume_generator(gen):
            results = []
            async for item in gen:
                results.append(item)
            return results

        all_chunk_results = await asyncio.gather(*(consume_generator(task) for task in process_tasks))

        # 5. Yield all DataPoints gathered from the chunk
        for file_results in all_chunk_results:
            for data_point in file_results:
                yield data_point

        logger.debug(f"Finished processing chunk {i+1}/{num_chunks}")
        await asyncio.sleep(0) # Yield control between chunks

    logger.info(f"Entity extraction finished for {repo_path}.")


# --- Task 2: Graph Ingestion (Leverages existing task) ---
# We reuse `add_data_points`


# --- Pipeline Orchestration (Mostly unchanged, but uses the revised Task 1) ---

async def parse_and_ingest_repo_aligned( # Renamed function slightly
    repo_path: str,
    dataset_id: str,
    user: User,
    # target_languages: Optional[List[str]] = None, # Less critical now
    detailed_extraction: bool = True,
    proc_chunk_size: int = 50, # Chunk size for processing files
    ingest_batch_size: int = 100, # Batch size for graph ingestion
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Orchestrates the ALIGNED pipeline to parse a repository (multi-format capable)
    and ingest it into the graph using chunking and dynamic extractors.
    Yields status updates.
    """
    if not os.path.isdir(repo_path):
        logger.error(f"Repository path not found or not a directory: {repo_path}")
        raise FileNotFoundError(f"Repository path not found: {repo_path}")

    logger.info(f"Starting ALIGNED ingestion pipeline for repo: {repo_path}, dataset: {dataset_id}")

    # Define the pipeline tasks using the revised extraction task
    tasks = [
        # Task 1: Extract entities chunked and dynamically
        Task(
            discover_and_extract_entities_chunked,
            repo_path=repo_path,
            dataset_id=dataset_id,
            user=user,
            # target_languages=target_languages, # Pass if still needed by discovery util
            detailed_extraction=detailed_extraction,
            chunk_size=proc_chunk_size, # Pass chunk size config
        ),
        # Task 2: Ingest the yielded DataPoint objects into the graph.
        Task(
            add_data_points,
            task_config={"batch_size": ingest_batch_size} # Configure batching for storage
        ),
    ]

    # Run the pipeline using Cognee's runner
    pipeline_name = f"aligned_parser_ingestion_{dataset_id}"
    try:
        # Assuming run_tasks signature is correct
        async for run_status in run_tasks(
            tasks=tasks,
            dataset_id=dataset_id,
            data_source_path=repo_path,
            user=user,
            pipeline_name=pipeline_name,
        ):
            logger.info(f"Pipeline Status ({pipeline_name}): {run_status.status} - {run_status.message}")
            yield run_status.dict()

        logger.info(f"Successfully completed ALIGNED ingestion pipeline for repo: {repo_path}")

    except Exception as e:
        logger.exception(f"ALIGNED Pipeline failed for repo {repo_path}: {e}")
        yield {"pipeline_name": pipeline_name, "status": "failed", "message": str(e)}


# --- Example Usage ---
async def main_test_aligned():
    print("Running ALIGNED parser.py test...")
    try:
        from cognee.modules.users.utils import get_default_user
        test_user = await get_default_user()
    except Exception as e:
        print(f"Could not get default user: {e}. Using mock user.")
        test_user = User(id="test-user-id", name="Test User")

    test_repo_path = "/path/to/your/local/test/repo/with/mixed/files" # <--- CHANGE THIS
    test_dataset_id = "my_mixed_dataset_1"

    if not os.path.exists(test_repo_path):
        print(f"ERROR: Test repository path does not exist: {test_repo_path}")
        return

    print(f"Starting ALIGNED ingestion for: {test_repo_path}")
    async for status in parse_and_ingest_repo_aligned(
        repo_path=test_repo_path,
        dataset_id=test_dataset_id,
        user=test_user,
        detailed_extraction=True,
        proc_chunk_size=20, # Smaller chunk size for testing
        ingest_batch_size=50
    ):
        print(f"Pipeline Update: {status}")

    print("ALIGNED Test finished.")

if __name__ == "__main__":
    try:
        # IMPORTANT: Ensure the placeholder Cognee utilities referenced above
        # (get_source_code_files, classify_file_type, get_entity_extractor, read_file_content)
        # actually exist and work as expected in your Cognee installation.
        # You might need to implement or adapt them based on Cognee's internal structure.
        asyncio.run(main_test_aligned())
    except NameError as ne:
        print(f"ERROR: A required Cognee utility might be missing or named differently: {ne}")
        print("Please verify the import paths and function names for centralized file discovery, classification, and extractor registry.")
    except Exception as e:
        print(f"Error running main test: {e}")
