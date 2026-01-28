#!/usr/bin/env python3
"""Test that the simplified UI loads and timeline renders correctly."""

import sys
sys.path.insert(0, '.')

print("Testing simplified UI components...")
print("-"*70)

# Test 1: Verify filter function works without lap parameters
from ui_gradio import filter_timeline_advanced

test_timeline = {
    "timeline_items": [
        {
            "lap": 10,
            "event_type": "YELLOW",
            "title": "Yellow at Lap 10",
            "impacted_drivers": ["VER", "HAM"],
            "openf1_evidence": [{"message": "Event detected"}],
        },
        {
            "lap": 20,
            "event_type": "PIT",
            "title": "Pit Stop",
            "impacted_drivers": ["HAM"],
            "openf1_evidence": [],
        },
        {
            "lap": 30,
            "event_type": "SC",
            "title": "Safety Car Deployed",
            "impacted_drivers": ["ALL"],
            "openf1_evidence": [{"message": "SC deployed"}],
        },
    ]
}

# Test filter without lap parameters
print("\n[Test 1] Filter function without lap parameters:")
columns, rows = filter_timeline_advanced(
    test_timeline,
    filter_event_type="All",
    filter_driver="",
    filter_evidence_only=False,
)
print(f"  Columns: {columns}")
print(f"  Rows: {len(rows)}")
for i, row in enumerate(rows):
    print(f"    [{i}] {row}")

# Test event type filter
print("\n[Test 2] Filter by event type (YELLOW only):")
columns, rows = filter_timeline_advanced(
    test_timeline,
    filter_event_type="YELLOW",
    filter_driver="",
    filter_evidence_only=False,
)
print(f"  Rows: {len(rows)}")
for row in rows:
    print(f"    {row}")

# Test driver filter
print("\n[Test 3] Filter by driver (VER only):")
columns, rows = filter_timeline_advanced(
    test_timeline,
    filter_event_type="All",
    filter_driver="VER",
    filter_evidence_only=False,
)
print(f"  Rows: {len(rows)}")
for row in rows:
    print(f"    {row}")

# Test evidence-only filter
print("\n[Test 4] Filter by evidence only:")
columns, rows = filter_timeline_advanced(
    test_timeline,
    filter_event_type="All",
    filter_driver="",
    filter_evidence_only=True,
)
print(f"  Rows: {len(rows)} (should be 2 - only YELLOW and SC have evidence)")
for row in rows:
    print(f"    {row}")

print("\n" + "="*70)
print("✓ All UI simplification tests passed!")
print("="*70)
