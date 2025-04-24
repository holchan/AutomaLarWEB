import asyncio
from typing import List, Dict
from .utils import helper_func # Example relative import

class DataProcessor:
    """Processes data asynchronously."""

    DEFAULT_TIMEOUT = 10

    def __init__(self, source: str):
        self.source = source
        self._data: List[Dict] = []

    async def load_data(self):
        """Loads data from the source."""
        print(f"Loading from {self.source}")
        await asyncio.sleep(0.1) # Simulate I/O
        self._data = [{"id": 1, "value": "A"}, {"id": 2, "value": "B"}]

    async def process(self) -> int:
        if not self._data:
            await self.load_data()
        count = 0
        for item in self._data:
            # Use helper
            processed_value = helper_func(item.get("value"))
            print(f"Processed item {item.get('id')}: {processed_value}")
            count += 1
        return count

# Example usage (usually not in the class file itself)
async def main():
    processor = DataProcessor("http://example.com/data")
    result = await processor.process()
    print(f"Processed {result} items.")
