#!/usr/bin/env python3
"""Quick test to see if 2025 has F1 data in OpenF1."""

import sys
import logging
sys.path.insert(0, '.')

# Set up logging to show what's happening
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from openf1.api import OpenF1Client

client = OpenF1Client()

print("Checking F1 seasons available in OpenF1...\n")

# Test years
for year in [2024, 2025, 2026]:
    print(f"Year {year}:")
    try:
        sessions = client.search_sessions(year=year)
        print(f"  Total sessions: {len(sessions)}")
        
        if sessions:
            # Count Bahrain
            bahrain = [s for s in sessions if 'bahrain' in s.get('gp_name', '').lower()]
            if bahrain:
                print(f"  Bahrain: Found {len(bahrain)} session(s)")
                for b in bahrain:
                    print(f"    - {b.get('session_type')}: {b.get('session_id')}")
            else:
                print(f"  Bahrain: Not found")
            
            # Show first 2 GPs
            print(f"  Sample GPs:")
            for sess in sessions[:2]:
                print(f"    - {sess.get('gp_name')}")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()
