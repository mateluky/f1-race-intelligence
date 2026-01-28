#!/usr/bin/env python3
"""Debug make_json_serializable type checking."""

from rag.schemas import TimelineEventType
from enum import Enum

enum_obj = TimelineEventType.YELLOW_FLAG
print(f"enum_obj: {enum_obj}")
print(f"type(enum_obj): {type(enum_obj)}")
print(f"isinstance(enum_obj, Enum): {isinstance(enum_obj, Enum)}")
print(f"isinstance(enum_obj, str): {isinstance(enum_obj, str)}")
print(f"isinstance(enum_obj, bool): {isinstance(enum_obj, bool)}")
print(f"isinstance(enum_obj, int): {isinstance(enum_obj, int)}")
print(f"isinstance(enum_obj, float): {isinstance(enum_obj, float)}")
print(f"isinstance(enum_obj, (str, int, float)): {isinstance(enum_obj, (str, int, float))}")

# So the problem is: TimelineEventType inherits from (str, Enum)
# isinstance(enum_obj, str) returns True!
# So the check isinstance(obj, (str, int, float)) matches first!
print("\n=== THE PROBLEM ===")
print("TimelineEventType(str, Enum) means:")
print(f"isinstance(obj, str) = True (so it returns early, before Enum check)")
print(f"isinstance(obj, Enum) = True (but never reached)")
