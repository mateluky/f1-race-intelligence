#!/usr/bin/env python3
"""Test 2-stage metadata extraction with real AppService."""

import logging
from rag.app_service import AppService
from rag.ingest import Chunk

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create AppService
app_service = AppService(use_mock=True)  # Use mock LLM to avoid needing real Ollama

# Simulate an ingested document
doc_id = "test_2025_aus"
filename = "2025_Australian_Grand_Prix.pdf"
raw_text = """
FORMULA 1 AUSTRALIAN GRAND PRIX 2025
Melbourne, Albert Park Circuit
Race Report - Round 1 of the 2025 Season

This report covers the 2025 Australian Grand Prix held at Albert Park in Melbourne.
The RACE took place on Sunday, March 16, 2025.

Key events during the race included safety car deployments and multiple pit stops.
"""

# Create mock chunks
chunks = []
for i, line in enumerate(raw_text.split('\n')):
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

# Test extraction
print("\n=== Testing 2-Stage Metadata Extraction ===\n")
result = app_service.extract_race_metadata(doc_id)

print(f"Success: {result['success']}")
print(f"Year: {result['year']}")
print(f"GP Name: {result['gp_name']}")
print(f"Session Type: {result['session_type']}")
print(f"Message: {result['message']}")
print(f"Extraction Path: {result.get('extraction_path', 'unknown')}")
print(f"Reasoning: {result.get('reasoning', 'N/A')}")

# Verify results
assert result['success'], "Extraction should succeed"
assert result['year'] == 2025, f"Year should be 2025, got {result['year']}"
assert "Australian" in result['gp_name'], f"GP name should contain 'Australian', got {result['gp_name']}"
assert result['session_type'] == 'RACE', f"Session should be RACE, got {result['session_type']}"
assert result['gp_name'] != 'Unknown', f"GP name should not be 'Unknown'"

print("\n✓ All assertions passed! 2-stage extraction working correctly.")
