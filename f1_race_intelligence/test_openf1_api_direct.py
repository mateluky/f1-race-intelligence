#!/usr/bin/env python3
"""Test OpenF1 API directly to see what formats work."""

import requests
import json

print("Testing OpenF1 API directly...\n")

base_url = "https://api.openf1.org/v1"

# Try different endpoint formats
endpoints = [
    "/sessions",
    "/drivers",
]

params_list = [
    {"year": 2024},
    {},
]

for endpoint in endpoints:
    print(f"Endpoint: {endpoint}")
    for params in params_list:
        url = f"{base_url}{endpoint}"
        print(f"  Params: {params}")
        try:
            response = requests.get(url, params=params, timeout=5)
            print(f"    Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    print(f"    Result: {len(data)} items")
                    if data:
                        print(f"    Sample: {json.dumps(data[0], indent=2)[:200]}...")
                else:
                    print(f"    Result: {json.dumps(data, indent=2)[:200]}...")
            else:
                print(f"    Error: {response.text[:100]}")
        except Exception as e:
            print(f"    Exception: {e}")
    print()
