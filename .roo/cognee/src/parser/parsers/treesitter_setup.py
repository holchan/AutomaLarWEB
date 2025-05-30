import os
import traceback
from typing import Dict, Any, Optional
from ..utils import logger

try: import tree_sitter_python as tspython
except ImportError: tspython = None; logger.debug("tree_sitter_python binding not found.")
try: import tree_sitter_javascript as tsjavascript
except ImportError: tsjavascript = None; logger.debug("tree_sitter_javascript binding not found.")
try: import tree_sitter_typescript.language_typescript as tstypescript_lang
except ImportError:
    try: import tree_sitter_typescript as tstypescript_module
    except ImportError: tstypescript_module = None; logger.debug("tree_sitter_typescript binding package not found.")
    else: tstypescript_lang = getattr(tstypescript_module, 'language_typescript', None) if tstypescript_module else None
else: tstypescript_module = None

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
    Language = Any
    Parser = Any

LANGUAGES: Dict[str, Language] = {}
PARSERS: Dict[str, Parser] = {}

LanguageModuleInput = Optional[Any]

def _load_language(lang_name: str, lang_module_or_entry_point: LanguageModuleInput):
    if not TS_CORE_AVAILABLE:
        logger.debug(f"Skipping load for '{lang_name}': Core library not available.")
        return

    language_entry_point = None
    if lang_module_or_entry_point is None:
        logger.debug(f"Skipping load for '{lang_name}': Language binding module/entry point not provided or import failed.")
        return

    logger.info(f"Attempting to load tree-sitter language: {lang_name}")
    try:
        if callable(lang_module_or_entry_point):
            language_entry_point = lang_module_or_entry_point
        elif hasattr(lang_module_or_entry_point, 'language') and callable(getattr(lang_module_or_entry_point, 'language')):
            language_entry_point = getattr(lang_module_or_entry_point, 'language')
        elif lang_name == "typescript" and tstypescript_module and hasattr(tstypescript_module, 'language_typescript') and callable(getattr(tstypescript_module, 'language_typescript')):
             language_entry_point = getattr(tstypescript_module, 'language_typescript')


        if not language_entry_point:
            logger.error(f"Could not find language entry point for {lang_name} in the provided module.")
            return

        language_obj = language_entry_point()

        if not isinstance(language_obj, Language):
             try:
                 wrapped_language_obj = Language(language_obj)
                 if isinstance(wrapped_language_obj, Language):
                     language_obj = wrapped_language_obj
                 else:
                    logger.error(f"Loading '{lang_name}' failed: Expected tree_sitter.Language, got {type(language_obj)} after direct call and after wrapping.")
                    return
             except Exception as wrap_e:
                logger.error(f"Loading '{lang_name}' failed during Language wrapping: {wrap_e}. Original type was {type(language_obj)}.")
                return


        LANGUAGES[lang_name] = language_obj
        parser = Parser()
        parser.language = language_obj
        PARSERS[lang_name] = parser
        logger.info(f"Successfully loaded and configured Language/Parser for: {lang_name}")

    except Exception as e:
        tb_str = traceback.format_exc()
        logger.error(f"Unexpected error loading language '{lang_name}': {e}\n{tb_str}")

logger.info("Loading available tree-sitter languages...")
_load_language("python", tspython)
_load_language("javascript", tsjavascript)
_load_language("typescript", tstypescript_lang if tstypescript_lang else tstypescript_module)
_load_language("c", tsc)
_load_language("cpp", tscpp)
_load_language("rust", tsrust)
logger.info("Finished attempting to load tree-sitter languages.")

def get_parser(language_key: str) -> Optional[Parser]:
    if not TS_CORE_AVAILABLE: return None
    return PARSERS.get(language_key)

def get_language(language_key: str) -> Optional[Language]:
    if not TS_CORE_AVAILABLE: return None
    return LANGUAGES.get(language_key)
