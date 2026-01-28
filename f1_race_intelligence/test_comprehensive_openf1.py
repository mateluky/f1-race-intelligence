#!/usr/bin/env python3
"""Comprehensive test of OpenF1 session resolution and timeline building."""

import sys
import logging
sys.path.insert(0, '.')

logging.basicConfig(level=logging.INFO, format='[%(name)s] %(message)s')

from openf1.api import OpenF1Client
from rag.timeline import TimelineBuilder
from rag.llm import MockLLM

print("="*70)
print("COMPREHENSIVE OPENF1 INTEGRATION TEST")
print("="*70)

# 1. Test OpenF1 client directly
print("\n[STEP 1] Testing OpenF1 Client")
print("-"*70)
client = OpenF1Client()
sessions = client.search_sessions(year=2024, gp_name="Bahrain Grand Prix", session_type="RACE")
print(f"✓ Found {len(sessions)} session(s) for 2024 Bahrain RACE")
if sessions:
    sess = sessions[0]
    print(f"  Session Key: {sess.get('session_key')}")
    print(f"  Location: {sess.get('location')}, {sess.get('country_name')}")
    print(f"  Type: {sess.get('session_type')}")

# 2. Test session resolution in TimelineBuilder
print("\n[STEP 2] Testing Session Resolution in TimelineBuilder")
print("-"*70)
llm = MockLLM()
builder = TimelineBuilder(None, llm)

session_metadata = {
    "year": 2024,
    "gp_name": "Bahrain Grand Prix",
    "session_type": "RACE"
}

# Simulate the session resolution logic
logger = logging.getLogger("rag.timeline")
test_sessions = client.search_sessions(
    year=session_metadata['year'],
    gp_name=session_metadata['gp_name'],
    session_type=session_metadata['session_type']
)

if test_sessions:
    print(f"✓ Session resolution successful!")
    print(f"  Found {len(test_sessions)} matching session(s)")
    session = test_sessions[0]
    session_id = session.get('session_key')
    print(f"  Using session_key: {session_id}")
    
    # 3. Test fetching race control data
    print("\n[STEP 3] Testing Race Control Data Fetch")
    print("-"*70)
    try:
        rc_data = client.get_race_control_messages(session_id)
        print(f"✓ Fetched {len(rc_data)} race control message(s)")
        if rc_data:
            for i, msg in enumerate(rc_data[:3]):
                print(f"  [{i}] {msg.get('category', 'N/A')} - {msg.get('message', '')[:50]}")
    except Exception as e:
        print(f"⚠ Could not fetch race control: {e}")
    
    # 4. Test fetching pit stop data
    print("\n[STEP 4] Testing Pit Stop Data Fetch")
    print("-"*70)
    try:
        pit_data = client.get_pit_stops(session_id)
        print(f"✓ Fetched {len(pit_data)} pit stop record(s)")
        if pit_data:
            unique_drivers = len(set([p.get('driver_number') for p in pit_data]))
            print(f"  Pit stops by {unique_drivers} unique driver(s)")
    except Exception as e:
        print(f"⚠ Could not fetch pit stops: {e}")
    
    # 5. Test fallback for non-existent year
    print("\n[STEP 5] Testing Fallback for 2025 (if available)")
    print("-"*70)
    sessions_2025 = client.search_sessions(year=2025, gp_name="Bahrain Grand Prix", session_type="RACE")
    if sessions_2025:
        print(f"✓ 2025 Bahrain data available: {len(sessions_2025)} session(s)")
    else:
        print(f"⚠ 2025 Bahrain data not found (may not be released yet)")
else:
    print("✗ Session resolution failed - could not find matching session")

print("\n" + "="*70)
print("TEST COMPLETE")
print("="*70)
