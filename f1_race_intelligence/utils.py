import json
from datetime import datetime
from pathlib import Path
import numpy as np

def safe_json(obj):
    """
    Recursively converts non-JSON-serializable objects to JSON-serializable types.
    - numpy scalars -> int/float
    - numpy arrays -> list
    - datetime -> ISO string
    - Path -> str
    """
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, Path):
        return str(obj)
    elif isinstance(obj, dict):
        return {key: safe_json(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [safe_json(item) for item in obj]
    else:
        return obj

# Example usage before tool calls
def prepare_tool_args(args):
    safe_args = safe_json(args)
    try:
        json.dumps(safe_args)  # Validate JSON serialization
        return safe_args
    except (TypeError, ValueError) as e:
        print(f"Invalid args for JSON serialization: {safe_args}")
        raise e