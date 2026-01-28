#!/usr/bin/env python3
"""Debug timeline build and data structure."""

import json
import logging
from rag.app_service import AppService

logging.basicConfig(level=logging.INFO)

# Create AppService with mock
app_service = AppService(use_mock=True)

# Simulate an ingested document
doc_id = "test_debug"
filename = "2025_Australian_Grand_Prix.pdf"
raw_text = """
FORMULA 1 AUSTRALIAN GRAND PRIX 2025
Melbourne, Albert Park Circuit
Race Report - Round 1 of the 2025 Season

This report covers the 2025 Australian Grand Prix held at Albert Park in Melbourne.
The RACE took place on Sunday, March 16, 2025.

Key events during the race included:
- Safety car deployment on lap 15 due to debris
- Multiple pit stops for tire changes
- Red flag at lap 25
- Close battle between Hamilton and Verstappen for the lead
"""

# Create mock chunks
chunks = []
for i, line in enumerate(raw_text.split('\n')):
    if line.strip():
        chunks.append({
            'id': f'{doc_id}_chunk_{i}',
            'document_id': doc_id,
            'content': line,
            'chunk_index': i,
            'metadata': {}
        })

# Store in app_service
app_service.ingested_docs[doc_id] = {
    'text': raw_text,
    'raw_text': raw_text[:2000],
    'filename': filename,
    'chunks': chunks,
    'num_chunks': len(chunks),
}

# Build timeline
print("\n=== Building Timeline ===\n")
result = app_service.build_timeline(
    doc_id=doc_id,
    auto_extract_metadata=True
)

print(f"Success: {result['success']}")
print(f"Event count: {result.get('event_count', 0)}")
print(f"Message: {result.get('message', '')}")

if result['success']:
    timeline = result.get('timeline', {})
    items = timeline.get('timeline_items', [])
    print(f"\nTimeline items: {len(items)}")
    
    if items:
        # Print first item with full detail
        first = items[0]
        print(f"\nFirst item structure:")
        print(f"  Keys: {list(first.keys())}")
        for key, value in first.items():
            print(f"  {key}: {type(value).__name__}")
            if isinstance(value, (list, dict)):
                print(f"    Content sample: {str(value)[:100]}")
            else:
                print(f"    Value: {value}")
        
        # Check for tuples anywhere
        def find_tuples(obj, path=""):
            if isinstance(obj, tuple):
                print(f"FOUND TUPLE at {path}: {obj}")
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    find_tuples(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    find_tuples(v, f"{path}[{i}]")
        
        print("\nSearching for tuples in timeline...")
        for i, item in enumerate(items):
            find_tuples(item, f"items[{i}]")
        
        print("\nTimeline JSON (first 1000 chars):")
        print(json.dumps(timeline, indent=2)[:1000])
else:
    print(f"Error: {result.get('error', 'Unknown error')}")
