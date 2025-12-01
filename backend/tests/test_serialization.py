"""
Comprehensive tests for JSON serialization utility.
"""

import json
import numpy as np
import pytest
from datetime import datetime
from typing import Any, Dict, List
from utils.serialization import json_serialize_safe, safe_json_dumps


class TestJSONSerialization:
    """Test suite for JSON serialization utilities."""

    def test_basic_types(self):
        """Test serialization of basic JSON-compatible types."""
        # Test basic types
        assert json_serialize_safe(None) is None
        assert json_serialize_safe(True) is True
        assert json_serialize_safe(False) is False
        assert json_serialize_safe(42) == 42
        assert json_serialize_safe(3.14) == 3.14
        assert json_serialize_safe("hello") == "hello"

    def test_numpy_types(self):
        """Test serialization of numpy types."""
        # Test numpy integers
        np_int = np.int32(42)
        assert json_serialize_safe(np_int) == 42
        assert isinstance(json_serialize_safe(np_int), int)

        np_int64 = np.int64(100)
        assert json_serialize_safe(np_int64) == 100
        assert isinstance(json_serialize_safe(np_int64), int)

        # Test numpy floats
        np_float = np.float32(3.14)
        result = json_serialize_safe(np_float)
        assert isinstance(result, float)
        assert abs(result - 3.14) < 1e-6  # Allow for float32 precision

        np_float64 = np.float64(2.718281828)
        result = json_serialize_safe(np_float64)
        assert isinstance(result, float)
        assert abs(result - 2.718281828) < 1e-10  # Float64 has better precision

        # Test numpy arrays
        np_array_1d = np.array([1, 2, 3])
        assert json_serialize_safe(np_array_1d) == [1, 2, 3]
        assert isinstance(json_serialize_safe(np_array_1d), list)

        np_array_2d = np.array([[1, 2], [3, 4]])
        assert json_serialize_safe(np_array_2d) == [[1, 2], [3, 4]]
        assert isinstance(json_serialize_safe(np_array_2d), list)

        # Test complex numpy array
        np_array_complex = np.array([1.1, 2.2, 3.3], dtype=np.float32)
        result = json_serialize_safe(np_array_complex)
        assert len(result) == 3
        assert all(isinstance(x, float) for x in result)
        # Check with tolerance for float32 precision
        for expected, actual in zip([1.1, 2.2, 3.3], result):
            assert abs(expected - actual) < 1e-6

    def test_datetime_serialization(self):
        """Test serialization of datetime objects."""
        # Test datetime
        dt = datetime(2025, 1, 1, 12, 0, 0)
        result = json_serialize_safe(dt)
        assert result == "2025-01-01T12:00:00"
        assert isinstance(result, str)

        # Test datetime with microseconds
        dt_micro = datetime(2025, 1, 1, 12, 0, 0, 123456)
        result = json_serialize_safe(dt_micro)
        assert result == "2025-01-01T12:00:00.123456"

    def test_nested_structures(self):
        """Test serialization of nested dictionaries and lists."""
        # Test nested dictionary with numpy types
        nested_dict = {
            "int_val": np.int32(42),
            "float_val": np.float64(3.14),
            "array_val": np.array([1, 2, 3]),
            "nested": {
                "deep_int": np.int64(100),
                "deep_array": np.array([[1, 2], [3, 4]]),
                "normal_str": "hello"
            },
            "list_val": [np.int32(1), np.float32(2.2), "normal"]
        }

        result = json_serialize_safe(nested_dict)

        # Check types and structure
        assert isinstance(result["int_val"], int)
        assert isinstance(result["float_val"], float)
        assert isinstance(result["array_val"], list)
        assert isinstance(result["nested"]["deep_int"], int)
        assert isinstance(result["list_val"][0], int)
        assert isinstance(result["list_val"][1], float)

        # Check integer values
        assert result["int_val"] == 42
        assert result["nested"]["deep_int"] == 100
        assert result["list_val"][0] == 1

        # Check float values with tolerance
        assert abs(result["float_val"] - 3.14) < 1e-10
        assert abs(result["list_val"][1] - 2.2) < 1e-6

        # Check array and string values
        assert result["array_val"] == [1, 2, 3]
        assert result["nested"]["deep_array"] == [[1, 2], [3, 4]]
        assert result["nested"]["normal_str"] == "hello"
        assert result["list_val"][2] == "normal"

    def test_list_and_tuple_serialization(self):
        """Test serialization of lists and tuples."""
        # Test list with mixed types
        mixed_list = [1, "hello", np.float32(3.14), [np.int32(42), np.array([1, 2])]]
        result = json_serialize_safe(mixed_list)

        # Check types and structure
        assert result[0] == 1
        assert result[1] == "hello"
        assert isinstance(result[2], float)
        assert abs(result[2] - 3.14) < 1e-6  # Float32 precision tolerance
        assert result[3] == [42, [1, 2]]

        # Test tuple (should be converted to list)
        test_tuple = (1, np.int32(2), "hello")
        result = json_serialize_safe(test_tuple)
        expected = [1, 2, "hello"]
        assert result == expected
        assert isinstance(result, list)  # Tuple becomes list

    def test_complex_nested_structure(self):
        """Test serialization of a complex nested structure."""
        complex_data = {
            "metadata": {
                "timestamp": datetime(2025, 1, 1, 12, 0, 0),
                "version": "1.0.0",
                "metrics": {
                    "accuracy": np.float32(0.95),
                    "precision": np.float64(0.87),
                    "recall": np.float32(0.92),
                    "loss_history": np.array([0.5, 0.4, 0.3, 0.2, 0.1])
                }
            },
            "predictions": [
                {
                    "id": np.int32(1),
                    "confidence": np.float64(0.98),
                    "bbox": np.array([10, 20, 30, 40]),
                    "features": np.array([0.1, 0.2, 0.3, 0.4, 0.5])
                },
                {
                    "id": np.int32(2),
                    "confidence": np.float32(0.87),
                    "bbox": np.array([15, 25, 35, 45]),
                    "features": np.array([0.6, 0.7, 0.8, 0.9, 1.0])
                }
            ],
            "statistics": {
                "total_predictions": np.int64(2),
                "avg_confidence": np.float64(0.925),
                "processing_time": np.float32(1.23)
            }
        }

        result = json_serialize_safe(complex_data)

        # Verify structure and types
        assert isinstance(result["metadata"]["timestamp"], str)
        assert result["metadata"]["timestamp"] == "2025-01-01T12:00:00"
        assert isinstance(result["metadata"]["metrics"]["accuracy"], float)
        assert abs(result["metadata"]["metrics"]["accuracy"] - 0.95) < 1e-6  # Float32 precision
        assert isinstance(result["metadata"]["metrics"]["loss_history"], list)
        assert result["metadata"]["metrics"]["loss_history"] == [0.5, 0.4, 0.3, 0.2, 0.1]

        assert isinstance(result["predictions"][0]["id"], int)
        assert result["predictions"][0]["id"] == 1
        assert isinstance(result["predictions"][0]["confidence"], float)
        assert result["predictions"][0]["bbox"] == [10, 20, 30, 40]

        assert isinstance(result["statistics"]["total_predictions"], int)
        assert result["statistics"]["total_predictions"] == 2
        assert isinstance(result["statistics"]["avg_confidence"], float)

    def test_edge_cases(self):
        """Test edge cases and special values."""
        # Test infinity and nan (these should remain as numpy types for now)
        inf_val = np.float64(np.inf)
        nan_val = np.float64(np.nan)

        # Note: json.dumps() will fail on inf/nan, but our function should pass them through
        # and let json.dumps handle the error
        result_inf = json_serialize_safe(inf_val)
        assert result_inf == inf_val

        result_nan = json_serialize_safe(nan_val)
        assert result_nan != result_nan  # NaN comparison

        # Test empty structures
        assert json_serialize_safe([]) == []
        assert json_serialize_safe({}) == {}
        assert json_serialize_safe(np.array([])) == []

    def test_safe_json_dumps_function(self):
        """Test the safe_json_dumps convenience function."""
        # Test basic usage
        data = {"number": np.int32(42), "text": "hello"}
        result_str = safe_json_dumps(data)
        parsed = json.loads(result_str)

        assert parsed["number"] == 42
        assert parsed["text"] == "hello"

        # Test with custom JSON arguments
        data = {"array": np.array([1, 2, 3]), "nested": {"value": np.float64(3.14)}}
        result_str = safe_json_dumps(data, indent=2)
        parsed = json.loads(result_str)

        assert parsed["array"] == [1, 2, 3]
        assert parsed["nested"]["value"] == 3.14
        # Check that formatting was applied (contains newlines and indentation)
        assert "\n" in result_str
        assert "  " in result_str

    def test_serialization_roundtrip(self):
        """Test that data survives serialization->deserialization roundtrip."""
        original_data = {
            "numpy_int": np.int32(42),
            "numpy_float": np.float64(3.14159),
            "numpy_array": np.array([1, 2, 3, 4.5]),
            "datetime": datetime(2025, 1, 1, 12, 0, 0),
            "nested": {
                "deep_numpy": np.float32(2.718),
                "deep_array": np.array([[1, 2], [3, 4]]),
                "normal_data": "hello world"
            },
            "list_with_numpy": [np.int64(1), np.float32(2.2), "normal"]
        }

        # Serialize and deserialize
        serialized = safe_json_dumps(original_data)
        deserialized = json.loads(serialized)

        # Check that non-numeric data is preserved
        assert deserialized["datetime"] == "2025-01-01T12:00:00"
        assert deserialized["nested"]["normal_data"] == "hello world"
        assert deserialized["list_with_numpy"][2] == "normal"

        # Check that numeric values are correctly converted
        assert deserialized["numpy_int"] == 42
        assert abs(deserialized["numpy_float"] - 3.14159) < 1e-10
        assert deserialized["numpy_array"] == [1, 2, 3, 4.5]
        assert abs(deserialized["nested"]["deep_numpy"] - 2.718) < 1e-6  # Float32 precision
        assert deserialized["nested"]["deep_array"] == [[1, 2], [3, 4]]
        assert deserialized["list_with_numpy"][0] == 1
        assert abs(deserialized["list_with_numpy"][1] - 2.2) < 1e-6  # Float32 precision

    def test_error_handling(self):
        """Test that the function handles problematic inputs gracefully."""
        # Test with object that should be passed through unchanged
        class CustomObject:
            def __init__(self, value):
                self.value = value

        custom_obj = CustomObject("test")
        result = json_serialize_safe(custom_obj)
        assert result is custom_obj  # Should pass through unchanged

        # Test with recursive structure (should handle without infinite recursion)
        recursive_dict = {}
        recursive_dict["self"] = recursive_dict

        # This should either handle gracefully or raise a clear error
        # Our implementation should handle this by processing each level once
        try:
            result = json_serialize_safe(recursive_dict)
            # If successful, the result should be JSON-serializable
            json.dumps(result)
        except (RecursionError, ValueError):
            # If it fails, it should fail with a clear error
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])