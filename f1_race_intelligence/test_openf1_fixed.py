#!/usr/bin/env python3
"""Test improved OpenF1 session resolution."""

import sys
import logging
sys.path.insert(0, '.')

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

from openf1.api import OpenF1Client

client = OpenF1Client()

print("="*70)
print("Test 1: Search for 2024 Bahrain RACE")
print("="*70)
sessions = client.search_sessions(year=2024, gp_name="Bahrain Grand Prix", session_type="RACE")
print(f"Result: {len(sessions)} session(s)")
if sessions:
    for sess in sessions:
        print(f"  - Location: {sess.get('location')}")
        print(f"    Country: {sess.get('country_name')}")
        print(f"    Type: {sess.get('session_type')}")
        print(f"    Key: {sess.get('session_key')}")

print("\n" + "="*70)
print("Test 2: Search for 2024 Bahrain (any session type)")
print("="*70)
sessions = client.search_sessions(year=2024, gp_name="Bahrain Grand Prix")
print(f"Result: {len(sessions)} session(s)")
for sess in sessions:
    print(f"  - {sess.get('session_type')} (key: {sess.get('session_key')})")

print("\n" + "="*70)
print("Test 3: Search for 2025 Bahrain (might fail)")
print("="*70)
sessions = client.search_sessions(year=2025, gp_name="Bahrain Grand Prix", session_type="RACE")
print(f"Result: {len(sessions)} session(s)")
if sessions:
    for sess in sessions:
        print(f"  - {sess.get('location')} ({sess.get('session_type')})")
else:
    print("  No sessions found - this is expected if 2025 data isn't available yet")
