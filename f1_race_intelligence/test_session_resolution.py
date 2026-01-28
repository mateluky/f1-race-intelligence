#!/usr/bin/env python3
"""Test the improved session resolution with fallback logic."""

import sys
sys.path.insert(0, '.')

from openf1.api import OpenF1Client
from rag.timeline import TimelineBuilder
from rag.llm import MockLLM

# Create mock LLM
llm = MockLLM()

# Create timeline builder
builder = TimelineBuilder(None, llm)

# Create real OpenF1 client
client = OpenF1Client()

# Test session resolution with different year/gp combinations
test_cases = [
    {"year": 2025, "gp_name": "Bahrain Grand Prix", "session_type": "RACE"},  # Latest - might not exist
    {"year": 2024, "gp_name": "Bahrain Grand Prix", "session_type": "RACE"},  # Known good year
    {"year": 2023, "gp_name": "Bahrain Grand Prix", "session_type": "RACE"},  # Previous year
]

print("="*70)
print("Testing Session Resolution with Fallback Logic")
print("="*70)

for i, metadata in enumerate(test_cases):
    print(f"\n[Test {i+1}] Searching for: {metadata['year']} {metadata['gp_name']} ({metadata['session_type']})")
    print("-"*70)
    
    try:
        # This will test the search_sessions method directly
        sessions = client.search_sessions(
            year=metadata['year'],
            gp_name=metadata['gp_name'],
            session_type=metadata['session_type']
        )
        
        if sessions:
            print(f"✓ Found {len(sessions)} session(s):")
            for sess in sessions:
                print(f"  - {sess.get('gp_name')} ({sess.get('session_type')}) - ID: {sess.get('session_id')}")
        else:
            print(f"✗ No sessions found")
            
            # Try fallback
            print(f"  → Trying fallback (without session type)...")
            fallback = client.search_sessions(year=metadata['year'], gp_name=metadata['gp_name'])
            if fallback:
                print(f"  ✓ Fallback found {len(fallback)} session(s):")
                for sess in fallback:
                    print(f"    - {sess.get('gp_name')} ({sess.get('session_type')}) - ID: {sess.get('session_id')}")
    except Exception as e:
        print(f"✗ Error: {e}")

print("\n" + "="*70)
