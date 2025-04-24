# src/parser/config.py
import os

# --- Chunking Configuration ---
CHUNK_SIZE = 100
CHUNK_OVERLAP = 15

# --- File Discovery Configuration ---
# Files/Dirs to ignore completely
IGNORED_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "venv",
    ".venv",
    "target", # For Rust
    ".next", # For Next.js builds
    ".vscode", # VSCode specific files
    ".idea", # JetBrains specific files
    "coverage", # Coverage reports
    "logs",
    "tmp",
    "temp",
}
IGNORED_FILES = {
    ".DS_Store",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.so", # Shared objects
    "*.dll", # Windows dynamic libraries
    "*.o", # Object files
    "*.a", # Static libraries
    "*.swp", # Vim swap files
    "*.swo", # Vim swap files
    "*.log", # Log files (can be noisy)
    "package-lock.json", # Often very large and less useful for parsing
    "yarn.lock", # Often very large and less useful for parsing
    "pnpm-lock.yaml", # Often very large and less useful for parsing
    "poetry.lock", # Often very large and less useful for parsing
    "uv.lock", # Often very large and less useful for parsing
}

# Supported extensions and their assigned parser type keys
# These keys MUST match the keys used in the PARSER_MAP in orchestrator.py
SUPPORTED_EXTENSIONS = {
    # Code (Mapped to specific language keys)
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".rs": "rust",
    # Styles (Mapped to 'css' key)
    ".css": "css",
    # Config/Infra (Mapped to 'dockerfile' key)
    "Dockerfile": "dockerfile", # Match exact filename
    ".dockerfile": "dockerfile",
    # Docs (Mapped to 'markdown' key)
    ".md": "markdown",
    ".mdx": "markdown",
    # Add others and map to unique keys matching parser classes
    # e.g., ".java": "java", ".go": "go", ".rb": "ruby", ".html": "html"
}
