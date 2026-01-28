# Zero-Events Debugging - Quick Reference

## Problem
Timeline reconstruction builds with 0 events and silently returns success.

## Solution
Three layers of instrumentation added:

### Layer 1: Application Logging (rag/timeline.py)
- Detailed logs at each step with structured tags
- Tracks metadata → session → fetches → merge → final
- Shows event counts at each stage

**Key Log Patterns:**
```
[METADATA] Detected: year=..., gp_name=..., session_type=...
[CLIENT] OpenF1 client type: MockOpenF1Client
[SESSION] Querying... [SUCCESS] Found N sessions
[FETCH] Fetching X... > N items
[TOTAL OPENF1] N events extracted
[FINAL SUMMARY] PDF=A, OpenF1=B, Merged=C, Final=D
```

### Layer 2: UI Error Handling (ui_gradio.py)
- Explicit check for 0 events after build
- Returns error message with actionable causes
- Never displays success for empty timeline

**Error Message Shown:**
```
❌ FAILED: Timeline build returned 0 events.
Possible causes:
1. GP name not found in OpenF1 database
2. OpenF1 endpoint returned no data
3. Session resolution failed
```

### Layer 3: Debug Panel (ui_gradio.py)
- Shows event count and type breakdown
- Displays PDF vs OpenF1 evidence counts
- Warns if 0 events with debugging hints

**Panel Shows:**
```
🔍 OpenF1 Debug Info:
Events: 3 total | YELLOW=1, PIT=2
Sources: PDF=0, OpenF1=3
```

## Diagnosing Issues

### 1. Check UI First
- If 0 events: ❌ FAILED message with causes
- If error: Check cause 1, 2, or 3 in order

### 2. Check Application Logs
Search for these patterns:

**Session Not Found:**
```
[FAIL] Could not match OpenF1 session for 2025 Australian Grand Prix
→ Check GP name spelling
```

**Session Found but No Events:**
```
[SUCCESS] Session resolution found 1 session
[FETCH] Fetching race control... > 0 items
[FETCH] Fetching pit stops... > 0 items
→ OpenF1 endpoints returned no data
```

**Mixed Data (PDF + OpenF1):**
```
[STEP 1/4] PDF events... > 2
[STEP 2/4] OpenF1 events... > 5
[STEP 3/4] Merged timeline... > 6
[STEP 4/4] Final timeline... > 5
→ 1 event removed during dedup
```

### 3. Detailed Flow Analysis

**Complete Success Path:**
```
[METADATA] year=2025, gp_name=Australian Grand Prix, session_type=RACE
[CLIENT] OpenF1 client type: MockOpenF1Client
[SESSION] Querying... [SUCCESS] Found 1 session
[0] session_id=xyz, gp_name=Australian Grand Prix, date=2025-03-28
[FETCH] Race control... > 1 item
[FETCH] Pit stops... > 1 item
[FETCH] Stints... > 1 item
[FETCH] Lap markers... > 0 items
[FETCH] Position changes... > 0 items
[TOTAL OPENF1] 3 events extracted
✅ Timeline built with 3 events
```

**Failure Path 1 - Bad GP Name:**
```
[METADATA] year=2025, gp_name=Unknown, session_type=RACE
[FAIL] Cannot resolve OpenF1 session: gp_name is 'Unknown'
❌ FAILED: Timeline build returned 0 events
  Cause 1: GP name not found in OpenF1 database ← CHECK THIS
```

**Failure Path 2 - Session Not Found:**
```
[METADATA] year=2025, gp_name=Typo Grand Prix, session_type=RACE
[SESSION] Querying... 
[FAIL] Could not match OpenF1 session for 2025 Typo Grand Prix
❌ FAILED: Timeline build returned 0 events
  Cause 1: GP name not found in OpenF1 database ← CHECK THIS
```

**Failure Path 3 - Empty Endpoints:**
```
[METADATA] year=2025, gp_name=Australian Grand Prix, session_type=RACE
[SESSION] Querying... [SUCCESS] Found 1 session
[FETCH] Race control... > 0 items
[FETCH] Pit stops... > 0 items
[FETCH] Stints... > 0 items
[FETCH] Lap markers... > 0 items
[FETCH] Position changes... > 0 items
[WARNING] OpenF1 returned 0 events
❌ FAILED: Timeline build returned 0 events
  Cause 2: OpenF1 endpoint returned no data ← CHECK THIS
```

## Files Modified

**rag/timeline.py** (943 lines)
- build_openf1_timeline(): Added comprehensive logging
- build_race_timeline(): Added step-by-step tracking
- _extract_race_control_events(): Added fetch logging

**ui_gradio.py** (1258 lines)
- get_openf1_debug_info(): NEW - Creates debug panel
- build_timeline_gradio(): Added zero-event check
- build_click(): Integrated debug panel

**openf1/api.py** (unchanged)
- No modifications needed

## Testing

Run test to verify instrumentation:
```bash
python test_openf1_debug.py
```

Expected output shows complete flow with all log tags and final summary.

## Log Tags Reference

| Tag | Meaning | Example |
|-----|---------|---------|
| [METADATA] | PDF metadata detected | year=2025, gp_name=Australian |
| [CLIENT] | Client type | MockOpenF1Client or RealOpenF1Client |
| [SESSION] | Session query starting | Querying OpenF1... |
| [SUCCESS] | Session found | Found 1 session(s) |
| [FAIL] | Session not found | Could not match OpenF1 session |
| [FETCH] | Fetch operation | Fetching race control events |
| [TOTAL OPENF1] | Total from OpenF1 | 3 events extracted |
| [STEP N/4] | Pipeline step | Extract PDF, Build OpenF1, Merge, Impact |
| [WARNING] | Non-fatal issue | OpenF1 returned 0 events |
| [ERROR] | Exception/failure | Exception building OpenF1 timeline |
| [FINAL SUMMARY] | Results aggregated | PDF=0, OpenF1=3, Merged=3, Final=3 |

## Key Improvements

✅ **Before**: Silent failure with 0 events, no visibility
✅ **After**: Explicit errors + detailed logs + debug panel

✅ **Before**: No way to diagnose where events disappear  
✅ **After**: Count tracking at 4 stages (PDF, OpenF1, Merged, Final)

✅ **Before**: Users confused by empty timeline
✅ **After**: Clear error message with actionable causes

## Next Steps if Still 0 Events

1. Verify PDF metadata extraction (check [METADATA] logs)
2. Verify GP name spelling (check session resolution)
3. Verify OpenF1 endpoint is reachable (check [FETCH] results)
4. Check OpenF1 website directly for this race/session
5. Contact OpenF1 if endpoints are down
