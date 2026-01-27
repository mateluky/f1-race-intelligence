# Race Timeline - Quick Start Guide

## Installation

```bash
# Install new dependencies
pip install gradio==4.26.0 plotly==5.17.0

# Or update all requirements
pip install -r requirements.txt
```

## Running the UI

```bash
python ui_gradio.py
```

Open browser: **http://localhost:7860**

---

## 5-Tab Workflow

### Tab 1: Upload & Ingest
1. Click "Select a File" → upload race PDF
2. Enter Document ID (e.g., "2024-silverstone-race")
3. Fill session metadata:
   - Year: 2024
   - GP: Silverstone
   - Type: R (Race) / Q (Qualify) / FP1/FP2/FP3
4. Click "Ingest PDF" → waits for ingestion
5. Click "Build Timeline" → extracts events

### Tab 2: Timeline Explorer
1. View event summary (count, types breakdown)
2. Use filter box: type event_type, driver name, or title
3. Browse dataframe (sortable columns)
4. Click row to select (details show in Tab 3)

### Tab 3: Event Details
- Full event description
- **PDF Citations** - Snippets with page numbers
- **OpenF1 Evidence** - Race control messages, pit stops
- Click citations to expand

### Tab 4: Visualization
- Plotly scatter chart
- X-axis: Event lap number
- Color: Event type (SC=red, VSC=orange, PIT=blue, etc.)
- Hover: Event title + description
- Zoom/pan: Interactive navigation

### Tab 5: Raw Data
- Complete timeline JSON
- Copy for export
- Debugging/analysis

---

## Data Flow

```
PDF Upload
    ↓
LLM extracts events (temperature=0.3 for structure)
    ↓
Retriever adds PDF citations
    ↓
OpenF1 API provides race control + pit stops
    ↓
Merge & deduplicate (by lap + event_type)
    ↓
Compute impact (drivers affected)
    ↓
RaceTimeline JSON
    ↓
Interactive Gradio UI
```

---

## Key Files

| File | Purpose |
|------|---------|
| `ui_gradio.py` | Gradio Blocks UI (5 tabs) |
| `rag/timeline.py` | TimelineBuilder orchestration |
| `rag/schemas.py` | TimelineItem, PDFCitation, OpenF1Evidence models |
| `rag/app_service.py` | Facade: build_timeline() method |
| `requirements.txt` | gradio, plotly dependencies |
| `README.md` | Full documentation section |

---

## Example: Programmatic API

```python
from rag.app_service import AppService

app = AppService()

# Ingest PDF first
app.ingest_pdf("race_report.pdf", doc_id="2024-silverstone")

# Build timeline
timeline = app.build_timeline(
    doc_id="2024-silverstone",
    year=2024,
    gp_name="Silverstone",
    session_type="R"  # Race
)

# Use results
if timeline["success"]:
    events = timeline["timeline"]["timeline_items"]
    for event in events:
        print(f"Lap {event['lap']}: {event['title']}")
        print(f"  PDF Citations: {len(event['pdf_citations'])}")
        print(f"  OpenF1 Evidence: {len(event['openf1_evidence'])}")
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "gradio not found" | `pip install gradio==4.26.0` |
| "plotly not found" | `pip install plotly==5.17.0` |
| Port 7860 in use | Gradio auto-increments port (7861, 7862, etc.) |
| No OpenF1 data | Falls back to mock data |
| Low confidence scores | PDF may be unclear; use official race reports |
| JSON parse error | Check raw data tab for malformed events |

---

## Event Types

- **SC** - Safety Car deployed
- **VSC** - Virtual Safety Car
- **RED** - Red Flag (session halted)
- **YELLOW** - Yellow flag warning
- **PIT** - Pit stop event
- **WEATHER** - Weather change
- **INCIDENT** - Accident/collision
- **PACE** - Notable pace change
- **INFO** - General information

---

## What's Included

✅ PDF event extraction with LLM + RAG citations
✅ OpenF1 race control + pit stop parsing
✅ Deduplication by (lap, event_type)
✅ Impact analysis (winners/losers for SC/VSC/PIT)
✅ 5-tab Gradio UI with filters, table, chart, details
✅ Plotly interactive visualization
✅ JSON export for analysis
✅ Mock mode (offline testing)
✅ Full error handling
✅ Comprehensive documentation

---

## Next Steps

1. **Upload test PDF** → Verify ingestion works
2. **Build timeline** → Check event extraction
3. **Explore events** → Filter and search
4. **Visualize** → Chart shows event timeline
5. **Export JSON** → Use in downstream analysis

---

**For full documentation, see:** [README.md](README.md#race-timeline-reconstruction-gradio-ui)
