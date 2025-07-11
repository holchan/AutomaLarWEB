import os

QUIESCENCE_PERIOD_SECONDS = 60
BATCH_SIZE_LLM_ENHANCEMENT = 20

GENERIC_CHUNK_SIZE = 1000
GENERIC_CHUNK_OVERLAP = 100

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    "__pycache__",
    "node_modules",
    "vendor",
    "build",
    "dist",
    "target",
    "out",
    "bin",
    "obj",
    "venv",
    ".venv",
    "env",
    ".env",
    "logs",
    "tmp",
    "temp",
    "coverage",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "site-packages",
    "*.egg-info",
    "docs/_build",
    "site",
    ".serverless",
    ".terraform",
    "__pypackages__"
}

IGNORED_FILES = {
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.so",
    "*.dll",
    "*.o",
    "*.a",
    "*.obj",
    "*.lib",
    "*.class",
    "*.jar",
    "*.war",
    "*.ear",
    "*.log",
    "*.swp",
    "*.swo",
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",
    "Pipfile.lock",
    "Gemfile.lock",
    "composer.lock",
    "go.sum",
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.lock",
    "*.bak",
    "*.tmp",
    "*.temp",
    "*~",
}

SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java", # Placeholder - parser needed
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp", # Placeholder - parser needed
    ".go": "go", # Placeholder - parser needed
    ".php": "php", # Placeholder - parser needed
    ".rs": "rust",
    ".sh": "shell", # Placeholder - parser needed
    ".ps1": "powershell",# Placeholder - parser needed
    ".css": "css",
    "Dockerfile": "dockerfile",
    ".dockerfile": "dockerfile",
    ".html": "html", # Placeholder - parser needed
    ".xml": "xml", # Placeholder - parser needed
    ".json": "json", # Placeholder - parser needed
    ".yaml": "yaml", # Placeholder - parser needed
    ".yml": "yaml", # Placeholder - parser needed
    ".md": "markdown",
    ".mdx": "markdown",
    ".txt": "text",
    ".sql": "sql",
}
