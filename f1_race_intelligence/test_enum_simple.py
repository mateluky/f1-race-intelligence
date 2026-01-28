#!/usr/bin/env python3
"""Verify Enum serialization produces actual strings."""

from rag.schemas import TimelineEventType
from rag.app_service import make_json_serializable

# Direct test
enum_val = TimelineEventType.YELLOW_FLAG
result = make_json_serializable(enum_val)
print(f'Result type: {type(result)}')
print(f'Result value: {result}')
print(f'Result repr: {repr(result)}')
print(f'Is string: {isinstance(result, str)}')
print(f'Equals YELLOW: {result == "YELLOW"}')
