#!/usr/bin/env python3
"""Test to verify detailed OpenF1 debugging and logging."""

import logging
import sys

# Configure logging to show all levels including DEBUG
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)-8s | %(name)s | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('timeline_debug.log')
    ]
)

from rag.app_service import AppService

print("="*80)
print("TIMELINE DEBUGGING TEST - OpenF1 Event Extraction")
print("="*80)

# Initialize service
service = AppService()

print("\n[TEST] Building timeline for 2025 Australian Grand Prix...")
result = service.build_timeline(
    doc_id="test_australia_2025",
    year=2025,
    gp_name="Australian Grand Prix",
    session_type="RACE",
    auto_extract_metadata=False
)

print("\n" + "="*80)
print("RESULT SUMMARY")
print("="*80)
print(f"Success: {result.get('success')}")
print(f"Message: {result.get('message')}")

if result.get('timeline'):
    timeline = result.get('timeline')
    items = timeline.get('timeline_items', [])
    print(f"Timeline events: {len(items)}")
    
    if items:
        print(f"\nEvent types:")
        for item in items:
            print(f"  - {item.get('event_type')}: {item.get('title')}")
else:
    print("Timeline is None or empty")

print("\n[LOG] Check 'timeline_debug.log' for full debugging output")
print("="*80)
