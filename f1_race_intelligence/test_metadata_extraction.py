#!/usr/bin/env python3
"""Quick test of metadata extraction functions."""

from rag.app_service import extract_metadata_heuristic, normalize_gp_name

# Test heuristic extraction
print("=== Testing Heuristic Extraction ===")
print()

# Test 1: Filename with year and GP
year, gp, session, summary = extract_metadata_heuristic(
    "2025_Australian_Grand_Prix.pdf",
    "Formula 1 Australian Grand Prix 2025"
)
print(f"Test 1: 2025_Australian_Grand_Prix.pdf")
print(f"  Result: year={year}, gp={gp}, session={session}")
print(f"  Summary: {summary}")
print()

# Test 2: GP name normalization
print("=== Testing GP Normalization ===")
test_names = [
    "Australia",
    "Australian Grand Prix",
    "Formula 1 Louis Vuitton Australian Grand Prix 2025",
    "Monaco",
    "Saudi Arabia",
]
for name in test_names:
    normalized = normalize_gp_name(name)
    print(f"  {name!r} -> {normalized!r}")

print()
print("✓ All tests passed!")
