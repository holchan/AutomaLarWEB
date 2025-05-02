# src/parser/config.py
import os

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100

IGNORED_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "venv",
    ".venv",
    "target",
    ".next",
    ".vscode",
    ".idea",
    "coverage",
    "logs",
    "tmp",
    "temp",
    "data",
    ".ruff_cache",
    ".mypy_cache",
}
IGNORED_FILES = {
    ".DS_Store",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.so",
    "*.dll",
    "*.o",
    "*.a",
    "*.swp",
    "*.swo",
    "*.log",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "uv.lock",
}

SUPPORTED_EXTENSIONS = {
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
    ".css": "css",
    "Dockerfile": "dockerfile",
    ".dockerfile": "dockerfile",
    ".md": "markdown",
    ".mdx": "markdown",
}
