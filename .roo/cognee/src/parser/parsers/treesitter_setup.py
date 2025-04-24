# src/parser/parsers/treesitter_setup.py
from typing import Dict, Any, Optional
from ..utils import logger

# --- Tree-sitter Imports ---
# Attempt to import all required language bindings
# Individual parsers will check if their specific language loaded successfully
try:
    import tree_sitter_python as tspython
except ImportError: tspython = None
try:
    import tree_sitter_javascript as tsjavascript
except ImportError: tsjavascript = None
try:
    # Note the specific import path for typescript
    import tree_sitter_typescript.typescript as tstypescript
except ImportError: tstypescript = None
try:
    import tree_sitter_c as tsc
except ImportError: tsc = None
try:
    import tree_sitter_cpp as tscpp
except ImportError: tscpp = None
try:
    import tree_sitter_rust as tsrust
except ImportError: tsrust = None
# Add imports for other languages here as needed
# try: import tree_sitter_java as tsjava
# except ImportError: tsjava = None

try:
    from tree_sitter import Language, Parser
    TS_CORE_AVAILABLE = True
    logger.info("Tree-sitter core library loaded successfully.")
except ImportError as e:
    logger.error(f"Tree-sitter core library not found or failed to import: {e}. Tree-sitter parsing will be disabled.")
    TS_CORE_AVAILABLE = False
    Language = None # type: ignore
    Parser = None # type: ignore


# --- Language Setup ---
# These dictionaries will store the loaded language objects and parser instances
LANGUAGES: Dict[str, Language] = {}
PARSERS: Dict[str, Parser] = {}

def _load_language(lang_name: str, lang_module: Optional[Any]):
    """Helper function to load a single tree-sitter language."""
    if not TS_CORE_AVAILABLE or lang_module is None:
        logger.warning(f"Skipping load for '{lang_name}': Core library or language binding missing.")
        return
    try:
        language = Language(lang_module.language())
        LANGUAGES[lang_name] = language
        parser = Parser() # Create a new parser instance for each language
        parser.set_language(language) # IMPORTANT: Set the language on the parser instance
        PARSERS[lang_name] = parser
        logger.info(f"Successfully loaded and configured tree-sitter language: {lang_name}")
    except Exception as e:
        logger.error(f"Failed to load tree-sitter language '{lang_name}': {e}", exc_info=True)

# Load all potentially supported languages
# The keys used here ('python', 'javascript', etc.) MUST match the keys
# used in config.SUPPORTED_EXTENSIONS for dispatching.
logger.info("Loading tree-sitter languages...")
_load_language("python", tspython)
_load_language("javascript", tsjavascript)
_load_language("typescript", tstypescript)
_load_language("c", tsc)
_load_language("cpp", tscpp)
_load_language("rust", tsrust)
# Add calls for other languages here
# _load_language("java", tsjava)
logger.info("Finished loading tree-sitter languages.")


def get_parser(language_key: str) -> Optional[Parser]:
    """
    Gets the pre-configured tree-sitter parser instance for a given language key.

    Args:
        language_key: The key identifying the language (e.g., 'python', 'javascript').

    Returns:
        A tree_sitter.Parser instance configured for the language, or None if not loaded.
    """
    if not TS_CORE_AVAILABLE:
        return None
    parser = PARSERS.get(language_key)
    if parser is None:
        logger.warning(f"Tree-sitter parser for language '{language_key}' not available or failed to load.")
    return parser

def get_language(language_key: str) -> Optional[Language]:
    """
    Gets the tree-sitter Language object for a given language key.
    Useful for compiling language-specific queries.

    Args:
        language_key: The key identifying the language (e.g., 'python', 'javascript').

    Returns:
        A tree_sitter.Language object, or None if not loaded.
    """
    if not TS_CORE_AVAILABLE:
        return None
    language = LANGUAGES.get(language_key)
    if language is None:
         logger.warning(f"Tree-sitter language object for '{language_key}' not available or failed to load.")
    return language
