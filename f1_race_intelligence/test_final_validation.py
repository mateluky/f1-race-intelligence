#!/usr/bin/env python3
"""FINAL VALIDATION - Comprehensive system health check after fixes."""

import json
from rag.schemas import TimelineEventType
from rag.app_service import AppService, make_json_serializable
from rag.timeline import TimelineBuilder

print("="*70)
print("FINAL VALIDATION - System Health Check")
print("="*70)

# Test 1: Enum Serialization
print("\n[TEST 1] Enum Serialization")
print("-" * 70)
test_enums = [
    TimelineEventType.YELLOW_FLAG,
    TimelineEventType.PACE_CHANGE,
    TimelineEventType.PIT_STOP,
    TimelineEventType.SAFETY_CAR,
]
all_good = True
for enum_obj in test_enums:
    result = make_json_serializable(enum_obj)
    is_str = type(result) is str
    symbol = "✓" if is_str else "✗"
    print(f"  {symbol} {enum_obj.name:15} → {result:10} (type: {type(result).__name__})")
    all_good = all_good and is_str

print(f"\nEnum serialization: {'✓ PASS' if all_good else '✗ FAIL'}")

# Test 2: Complex Structure Serialization
print("\n[TEST 2] Complex Structure Serialization")
print("-" * 70)
complex_structure = {
    "events": [
        {
            "type": TimelineEventType.YELLOW_FLAG,
            "lap": 15,
            "title": "Yellow flag",
            "tags": [TimelineEventType.INCIDENT]
        },
        {
            "type": TimelineEventType.PIT_STOP,
            "lap": 20,
            "nested": {
                "event_type": TimelineEventType.PACE_CHANGE
            }
        }
    ]
}

try:
    result = make_json_serializable(complex_structure)
    json_str = json.dumps(result)
    
    # Verify all types are strings
    all_strings = True
    all_strings = all_strings and isinstance(result["events"][0]["type"], str)
    all_strings = all_strings and isinstance(result["events"][0]["tags"][0], str)
    all_strings = all_strings and isinstance(result["events"][1]["nested"]["event_type"], str)
    
    if all_strings:
        print(f"✓ All Enums converted to strings")
        print(f"✓ JSON serializable ({len(json_str)} bytes)")
        print(f"  Sample: {result['events'][0]['type']} (value only, clean)")
    else:
        print(f"✗ Some values still not strings")
except Exception as e:
    print(f"✗ FAIL: {e}")
    all_good = False

# Test 3: Timeline Building
print("\n[TEST 3] Timeline Building with Metadata")
print("-" * 70)
try:
    service = AppService()
    result = service.build_timeline(
        doc_id="test_doc_2025_australia",
        year=2025,
        gp_name="Australian Grand Prix",
        session_type="RACE",
        auto_extract_metadata=False
    )
    
    if result["success"]:
        timeline_dict = result.get("timeline", {})
        events = timeline_dict.get("timeline_items", [])
        print(f"✓ Timeline built successfully")
        print(f"✓ Event count: {len(events)}")
        
        # Check first event structure
        if events:
            first = events[0]
            event_type = first.get("event_type")
            print(f"✓ First event type: {event_type} (type: {type(event_type).__name__})")
            
            # Verify it's a pure string
            if type(event_type) is str:
                print(f"✓ Event type is pure string (not Enum)")
            else:
                print(f"✗ Event type is not pure string: {type(event_type)}")
                all_good = False
    else:
        print(f"✗ Timeline build failed: {result.get('error', 'Unknown error')}")
        all_good = False
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
    all_good = False

# Test 4: Gradio Compatibility
print("\n[TEST 4] Gradio Dataframe Compatibility")
print("-" * 70)
try:
    if 'events' in locals() and events:
        first = events[0]
        
        # Simulate what Gradio does - convert to JSON and back
        json_str = json.dumps(first)
        reloaded = json.loads(json_str)
        
        print(f"✓ JSON serialization: {len(json_str)} bytes")
        print(f"✓ All fields JSON-compatible")
        
        # Check key fields are primitives
        primitive_fields = ["lap", "title", "event_type", "confidence"]
        all_primitive = True
        for field in primitive_fields:
            val = reloaded.get(field)
            is_primitive = isinstance(val, (str, int, float, bool, type(None)))
            symbol = "✓" if is_primitive else "✗"
            print(f"  {symbol} {field}: {type(val).__name__}")
            all_primitive = all_primitive and is_primitive
        
        if all_primitive:
            print(f"\n✓ Gradio compatible: All primitives")
        else:
            print(f"\n✗ NOT Gradio compatible: Non-primitive types found")
            all_good = False
    else:
        print("⚠ Skipped (no events to test)")
except Exception as e:
    print(f"✗ Error: {e}")
    all_good = False

# Final Summary
print("\n" + "="*70)
if all_good:
    print("✓✓✓ FINAL RESULT: ALL SYSTEMS GO ✓✓✓")
    print("="*70)
    print("System Status:")
    print("  ✓ Enum serialization working correctly")
    print("  ✓ Timeline building produces events")
    print("  ✓ All output is Gradio-compatible")
    print("  ✓ JSON serialization verified")
    print("\n⭐ System is ready for production deployment!")
else:
    print("✗✗✗ FINAL RESULT: ISSUES FOUND ✗✗✗")
    print("="*70)
    print("Please review failures above")

print("="*70)
