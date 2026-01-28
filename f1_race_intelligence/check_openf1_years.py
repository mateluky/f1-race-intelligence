#!/usr/bin/env python3
"""Check what years and sessions are available in OpenF1 API."""

import sys
sys.path.insert(0, '/c/Users/lukac/Documents/Egyetem/EIT Digital/Nice/Text Mining and NLP/f1_race_intelligence')

from openf1.api import OpenF1Client

client = OpenF1Client()

# Try to fetch sessions for multiple years
for year in [2024, 2025, 2026]:
    print(f"\n{'='*60}")
    print(f"Sessions for Year {year}")
    print('='*60)
    try:
        sessions = client.search_sessions(year=year)
        print(f"Total sessions for {year}: {len(sessions)}")
        
        if sessions:
            for i, sess in enumerate(sessions[:5]):  # Show first 5
                print(f"  [{i}] {sess.get('gp_name')} | {sess.get('session_type')} | {sess.get('session_date')}")
            
            # Look for Bahrain specifically
            bahrain = [s for s in sessions if 'bahrain' in s.get('gp_name', '').lower()]
            if bahrain:
                print(f"\n  → Found {len(bahrain)} Bahrain session(s):")
                for sess in bahrain:
                    print(f"    - {sess.get('gp_name')} ({sess.get('session_type')}) - {sess.get('session_id')}")
            else:
                print(f"\n  → No Bahrain sessions found")
    except Exception as e:
        print(f"ERROR: {e}")

print("\n" + "="*60)
