# Gradio Event Wiring Fix - Quick Reference

## What Was Broken ❌

```python
# This caused: AttributeError: 'State' object has no attribute 'change'
timeline_state.change(fn=update_summary, inputs=timeline_state, outputs=summary)
```

**Why?** `gr.State` objects cannot emit events. They are passive storage only.

---

## How It's Fixed ✅

### Pattern 1: Button Click (Simple Event)
```python
def ingest_click(pdf, doc_id, mock):
    """Handle PDF ingest button click."""
    status, success = ingest_pdf_gradio(pdf, doc_id, mock)
    return status

ingest_btn.click(
    fn=ingest_click,
    inputs=[pdf_file, doc_id_input, mock_mode],
    outputs=[ingest_status],  # Updates this component
)
```

### Pattern 2: Button Click (Complex - Multiple Outputs)
```python
def build_click(doc_id, year, gp_name, session_type, mock):
    """Build timeline and prepare all outputs."""
    status, timeline = build_timeline_gradio(doc_id, year, gp_name, session_type, mock)
    
    # Compute everything needed for UI
    summary_text = update_summary_from_state(timeline)
    table_rows = format_timeline_for_table(timeline)
    event_html = get_event_details(timeline, 0)
    chart_fig = create_timeline_chart(timeline)
    raw_json_str = json.dumps(timeline, indent=2)
    
    # Return all at once (ATOMIC update)
    return status, timeline, summary_text, table_rows, event_html, chart_fig, raw_json_str

build_btn.click(
    fn=build_click,
    inputs=[doc_id_input, year_input, gp_name_input, session_type_input, mock_mode],
    outputs=[build_status, timeline_state, timeline_summary, timeline_table, 
             detail_output, timeline_chart, raw_json],
)
```

### Pattern 3: Component Change (Depends on State)
```python
def filter_and_update_table(filter_text, timeline):
    """Apply filter when user types."""
    if not timeline:
        return []
    return filter_timeline_table(timeline, filter_text)

# ✅ This works because filter_input is a real component (Textbox)
filter_input.change(
    fn=filter_and_update_table,
    inputs=[filter_input, timeline_state],  # State is dependency, not event source
    outputs=[timeline_table],
)
```

---

## Key Rules

| Rule | ✅ Do | ❌ Don't |
|------|-------|---------|
| **State Events** | Use State as input/output | Call state.change() |
| **Button Events** | button.click(fn=...) | button.change() |
| **Component Events** | component.change(inputs=[state, ...]) | state.change() |
| **Outputs** | Return all at once | Return multiple values separately |
| **Data Flow** | Component → Function → Outputs | Component → State → Event |

---

## Event Sources (Can Emit Events)

✅ **Button** (gr.Button) - `.click()`
✅ **Textbox** (gr.Textbox) - `.change()`
✅ **Dropdown** (gr.Dropdown) - `.change()`
✅ **Slider** (gr.Slider) - `.change()`
✅ **Checkbox** (gr.Checkbox) - `.change()`
✅ **File** (gr.File) - `.change()`
✅ **Dataframe** (gr.Dataframe) - `.select()`

❌ **State** (gr.State) - Cannot emit events

---

## Component Outputs (Can Be Updated)

Any Gradio component can be used as an output:
- Textbox, HTML, Image, Plot, Dataframe, etc.

When a button/component event fires, all outputs update simultaneously.

---

## Common Mistakes & Fixes

### ❌ Mistake 1: State.change()
```python
# WRONG
timeline_state.change(fn=render_chart, inputs=timeline_state, outputs=chart)
```

**Fix:** Put rendering logic in button handler
```python
# RIGHT
def build_click(...):
    timeline = ...
    chart = create_timeline_chart(timeline)
    return ..., timeline, ..., chart, ...

build_btn.click(fn=build_click, outputs=[..., timeline_state, ..., chart])
```

### ❌ Mistake 2: Cascading Updates
```python
# WRONG - Creates event dependency chain
filter_input.change(fn=update_table, outputs=[table_state])
table_state.change(fn=update_chart, outputs=[chart])  # ERROR!
```

**Fix:** Do all computations in one button handler
```python
# RIGHT - All at once
def build_click(...):
    table = format_timeline_for_table(timeline)
    chart = create_timeline_chart(timeline)
    return table, chart

build_btn.click(fn=build_click, outputs=[table, chart])
```

### ❌ Mistake 3: State as Event Source
```python
# WRONG - State cannot emit events
state.change(fn=render_ui, inputs=state, outputs=[...])
```

**Fix:** Use real components for event triggers
```python
# RIGHT - Component triggers, state is input
def on_filter(text, state_data):
    return filter_and_render(state_data, text)

filter_input.change(fn=on_filter, inputs=[filter_input, state], outputs=[table])
```

---

## Testing Your Changes

**Check 1: No State.change() Calls**
```bash
grep -n "\.change()" ui_gradio.py | grep -i state
# Should return: (nothing)
```

**Check 2: Python Syntax Valid**
```bash
python -c "import ast; ast.parse(open('ui_gradio.py').read()); print('✅ OK')"
```

**Check 3: Functions Exist**
```bash
grep "^def " ui_gradio.py | wc -l
# Should show all functions present
```

**Check 4: Event Handlers Present**
```bash
grep -E "(\.click|\.change)\(" ui_gradio.py | head -5
# Should show proper event bindings
```

---

## Gradio Event Documentation

**Reference:**
- Button events: `button.click(fn, inputs, outputs)`
- Component events: `component.change(fn, inputs, outputs)`
- State usage: Pass as input/output only, never as event source

**Rule of Thumb:**
- If you need to update UI on some action → use button/component .click() or .change()
- If you need to store data → use gr.State as input/output
- Never try to call .change() on a State object

---

## Summary

✅ **Before:** State.change() → AttributeError ❌  
✅ **After:** Button.click() returns all outputs → Works! ✅

**Key Insight:** Think of State as a file, not an event stream. Read from it when needed, write to it via component events.

---

## Related Files

- **GRADIO_EVENT_FIX.md** - Technical details
- **EVENT_FLOW.md** - Visual diagrams
- **GRADIO_EVENT_FIX_ACCEPTANCE.md** - Acceptance criteria
- **ui_gradio.py** - Fixed implementation
