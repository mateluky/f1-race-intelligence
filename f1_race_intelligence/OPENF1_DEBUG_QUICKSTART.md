# OpenF1 Evidence Debug - Quick Start

## The Problem
Timeline table shows "OpenF1:0" for every event, even though OpenF1 should be providing data.

## The Solution
Three-layer debugging system:

### Layer 1: Client Type Check
**What it shows**: Whether you're using real OpenF1 API or mock client

**Where to find it**:
- Application logs: `[OpenF1] Client type: OpenF1Client` (or MockOpenF1Client)
- UI debug panel: "Client Type: OpenF1Client"

**What to do**:
- If `MockOpenF1Client`: You're in test/demo mode, won't reach real OpenF1 API
- If `OpenF1Client`: Real API is being used

### Layer 2: Session Resolution Debug
**What it shows**: Whether OpenF1 can find the race session

**Where to find it**:
- Application logs:
  ```
  [METADATA] Detected: year=2025, gp_name=Australian Grand Prix, session_type=RACE
  [SESSION] Querying OpenF1 sessions...
  [SUCCESS] Session resolution found 1 session(s)
    [0] session_id=2025_AUS_R, gp_name=Australian Grand Prix, ...
  ```
- UI debug panel: Shows session_id found or "Session NOT Found"

**What to do**:
- If "Session Found": Session resolution worked ✓
- If "Session NOT Found": 
  - Check GP name spelling
  - Verify year is correct
  - Check if race has occurred on OpenF1.com

### Layer 3: Endpoint Data Counts
**What it shows**: How many events each OpenF1 endpoint returned

**Where to find it**:
- Application logs:
  ```
  [FETCH] Fetching race control events...
    > Race control events: 3
  [FETCH] Fetching pit stop events...
    > Pit events: 2
  [FETCH] Fetching stint events...
    > Stint events: 5
  ```

**What to do**:
- If all counts are 0: OpenF1 has no data for this session
- If some counts > 0: Endpoints are working, data is available

### Layer 4: Evidence in Timeline Table
**What it shows**: Evidence counts for each timeline event

**Where to find it**:
- Table "Evidence" column shows: `PDF:X | OpenF1:Y`
  - `PDF:0 | OpenF1:1` = Event from OpenF1 ✓
  - `PDF:1 | OpenF1:0` = Event from PDF ✓
  - `PDF:1 | OpenF1:1` = Event from both (merged) ✓

**What to do**:
- If seeing `OpenF1:0` everywhere: Check layers 1-3 above
- If seeing `OpenF1:1+`: Data flow is working! ✓

## Troubleshooting

### Symptom: "OpenF1:0" everywhere
**Diagnosis**:
1. Check Layer 1: Are you using real OpenF1 client?
2. Check Layer 2: Did session resolution succeed?
3. Check Layer 3: Did endpoints return any data?
4. Check Layer 4: Is evidence visible in table?

**Solution**:
- If Layer 1 = Mock: You need real client (check config)
- If Layer 2 = Session NOT Found: Check GP name and year
- If Layer 3 = All 0: OpenF1 API may have no data for this race
- If Layer 4 = Still 0: Check logs for errors

### Symptom: "Session NOT Found"
**Likely causes**:
1. GP name has typo (check spelling)
2. Year is wrong
3. Race hasn't happened yet on OpenF1
4. OpenF1 API is down

**How to verify**:
- Visit https://api.openf1.org (should be up)
- Check if race exists on Formula1.com
- Try a different well-known race (e.g., "Monaco Grand Prix" for May)

### Symptom: Session found but endpoints return 0
**Likely causes**:
1. Race data hasn't been uploaded to OpenF1 yet
2. OpenF1 is having technical issues
3. The specific race doesn't have endpoint data available

**How to verify**:
- Check https://openf1.org/calendar
- Try building with a recent completed race (e.g., most recent grand prix)

## UI Debug Panels (Gradio)

When you build a timeline, the UI shows:

### Build Status Area:
```
✓ or ❌ status message

🔧 OpenF1 Session Resolution Debug
Client Type: OpenF1Client
Detected: Year=2025, GP=Australian Grand Prix, Type=RACE
✓ Session Found: 2025_AUS_R
Matched: Australian Grand Prix 2025 (RACE) - 2025-03-28

🔍 OpenF1 Debug Info:
Events: 13 total | YELLOW=2, PIT=2, SC=1, STINT=5
Sources: PDF=2, OpenF1=11
```

### Timeline Table:
```
Lap | Type    | Title              | Evidence
----|---------|------------------|----------
 1  | YELLOW  | Yellow flag 1      | PDF:0 | OpenF1:1
 22 | PIT     | Pit stops: Lap 22  | PDF:0 | OpenF1:1
 15 | STINT   | Tire change        | PDF:0 | OpenF1:1
```

## Log Search Tips

### Find what client is being used:
```bash
grep "[OpenF1]" logs.txt
grep "Client type" logs.txt
```

### Find session resolution:
```bash
grep "\[SESSION\]" logs.txt
grep "Session resolution" logs.txt
```

### Find endpoint counts:
```bash
grep "\[FETCH\]" logs.txt
grep "Race control events" logs.txt
```

### Find final summary:
```bash
grep "\[FINAL SUMMARY\]" logs.txt
grep "PDF events:" logs.txt
```

## Is It Working?

**✓ Yes** if you see:
- `[OpenF1] Client type: OpenF1Client`
- `[SUCCESS] Session resolution found 1 session(s)`
- `[FETCH] ... events: 1+` (at least one endpoint > 0)
- Table shows `OpenF1:1+` for some events

**✗ No** if you see:
- `[OpenF1] Client type: MockOpenF1Client` (and need real data)
- `[FAIL] Could not match OpenF1 session...`
- All `[FETCH]` counts are 0
- Table shows `OpenF1:0` for all events

## Key Files for Debugging

- **Logs**: Check application console/logs for debug output
- **Table**: Evidence column shows `PDF:X | OpenF1:Y`
- **UI Panel**: Session resolution and event summary
- **Code**: `rag/timeline.py` (build_openf1_timeline), `ui_gradio.py` (UI display)

## Next Steps if Still Not Working

1. Enable DEBUG level logging: `logging.basicConfig(level=logging.DEBUG)`
2. Add print statements in build_openf1_timeline()
3. Test OpenF1 API directly: `curl https://api.openf1.org/sessions?year=2025`
4. Check if you have network access to api.openf1.org
5. Try a different race/year known to have data

