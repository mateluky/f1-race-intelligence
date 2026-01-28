# Quick Reference: OpenF1 Event Types

## All Supported Event Types

### 1. 🛞 PIT_STOP
**What it is:** Pit stop events (compound change, pit loss, strategy)
**OpenF1 Source:** pit_stops endpoint
**Evidence:** Pit stop data with lap, compound, pit loss time

### 2. 🚗 SAFETY_CAR (SC)
**What it is:** Full safety car deployment
**OpenF1 Source:** Race control messages
**Trigger Words:** "SAFETY CAR" (NOT "VIRTUAL")
**Evidence:** Race control message with SC deployment time

### 3. 🏁 VIRTUAL_SC (VSC)
**What it is:** Virtual safety car (yellow flag conditions without physical car)
**OpenF1 Source:** Race control messages
**Trigger Words:** "VIRTUAL SAFETY CAR" or "VSC"
**Evidence:** Race control message with VSC deployment

### 4. 🟨 YELLOW_FLAG
**What it is:** Yellow flag for hazard/incident
**OpenF1 Source:** Race control messages
**Trigger Words:** "YELLOW FLAG" or ("YELLOW" AND "FLAG")
**Evidence:** Race control message describing hazard

### 5. 🔴 RED_FLAG
**What it is:** Red flag (session stopped)
**OpenF1 Source:** Race control messages
**Trigger Words:** "RED FLAG"
**Evidence:** Race control message with RED FLAG

### 6. ⛈️ WEATHER
**What it is:** Weather changes or track conditions
**OpenF1 Source:** Race control messages
**Trigger Words:** "RAIN", "WET", "TRACK CONDITIONS", "WEATHER"
**Evidence:** Race control message describing conditions

### 7. 💥 INCIDENT
**What it is:** Incidents, crashes, collisions, investigations
**OpenF1 Source:** Race control messages
**Trigger Words:** "INCIDENT", "COLLISION", "CRASH", "OFF TRACK", "DEBRIS", "INVESTIGATION", "PENALTY"
**Evidence:** Race control message describing incident

### 8. 📊 PACE_CHANGE
**What it is:** Notable lap time changes (fastest lap, pit loss recovery)
**OpenF1 Source:** Lap timing data
**Evidence:** Lap timing data showing delta

### 9. ℹ️ INFO
**What it is:** Informational messages (filtered for relevance)
**OpenF1 Source:** Race control messages
**Filter:** Kept only if contains pit lane, grid penalty, or tyre rule keywords
**Evidence:** Race control message

---

## Using the Timeline Explorer

### Filter by Event Type
1. Open **Timeline Explorer** tab
2. Use **"Event Type"** dropdown
3. Select specific type or "All"
4. Table updates to show filtered events

### Filter by Driver
1. Enter driver name (partial match)
2. Shows only events affecting that driver

### Show Only OpenF1 Evidence
1. Check **"Only OpenF1 Evidence"** checkbox
2. Hides PDF-only events (if merged with PDF)

---

## Understanding the Debug Panel

```
🔍 OpenF1 Debug Info:
Events: 47 total | INFO=5, PIT_STOP=12, SAFETY_CAR=2, VIRTUAL_SC=1, YELLOW_FLAG=3, RED_FLAG=0
Sources: PDF=0, OpenF1=47
⚠️ Note: No RED events found. Check if race control messages...
```

### What each part means:

- **47 total**: Total number of extracted events
- **INFO=5, PIT_STOP=12, ...**: Count of each event type
- **PDF=0, OpenF1=47**: Evidence source breakdown
- **⚠️ Warning**: Flags if expected types are missing

### What the warning means:

If you see a warning about missing flags (SC, VSC, YELLOW, RED):
- **Cause 1:** Those events didn't happen in the race
- **Cause 2:** Race control messages don't describe them properly
- **How to check:** Look at raw race control messages in debug logs

---

## Example Scenarios

### Scenario 1: 2024 Bahrain Race
**Expected distribution:**
```
SAFETY_CAR=2    (Safety cars deployed)
YELLOW_FLAG=3   (Yellow flags for incidents)
PIT_STOP=12     (Teams made pit stops)
```

**In debug panel:**
✅ Shows these types
⚠️ Doesn't warn about RED_FLAG (none expected)

### Scenario 2: 2024 Monaco Race
**Expected distribution:**
```
SAFETY_CAR=1    (Usually has 1 SC)
VIRTUAL_SC=2    (VSCs common at Monaco)
RED_FLAG=0 or 1 (Rare, only if major incident)
```

**In debug panel:**
✅ Shows SC and VSC counts
⚠️ May warn about RED_FLAG if expected but not found

---

## Troubleshooting Missing Events

### Problem: No SAFETY_CAR events in table
**Check:**
1. Did the race actually have safety cars?
   - Look at race recap, count SCs
2. Are race control messages in OpenF1?
   - Check OpenF1 API directly: `/race_control` endpoint
3. Is message text being parsed correctly?
   - Look for "SAFETY CAR" (uppercase) in messages
   - Check logs: `[RC] Categorized race control messages: SC=0`

### Problem: All events are PIT_STOP only
**Check:**
1. Is race control endpoint working?
   - Run: `openf1_client.get_race_control(session_key=...)`
   - Should return list of messages
2. Are messages in the right format?
   - Each message should have `message` field with text
3. Check log output:
   - Should show: `[RC] Categorized race control messages: ...`
   - If SC=0, VSC=0, etc., then extraction is working but no flags in data

### Problem: Warning says "No RED events found"
**This is OK if:**
- There were no red flags in the race (normal)
- Confirm by checking race recap

**This is a PROBLEM if:**
- Race definitely had red flag
- Then parsing rules may need adjustment
- Contact developers with race name/year

---

## For Developers: Message Parsing Priority

When parsing race control messages, the system checks in this order:

```
1. "RED FLAG"                      → RED_FLAG
2. "SAFETY CAR" + NOT "VIRTUAL"   → SAFETY_CAR
3. "VIRTUAL SAFETY CAR" | "VSC"   → VIRTUAL_SC
4. "YELLOW FLAG" | "YELLOW"+FLAG  → YELLOW_FLAG
5. RAIN | WET | CONDITIONS | ...  → WEATHER
6. INCIDENT | CRASH | DEBRIS | ... → INCIDENT
7. Other (filtered)                → INFO
```

This priority order prevents false matches (e.g., checking RED before SC).

---

## Evidence Quality

Each event shows evidence with:

- **Evidence Type**: Source (e.g., "race_control")
- **Evidence ID**: Message ID for traceability
- **Snippet**: Message text excerpt
- **Payload**: Full data (for detailed inspection)

Events with **more evidence** = higher confidence

✅ Good: 3+ evidence items for same event
⚠️ OK: 1-2 evidence items
❌ Problem: 0 evidence items (shouldn't happen with current system)

---

## Performance Tips

### Faster Timeline Building
1. Use **OpenF1 only** (don't merge with PDF)
   - PDF processing takes 2-3 seconds
   - OpenF1 takes 1-2 seconds

2. Specify **session type** (Race, Qualifying, Sprint)
   - More efficient than searching all sessions

3. Use **recent races** (2024+)
   - More complete OpenF1 data

### Faster Filtering
- Filter by **event type** first
- Then filter by driver name
- Avoids processing irrelevant events

---

## Questions?

- **"Where's the evidence for this event?"**
  - Hover over "Evidence" column to see details
  - Check debug panel for total evidence count

- **"Why is lap number missing?"**
  - Some OpenF1 messages don't have lap info
  - Lap will be None in these cases
  - Future: Can infer from timestamp

- **"Can I export the timeline?"**
  - Click "Get JSON" button
  - Exports full timeline with all evidence
  - Import into other tools/analysis

---

## Event Type Icons at a Glance

| Icon | Type | Color |
|------|------|-------|
| 🛞 | PIT_STOP | Green |
| 🚗 | SAFETY_CAR | Yellow |
| 🏁 | VIRTUAL_SC | Yellow |
| 🟨 | YELLOW_FLAG | Yellow |
| 🔴 | RED_FLAG | Red |
| ⛈️ | WEATHER | Blue |
| 💥 | INCIDENT | Red |
| 📊 | PACE_CHANGE | Blue |
| ℹ️ | INFO | Gray |

Use these to quickly scan the timeline!
