#!/usr/bin/env python3
"""Test what .value returns for string enums."""

from rag.schemas import TimelineEventType

enum_obj = TimelineEventType.YELLOW_FLAG
print(f"enum_obj: {enum_obj}")
print(f"type(enum_obj): {type(enum_obj)}")
print(f"enum_obj.value: {enum_obj.value}")
print(f"type(enum_obj.value): {type(enum_obj.value)}")
print(f"isinstance(enum_obj, str): {isinstance(enum_obj, str)}")
print(f"isinstance(enum_obj.value, str): {isinstance(enum_obj.value, str)}")

# The problem: enum_obj IS a string already since TimelineEventType(str, Enum)
# So we need to cast it explicitly to str
print(f"\nstr(enum_obj): {str(enum_obj)}")
print(f"type(str(enum_obj)): {type(str(enum_obj))}")
