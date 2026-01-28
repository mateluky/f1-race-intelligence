#!/usr/bin/env python3
"""Debug timeline dict structure after build."""

from rag.app_service import AppService
from rag.schemas import RaceMetadata

# Simulate metadata
metadata = RaceMetadata(
    year=2025,
    gp_name="Australian Grand Prix", 
    session_type="RACE"
)

service = AppService()
print("Building timeline...")
result = service.build_timeline(metadata)
print(f"\nResult success: {result.success}")
print(f"Result message: {result.message}")

if result.data:
    timeline_dict = result.data
    print(f"\nTimeline dict keys: {timeline_dict.keys()}")
    items = timeline_dict.get("timeline_items", [])
    print(f"Timeline items count: {len(items)}")
    
    if items:
        first_item = items[0]
        print(f"\nFirst item keys: {first_item.keys()}")
        print(f"First item event_type: {first_item.get('event_type')}")
        print(f"First item event_type type: {type(first_item.get('event_type'))}")
        print(f"First item repr: {repr(first_item.get('event_type'))}")

