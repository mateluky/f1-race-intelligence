#!/usr/bin/env python3
"""Test timeline with Gradio dataframe conversion."""

import json
import logging
from rag.app_service import AppService
from ui_gradio import format_timeline_for_table

logging.basicConfig(level=logging.WARNING)

# Create AppService with mock
app_service = AppService(use_mock=True)

# Simulate an ingested document
doc_id = "test_gradio"
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
print("\n=== Building Timeline for Gradio ===\n")
result = app_service.build_timeline(
    doc_id=doc_id,
    auto_extract_metadata=True
)

print(f"Success: {result['success']}")
print(f"Event count: {result.get('event_count', 0)}")

if result['success']:
    timeline = result.get('timeline', {})
    
    # Convert to table format (as Gradio would)
    print("\n=== Converting to Table Format ===")
    rows = format_timeline_for_table(timeline)
    print(f"Table rows: {len(rows)}")
    
    if rows:
        # Check for problematic types
        print("\nChecking row values for Gradio compatibility:")
        for i, row in enumerate(rows):
            print(f"\nRow {i}:")
            for key, value in row.items():
                value_type = type(value).__name__
                is_valid = isinstance(value, (str, int, float, bool, list, type(None)))
                status = "✓" if is_valid else "✗ INVALID"
                print(f"  {key}: {value_type} {status}")
                if isinstance(value, (tuple, dict)) or value_type == 'tuple':
                    print(f"    ERROR: Found {value_type}: {value}")
        
        # Try to serialize to JSON (simulating what Gradio does)
        print("\n=== Testing JSON Serialization ===")
        try:
            json_str = json.dumps(rows, indent=2)
            print("✓ Successfully converted to JSON")
            print(f"JSON length: {len(json_str)} characters")
        except TypeError as e:
            print(f"✗ JSON serialization failed: {e}")
    
else:
    print(f"Error: {result.get('error', 'Unknown error')}")

print("\n✓ Test complete!")
