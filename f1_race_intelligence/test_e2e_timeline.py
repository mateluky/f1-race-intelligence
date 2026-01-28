#!/usr/bin/env python3
"""End-to-end test: metadata extraction → timeline building → Gradio table conversion."""

import json
import logging
from rag.app_service import AppService
from ui_gradio import format_timeline_for_table

# Suppress logging for clean output
logging.disable(logging.CRITICAL)

print("=" * 70)
print("END-TO-END TIMELINE TEST")
print("=" * 70)

# Create AppService
app_service = AppService(use_mock=True)

# Create realistic PDF content
doc_id = "test_e2e_2025_aus"
filename = "2025_Australian_Grand_Prix.pdf"
raw_text = """
FORMULA 1 - 2025 AUSTRALIAN GRAND PRIX
Melbourne, Albert Park Circuit
RACE REPORT - March 16, 2025

The 2025 Australian Grand Prix was held at Albert Park in Melbourne.
The RACE featured intense competition and multiple strategic decisions.

Key Events:
- Lap 10: First safety car deployment
- Lap 15: Yellow flag in sector 1
- Lap 22: Multiple pit stops
- Lap 35: Red flag situation
- Lap 45: Final stint changes
"""

# Prepare chunks
chunks = [
    {'id': f'{doc_id}_chunk_{i}', 'document_id': doc_id, 'content': line.strip(), 
     'chunk_index': i, 'metadata': {}}
    for i, line in enumerate(raw_text.split('\n')) if line.strip()
]

app_service.ingested_docs[doc_id] = {
    'text': raw_text,
    'raw_text': raw_text[:2000],
    'filename': filename,
    'chunks': chunks,
    'num_chunks': len(chunks),
}

print("\n[STEP 1] Metadata Extraction")
print("-" * 70)

# Extract metadata
metadata_result = app_service.extract_race_metadata(doc_id)
year = metadata_result['year']
gp_name = metadata_result['gp_name']
session_type = metadata_result['session_type']

print(f"✓ Year: {year}")
print(f"✓ GP Name: {gp_name}")
print(f"✓ Session Type: {session_type}")
print(f"✓ Extraction Path: {metadata_result.get('extraction_path', 'unknown')}")

assert year == 2025, f"Expected 2025, got {year}"
assert "Australian" in gp_name, f"Expected 'Australian' in GP name, got {gp_name}"
assert session_type == "RACE", f"Expected RACE, got {session_type}"

print("\n[STEP 2] Timeline Building")
print("-" * 70)

# Build timeline
timeline_result = app_service.build_timeline(
    doc_id=doc_id,
    auto_extract_metadata=True
)

assert timeline_result['success'], f"Timeline build failed: {timeline_result.get('error')}"

event_count = timeline_result.get('event_count', 0)
print(f"✓ Success: {timeline_result['success']}")
print(f"✓ Event Count: {event_count}")
print(f"✓ Message: {timeline_result['message']}")

assert event_count > 0, "Timeline should have events"

print("\n[STEP 3] Table Conversion")
print("-" * 70)

timeline = timeline_result.get('timeline', {})
rows = format_timeline_for_table(timeline)

print(f"✓ Table rows: {len(rows)}")

# Validate table format
for i, row in enumerate(rows):
    for key, value in row.items():
        value_type = type(value).__name__
        is_valid = isinstance(value, (str, int, float, bool, list, type(None)))
        assert is_valid, f"Row {i} {key} has invalid type {value_type}: {value}"

print(f"✓ All {len(rows)} rows have valid Gradio types")

# Test JSON serialization
try:
    json_str = json.dumps(rows)
    print(f"✓ JSON serialization: {len(json_str)} bytes")
except TypeError as e:
    raise AssertionError(f"JSON serialization failed: {e}")

print("\n[STEP 4] Sample Output")
print("-" * 70)

if rows:
    print("\nFirst event:")
    first_row = rows[0]
    for key, value in first_row.items():
        print(f"  {key}: {value}")

print("\n" + "=" * 70)
print("✓ ALL TESTS PASSED!")
print("=" * 70)
print("\nSummary:")
print(f"  • Metadata: {year} {gp_name} ({session_type})")
print(f"  • Timeline Events: {event_count}")
print(f"  • Table Rows: {len(rows)}")
print(f"  • Gradio Compatible: Yes ✓")
print("\nThe system is ready for production use!")
