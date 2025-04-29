# src/parser/parsers/treesitter_setup.py
import os
import traceback
from typing import Dict, Any, Optional, Callable, Union
from ..utils import logger

# --- Tree-sitter Imports ---
try:
    import tree_sitter_python as tspython
except ImportError: tspython = None; logger.debug("tree_sitter_python not found.")
try:
    import tree_sitter_javascript as tsjavascript
except ImportError: tsjavascript = None; logger.debug("tree_sitter_javascript not found.")
# --- FIX: Import TypeScript module only ---
try:
    import tree_sitter_typescript as tstypescript_module
    logger.debug("Successfully imported tree_sitter_typescript module.")
except ImportError:
    tstypescript_module = None # Keep fallback for import error
    logger.debug("tree_sitter_typescript binding package not found.")
# --- END FIX ---
try:
    import tree_sitter_c as tsc
except ImportError: tsc = None; logger.debug("tree_sitter_c not found.")
try:
    import tree_sitter_cpp as tscpp
except ImportError: tscpp = None; logger.debug("tree_sitter_cpp not found.")
try:
    import tree_sitter_rust as tsrust
except ImportError: tsrust = None; logger.debug("tree_sitter_rust not found.")


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
LANGUAGES: Dict[str, Language] = {}
PARSERS: Dict[str, Parser] = {}

# Define a type hint for the input
LanguageModuleInput = Optional[Any] # Simpler hint for module

def _load_language(lang_name: str, lang_module: LanguageModuleInput): # Simplified param name
    """Helper function to load a single tree-sitter language."""
    if not TS_CORE_AVAILABLE:
         logger.warning(f"Skipping load for '{lang_name}': Core library not available.")
         return
    if lang_module is None:
         logger.warning(f"Skipping load for '{lang_name}': Language binding module not provided or import failed.")
         return

    logger.debug(f"Attempting to load tree-sitter language: {lang_name}")
    try:
        language_callable = None
        # --- Standard way to find the callable ---
        # Most bindings expose '.language()' directly on the module
        if hasattr(lang_module, 'language') and callable(lang_module.language):
            language_callable = lang_module.language
            logger.debug(f"Found language callable via attribute '.language' for {lang_name}")
        # --- Check for TypeScript's specific attribute ---
        elif lang_name == "typescript" and hasattr(lang_module, 'language_typescript') and callable(lang_module.language_typescript):
             language_callable = lang_module.language_typescript # Use the specific 'language_typescript' attribute
             logger.debug(f"Found language callable via attribute '.language_typescript' for {lang_name}")
        else:
            # If neither common pattern works, log error and exit for this lang
            logger.error(f"Could not find language callable for {lang_name} using known patterns (.language or .language_typescript). Module type: {type(lang_module)}")
            return # Stop processing this language

        if not language_callable:
             # This path shouldn't be reached if the checks above are exhaustive, but added defensively
             logger.error(f"Unexpected: Failed to resolve language callable for {lang_name} after checks.")
             return

        # --- Use Language() constructor CONSISTENTLY for ALL languages ---
        language_raw = language_callable()
        language_obj = Language(language_raw) # This might trigger DeprecationWarning
        # --- END CONSISTENT HANDLING ---

        # Add type check before storing
        if not isinstance(language_obj, Language):
            logger.error(f"CRITICAL TYPE MISMATCH for '{lang_name}': Expected tree_sitter.Language, but got {type(language_obj)}. Raw value was {type(language_raw)}. Storing failed.")
            return # Exit the function for this language

        LANGUAGES[lang_name] = language_obj
        parser = Parser()
        parser.language = language_obj
        PARSERS[lang_name] = parser
        logger.info(f"Successfully created and stored Language/Parser for: {lang_name}")

    except AttributeError as ae:
         # This might catch issues if the assumed callable structure is wrong
         logger.error(f"AttributeError processing language binding for '{lang_name}': {ae}.", exc_info=True)
    except Exception as e:
        tb_str = traceback.format_exc()
        logger.error(f"Detailed error loading language '{lang_name}': {e}\n{tb_str}")


# --- Load all potentially supported languages ---
logger.info("Loading tree-sitter languages...")
_load_language("python", tspython)
_load_language("javascript", tsjavascript)
# --- FIX: Pass the imported MODULE for TypeScript ---
_load_language("typescript", tstypescript_module)
# --- END FIX ---
_load_language("c", tsc)
_load_language("cpp", tscpp)
_load_language("rust", tsrust)
logger.info("Finished loading tree-sitter languages.")


# --- get_parser and get_language functions remain the same ---
# ... (rest of file) ...
def get_parser(language_key: str) -> Optional[Parser]:
    """Gets the pre-configured tree-sitter parser instance for a given language key."""
    if not TS_CORE_AVAILABLE:
        logger.debug("get_parser: Tree-sitter core not available.") # DEBUG
        return None
    parser = PARSERS.get(language_key)
    if parser is None:
        # Log slightly differently if the key itself is unknown vs. if loading failed
        if language_key not in LANGUAGES:
             logger.warning(f"Tree-sitter parser for language '{language_key}' not available (language never loaded or key unknown).")
        else:
             logger.warning(f"Tree-sitter parser for language '{language_key}' not available (failed to create parser instance during load).")

    return parser

def get_language(language_key: str) -> Optional[Language]:
    """Gets the tree-sitter Language object for a given language key."""
    if not TS_CORE_AVAILABLE:
        logger.debug("get_language: Tree-sitter core not available.") # DEBUG
        return None
    language = LANGUAGES.get(language_key)
    if language is None:
         # Be slightly more specific in warning
         if language_key in PARSERS: # If parser exists but language doesn't, something's weird
             logger.error(f"Inconsistency: Parser exists for '{language_key}' but Language object is None.")
         else:
             logger.warning(f"Tree-sitter language object for '{language_key}' not available or failed to load.")
    return language
