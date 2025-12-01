"""Serialization utilities for JSON compatibility."""

import json
import numpy as np
from typing import Any
from datetime import datetime


def json_serialize_safe(obj: Any) -> Any:
    """Convert object to JSON-serializable format.

    Handles numpy types, datetime objects, and nested structures
    that cannot be directly serialized by the json module.

    Args:
        obj: Object to convert to JSON-serializable format

    Returns:
        JSON-serializable version of the object
    """
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: json_serialize_safe(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [json_serialize_safe(item) for item in obj]
    else:
        return obj


def safe_json_dumps(obj: Any, **kwargs) -> str:
    """Safe JSON serialization that handles numpy types.

    Args:
        obj: Object to serialize
        **kwargs: Additional arguments passed to json.dumps()

    Returns:
        JSON string representation of the object
    """
    return json.dumps(json_serialize_safe(obj), **kwargs)