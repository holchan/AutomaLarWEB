# Main Document Title

This is the introductory paragraph. It explains the purpose of this document.

## Section 1: Setup

Here are the steps for setting up the environment:

1.  Install Python 3.9+.
2.  Create a virtual environment: `python -m venv .venv`
3.  Activate it: `source .venv/bin/activate` (Linux/macOS) or `.venv\Scripts\activate` (Windows)
4.  Install dependencies: `pip install -r requirements.txt`

```python
# Example code block
import os

def check_path(p):
    print(f"Checking: {p}")
    return os.path.exists(p)

```

## Section 2: Usage

To run the main script:

```bash
python main_script.py --input data.csv
```

See `main_script.py --help` for more options.

### Subsection 2.1: Advanced Options

- `--verbose`: Enable detailed logging.
- `--output <file>`: Specify output file.

This section provides further details.
