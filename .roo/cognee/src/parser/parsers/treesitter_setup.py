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

def _load_language(lang_name: str, lang_module: LanguageModuleInput):
    """Helper function to load a single tree-sitter language."""
    logger.info(f"Attempting to load language '{lang_name}'...") # Add entry log

    if not TS_CORE_AVAILABLE:
        logger.warning(f"Skipping load for '{lang_name}': Core library not available.")
        print(f"DEBUG: EXITING _load_language for '{lang_name}' because TS_CORE_AVAILABLE is False") # FORCE PRINT
        return # EXIT POINT 1

    if lang_module is None:
        logger.warning(f"Skipping load for '{lang_name}': Language binding module not provided or import failed.")
        print(f"DEBUG: EXITING _load_language for '{lang_name}' because lang_module is None") # FORCE PRINT
        return # EXIT POINT 2

    logger.debug(f"Proceeding with loading tree-sitter language: {lang_name}")
    try:
        language_callable = None
        # ... (logic to find callable remains the same) ...
        if hasattr(lang_module, 'language') and callable(lang_module.language):
            language_callable = lang_module.language
            logger.debug(f"Found language callable via attribute '.language' for {lang_name}")
        elif lang_name == "typescript" and hasattr(lang_module, 'language_typescript') and callable(lang_module.language_typescript):
             language_callable = lang_module.language_typescript
             logger.debug(f"Found language callable via attribute '.language_typescript' for {lang_name}")
        else:
             logger.error(f"Could not find language callable for {lang_name} using known patterns. Module type: {type(lang_module)}")
             print(f"DEBUG: EXITING _load_language for '{lang_name}' because language callable not found") # FORCE PRINT
             return # EXIT POINT 3

        if not language_callable:
             logger.error(f"Unexpected: Failed to resolve language callable for {lang_name} after checks.")
             print(f"DEBUG: EXITING _load_language for '{lang_name}' because language callable resolved to None") # FORCE PRINT
             return # EXIT POINT 4

        # --- Call the language function ---
        logger.debug(f"Calling language function for {lang_name}...")
        language_raw = language_callable()
        logger.debug(f"Called language function for {lang_name}, type of result: {type(language_raw)}")

        # --- Use Language() constructor ---
        language_obj = Language(language_raw) # This might trigger DeprecationWarning
        logger.debug(f"Created Language object for {lang_name}, type: {type(language_obj)}")


        if not isinstance(language_obj, Language):
            logger.error(f"CRITICAL TYPE MISMATCH for '{lang_name}': Expected tree_sitter.Language, but got {type(language_obj)}. Storing failed.")
            print(f"DEBUG: EXITING _load_language for '{lang_name}' due to Language object type mismatch") # FORCE PRINT
            return # EXIT POINT 5

        # --- Store Language and Parser ---
        LANGUAGES[lang_name] = language_obj
        parser = Parser()
        # --- MODIFIED: Add try-except around set_language ---
        try:
            parser.set_language(language_obj) # Use the recommended way
            logger.debug(f"Set language for {lang_name} parser successfully.")
        except AttributeError:
             logger.error(f"Parser object for {lang_name} does not have 'set_language'. Trying assignment.")
             try:
                 parser.language = language_obj # Fallback assignment (older API?)
                 logger.debug(f"Assigned language for {lang_name} parser successfully.")
             except Exception as assign_e:
                 logger.error(f"Failed to assign language for {lang_name} parser: {assign_e}", exc_info=True)
                 # Decide if you should clear LANGUAGES entry or not? Maybe remove it.
                 del LANGUAGES[lang_name]
                 print(f"DEBUG: EXITING _load_language for '{lang_name}' because failed to assign language to parser") # FORCE PRINT
                 return # EXIT POINT 6 (Failed to set language)

        PARSERS[lang_name] = parser
        logger.info(f"Successfully created and stored Language/Parser for: {lang_name}") # Changed level to INFO
        print(f"DEBUG: SUCCESS loading language '{lang_name}'") # FORCE PRINT <<< Added success print

    except AttributeError as ae:
        logger.error(f"AttributeError processing language binding for '{lang_name}': {ae}.", exc_info=True)
        if lang_name in LANGUAGES: del LANGUAGES[lang_name] # Clean up on error
        print(f"DEBUG: EXITING _load_language for '{lang_name}' due to AttributeError: {ae}") # FORCE PRINT
        return # EXIT POINT 7
    except Exception as e:
        tb_str = traceback.format_exc()
        logger.error(f"Detailed error loading language '{lang_name}': {e}\n{tb_str}")
        if lang_name in LANGUAGES: del LANGUAGES[lang_name] # Clean up on error
        print(f"DEBUG: EXITING _load_language for '{lang_name}' due to Exception: {e}") # FORCE PRINT
        return # EXIT POINT 8


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
