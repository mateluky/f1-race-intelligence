#!/usr/bin/env python3
"""Understand the OpenF1 API structure - sessions vs meetings."""

import requests
import json

print("Exploring OpenF1 API structure...\n")

base_url = "https://api.openf1.org/v1"

# Get one session from 2024
print("1. Getting a session from 2024:")
resp = requests.get(f"{base_url}/sessions", params={"year": 2024}, timeout=5)
sessions = resp.json()
if sessions:
    session = sessions[0]
    print(json.dumps(session, indent=2))
    meeting_key = session.get('meeting_key')
    
    if meeting_key:
        print(f"\n2. Getting meeting with key {meeting_key}:")
        resp = requests.get(f"{base_url}/meetings", params={"meeting_key": meeting_key}, timeout=5)
        meetings = resp.json()
        if meetings:
            meeting = meetings[0]
            print(json.dumps(meeting, indent=2)[:500])
            print("\n... (truncated)")
