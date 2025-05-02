# src/parser/parsers/treesitter_setup.py
import os
import traceback
from typing import Dict, Any, Optional
from ..utils import logger

try: import tree_sitter_python as tspython
except ImportError: tspython = None; logger.debug("tree_sitter_python binding not found.")
try: import tree_sitter_javascript as tsjavascript
except ImportError: tsjavascript = None; logger.debug("tree_sitter_javascript binding not found.")
try: import tree_sitter_typescript as tstypescript_module
except ImportError: tstypescript_module = None; logger.debug("tree_sitter_typescript binding package not found.")
try: import tree_sitter_c as tsc
except ImportError: tsc = None; logger.debug("tree_sitter_c binding not found.")
try: import tree_sitter_cpp as tscpp
except ImportError: tscpp = None; logger.debug("tree_sitter_cpp binding not found.")
try: import tree_sitter_rust as tsrust
except ImportError: tsrust = None; logger.debug("tree_sitter_rust binding not found.")

try:
    from tree_sitter import Language, Parser
    TS_CORE_AVAILABLE = True
    logger.info("Tree-sitter core library loaded successfully.")
except ImportError as e:
    logger.error(f"Tree-sitter core library not found or failed to import: {e}. Tree-sitter parsing will be disabled.")
    TS_CORE_AVAILABLE = False
    Language = None
    Parser = None

LANGUAGES: Dict[str, Language] = {}
PARSERS: Dict[str, Parser] = {}

LanguageModuleInput = Optional[Any]

def _load_language(lang_name: str, lang_module: LanguageModuleInput):
    """Helper function to load a single tree-sitter language."""
    if not TS_CORE_AVAILABLE:
        logger.debug(f"Skipping load for '{lang_name}': Core library not available.")
        return
    if lang_module is None:
        logger.debug(f"Skipping load for '{lang_name}': Language binding module not installed or import failed.")
        return

    logger.info(f"Attempting to load tree-sitter language: {lang_name}")
    try:
        language_callable = None
        if hasattr(lang_module, 'language') and callable(lang_module.language):
            language_callable = lang_module.language
        elif lang_name == "typescript" and hasattr(lang_module, 'language_typescript') and callable(lang_module.language_typescript):
            language_callable = lang_module.language_typescript

        if not language_callable:
            logger.error(f"Could not find language callable for {lang_name} in the imported module {lang_module}.")
            return

        language_raw = language_callable()

        language_obj = Language(language_raw)

        if not isinstance(language_obj, Language):
            logger.error(f"Loading '{lang_name}' failed: Expected tree_sitter.Language, got {type(language_obj)}.")
            return

        LANGUAGES[lang_name] = language_obj
        parser = Parser()
        parser.set_language(language_obj)
        PARSERS[lang_name] = parser
        logger.info(f"Successfully loaded and configured Language/Parser for: {lang_name}")

    except AttributeError as ae:
        logger.error(f"AttributeError loading language '{lang_name}': {ae}. Check binding compatibility.", exc_info=True)
    except Exception as e:
        tb_str = traceback.format_exc()
        logger.error(f"Unexpected error loading language '{lang_name}': {e}\n{tb_str}")

logger.info("Loading available tree-sitter languages...")
_load_language("python", tspython)
_load_language("javascript", tsjavascript)
_load_language("typescript", tstypescript_module)
_load_language("c", tsc)
_load_language("cpp", tscpp)
_load_language("rust", tsrust)
logger.info("Finished attempting to load tree-sitter languages.")

def get_parser(language_key: str) -> Optional[Parser]:
    """Gets the pre-configured tree-sitter parser instance for a given language key."""
    if not TS_CORE_AVAILABLE: return None
    parser = PARSERS.get(language_key)
    if parser is None:
        if language_key in ["python", "javascript", "typescript", "c", "cpp", "rust"]:
            logger.warning(f"Tree-sitter parser for language '{language_key}' not available (binding installed but loading failed?).")
    return parser

def get_language(language_key: str) -> Optional[Language]:
    """Gets the tree-sitter Language object for a given language key."""
    if not TS_CORE_AVAILABLE: return None
    language = LANGUAGES.get(language_key)
    if language is None:
        if language_key in ["python", "javascript", "typescript", "c", "cpp", "rust"]: # Add expected keys
            logger.warning(f"Tree-sitter language object for '{language_key}' not available (binding installed but loading failed?).")
    return language
