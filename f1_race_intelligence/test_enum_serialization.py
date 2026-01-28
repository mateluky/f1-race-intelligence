#!/usr/bin/env python3
"""Quick test to verify Enum serialization works correctly."""

from rag.schemas import TimelineEventType
from rag.app_service import make_json_serializable
import json

# Test 1: Direct Enum
print("[TEST 1] Direct Enum serialization")
enum_obj = TimelineEventType.YELLOW_FLAG
print(f"  Input: {enum_obj} (type: {type(enum_obj).__name__})")
result = make_json_serializable(enum_obj)
print(f"  Output: {result} (type: {type(result).__name__})")
is_str = isinstance(result, str)
print(f"  {'✓ PASS' if is_str else '✗ FAIL'}: Result is string: {is_str}")

# Test 2: Enum in dict
print("\n[TEST 2] Enum inside dict")
data = {"event_type": TimelineEventType.PACE_CHANGE}
print(f"  Input event_type type: {type(data['event_type']).__name__}")
result = make_json_serializable(data)
print(f"  Output event_type: {result['event_type']} (type: {type(result['event_type']).__name__})")
is_str = isinstance(result["event_type"], str)
print(f"  {'✓ PASS' if is_str else '✗ FAIL'}: Result value is string: {is_str}")

# Test 3: Enum in list
print("\n[TEST 3] Enum inside list")
data = [TimelineEventType.PIT_STOP, TimelineEventType.SAFETY_CAR]
print(f"  Input types: {[type(x).__name__ for x in data]}")
result = make_json_serializable(data)
print(f"  Output types: {[type(x).__name__ for x in result]}")
print(f"  Output values: {result}")
all_strings = all(isinstance(x, str) for x in result)
print(f"  {'✓ PASS' if all_strings else '✗ FAIL'}: All results are strings: {all_strings}")

# Test 4: Enum in nested structure
print("\n[TEST 4] Enum in nested dict/list")
data = {
    "events": [
        {"type": TimelineEventType.YELLOW_FLAG, "lap": 5},
        {"type": TimelineEventType.INCIDENT, "lap": 10}
    ]
}
result = make_json_serializable(data)
print(f"  Output types: {[type(e['type']).__name__ for e in result['events']]}")
print(f"  Output values: {[e['type'] for e in result['events']]}")
all_strings = all(isinstance(e["type"], str) for e in result["events"])
print(f"  {'✓ PASS' if all_strings else '✗ FAIL'}: All event types are strings: {all_strings}")

# Test 5: JSON serializable
print("\n[TEST 5] Full JSON serialization")
data = {"events": [{"type": TimelineEventType.YELLOW_FLAG}]}
result = make_json_serializable(data)
try:
    json_str = json.dumps(result)
    print(f"  ✓ PASS: Successfully serialized to JSON")
    print(f"  JSON: {json_str}")
except Exception as e:
    print(f"  ✗ FAIL: JSON serialization failed: {e}")

print("\n[SUMMARY] Enum serialization test completed")
