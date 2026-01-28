#!/usr/bin/env python3
"""Test full make_json_serializable flow."""

from rag.schemas import TimelineEventType
from rag.app_service import make_json_serializable
import json

# Test 1: Direct enum
print("[TEST 1] Direct Enum")
enum_obj = TimelineEventType.YELLOW_FLAG
result = make_json_serializable(enum_obj)
print(f"  Input type: {type(enum_obj)}")
print(f"  Output: {result}")
print(f"  Output type: {type(result)}")
print(f"  Is pure string: {isinstance(result, str) and type(result).__name__ == 'str'}")

# Test 2: Dict with enum
print("\n[TEST 2] Dict with Enum")
data = {"event_type": TimelineEventType.YELLOW_FLAG}
result = make_json_serializable(data)
print(f"  Input event_type: {data['event_type']} (type: {type(data['event_type'])})")
print(f"  Output event_type: {result['event_type']} (type: {type(result['event_type'])})")
print(f"  Is pure string: {isinstance(result['event_type'], str) and type(result['event_type']).__name__ == 'str'}")

# Test 3: JSON serialization
print("\n[TEST 3] JSON Serialization")
data = {"events": [{"type": TimelineEventType.YELLOW_FLAG}]}
result = make_json_serializable(data)
try:
    json_str = json.dumps(result)
    print(f"  ✓ JSON successful: {json_str}")
except Exception as e:
    print(f"  ✗ JSON failed: {e}")

# Test 4: Check actual type name
print("\n[TEST 4] Type Name Check")
result = make_json_serializable(TimelineEventType.YELLOW_FLAG)
print(f"  type(result): {type(result)}")
print(f"  type(result).__name__: {type(result).__name__}")
print(f"  type(result).__module__: {type(result).__module__}")
print(f"  Is <class 'str'>: {type(result) is str}")
