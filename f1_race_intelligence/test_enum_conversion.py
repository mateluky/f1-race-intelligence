#!/usr/bin/env python3
"""Test different ways to convert string enum to pure string."""

from rag.schemas import TimelineEventType

enum_obj = TimelineEventType.YELLOW_FLAG
print(f"Original: {enum_obj} (type: {type(enum_obj)})")
print(f"obj.value: {enum_obj.value} (type: {type(enum_obj.value)})")
print(f"str(obj.value): {str(enum_obj.value)} (type: {type(str(enum_obj.value))})")
print(f"%s format: {'%s' % enum_obj.value} (type: {type('%s' % enum_obj.value)})")

# Try explicit conversion
result = str(enum_obj.value)
print(f"\nresult = str(enum_obj.value)")
print(f"type(result): {type(result)}")
print(f"isinstance(result, str): {isinstance(result, str)}")
print(f"result == 'YELLOW': {result == 'YELLOW'}")

# Check if it's truly a string or still an enum-like thing
import json
try:
    json.dumps({"value": result})
    print("✓ JSON serializable")
except:
    print("✗ NOT JSON serializable")
