# A simple function example
import os
import logging

logger = logging.getLogger(__name__)

def process_data(file_path: str) -> bool:
    """
    Reads data from a file and processes it.
    Just a dummy function for testing.
    """
    if not os.path.exists(file_path):
        logger.error("File not found")
        return False
    # Simulate processing
    print(f"Processing {file_path}")
    return True

# End of file
