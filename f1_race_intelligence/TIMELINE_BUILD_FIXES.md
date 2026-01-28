# Timeline Build - Bug Fixes

## Issues Fixed

### Issue 1: Timeline Building 0 Events
**Root Cause:** TimelineEventType enum was missing `PACE` and `STRATEGY` values, but the code was trying to use them.

**Error:** `type object 'TimelineEventType' has no attribute 'PACE'`

**Fix:** Updated 3 occurrences in [rag/timeline.py](rag/timeline.py):
- Line 508: Changed `TimelineEventType.STRATEGY` → `TimelineEventType.PIT_STOP`
- Line 591: Changed `TimelineEventType.PACE` → `TimelineEventType.PACE_CHANGE`
- Line 839: Updated comparison list to use `PACE_CHANGE` and `PIT_STOP`
- Updated docstring to reference `PACE_CHANGE` instead of `PACE`

**Result:** ✓ Timeline now builds with 3+ events instead of 0

### Issue 2: Gradio Dataframe ValueError (Cannot process type tuple)
**Root Cause:** `make_json_serializable()` wasn't handling Enum types, leaving them as objects that Gradio couldn't process in Dataframe.

**Error:** `ValueError: Cannot process value of type <class 'tuple'> in gr.Dataframe`

**Fix:** Enhanced [rag/app_service.py](rag/app_service.py) `make_json_serializable()`:
- Added Enum handling: `elif hasattr(obj, "value"): return make_json_serializable(obj.value)`
- Reordered bool check before int (bool is subclass of int)
- Now recursively converts all Enum values to their primitive representation

**Result:** ✓ All table values are proper primitives (str, int, float, bool, list)

## Testing

### Before Fixes
```
Success: False
Event count: 0
Error: type object 'TimelineEventType' has no attribute 'PACE'
```

### After Fixes
```
Success: True
Event count: 3
Table rows: 3
Row values: All primitives ✓
JSON serialization: ✓
```

## Validation

✓ Metadata extraction: Detects year=2025, gp="Australian Grand Prix"
✓ Session resolution: Finds OpenF1 session
✓ Timeline building: 3 OpenF1 events extracted
✓ Table conversion: All values Gradio-compatible
✓ No tuple errors in Dataframe
✓ All syntax validation passed

## Files Modified

1. **rag/timeline.py** (4 changes)
   - 3x TimelineEventType enum value fixes
   - 1x docstring update

2. **rag/app_service.py** (1 change)
   - Enhanced `make_json_serializable()` with Enum handling

## Ready for Testing

The system is now ready to upload actual F1 race PDFs and build timelines with full OpenF1 integration.
