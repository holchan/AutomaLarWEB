# src/parser/parsers/markdown_parser.py
from typing import AsyncGenerator
from .base_parser import BaseParser
from ..entities import DataPoint, TextChunk
from ..chunking import basic_chunker
from ..utils import read_file_content, logger

# Attempt to import mistune for more advanced parsing (optional)
try:
    import mistune
    MD_LOADED = True
    # You could configure mistune plugins here if needed
    # markdown_parser = mistune.create_markdown(renderer=None, plugins=[...])
    markdown_parser = mistune.create_markdown(renderer=None) # Basic block tokenizer
except ImportError:
    MD_LOADED = False
    markdown_parser = None

class MarkdownParser(BaseParser):
    """Parses Markdown files (.md, .mdx), yielding text chunks."""

    def __init__(self):
        super().__init__()
        if not MD_LOADED:
            logger.info("Mistune library not found. Markdown parsing will rely solely on basic chunking.")

    async def parse(self, file_path: str, file_id: str) -> AsyncGenerator[DataPoint, None]:
        """Parses a Markdown file, yielding text chunks."""
        logger.debug(f"Parsing Markdown file: {file_path}")
        content = await read_file_content(file_path)
        if content is None:
            logger.error(f"Could not read content from {file_path}")
            return

        try:
            # 1. Yield Chunks using the basic chunker
            chunks = basic_chunker(content)
            for i, chunk_text in enumerate(chunks):
                if not chunk_text.strip(): continue
                chunk_id_str = f"{file_id}:chunk:{i}"
                yield TextChunk(chunk_id_str=chunk_id_str, parent_id=file_id, text=chunk_text, chunk_index=i)

            # 2. Optional: Advanced parsing with Mistune (if loaded)
            # This could yield specific entities like headings, code blocks, tables etc.
            # For now, we primarily rely on the chunks above.
            if MD_LOADED and markdown_parser:
                try:
                    tokens = markdown_parser.parse(content)
                    # Example: Iterate tokens and potentially yield structured data
                    # for token in tokens:
                    #     if token['type'] == 'heading':
                    #         # yield HeadingEntity(...)
                    #     elif token['type'] == 'block_code':
                    #         # yield CodeBlockEntity(...)
                    logger.debug(f"Successfully tokenized Markdown with Mistune for {file_path} (found {len(tokens)} tokens).")
                    # Currently not yielding specific entities from tokens, just chunking.
                except Exception as e:
                    logger.error(f"Error during Mistune tokenization for {file_path}: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Failed to parse Markdown file {file_path}: {e}", exc_info=True)
