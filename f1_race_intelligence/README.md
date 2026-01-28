# F1 Race Intelligence System

An end-to-end agentic RAG system with MCP server/client for analyzing Formula 1 race documents.

## Overview

This system:
1. Ingests F1 PDF documents (race debriefs, strategy notes, FIA documents)
2. Chunks and embeds text, storing in a vector database
3. Extracts factual claims using an agentic workflow
4. Validates/enriches claims using the OpenF1 API
5. Generates a "Race Intelligence Brief" with evidence mapping

## Architecture

- **Streamlit UI** (`app.py`): Web frontend with PDF upload, ingestion, brief building, and result exploration
- **AppService Facade** (`rag/app_service.py`): Thin adapter between UI and RAG pipeline; ensures JSON-serializable outputs
- **RAG Pipeline**: PDF ingestion → chunking → embedding → vector store → retrieval
- **Agent**: Claim extraction → entity detection → OpenF1 API planning → evidence mapping
- **MCP Server**: FastAPI-based server exposing tools for client interaction
- **OpenF1 Integration**: Cached API client with graceful degradation

### UI Architecture

The Streamlit app treats the `AppService` as the backend:

```
Streamlit UI
    ↓
AppService (app_service.py)
    ├→ ingest_pdf(pdf_path, doc_id)
    ├→ build_brief(doc_id, metadata)
    └→ query(question, doc_id)
    ↓
RAG Pipeline + RaceAgent
    ├→ ingest.py (PDF parsing)
    ├→ embed.py (Text embedding)
    ├→ store.py (Vector DB)
    ├→ agent.py (Claim extraction & evidence mapping)
    └→ llm.py (LLM calls)
```

**Key Design Decisions:**
- `AppService` wraps the RAG pipeline to provide a simple, UI-friendly API
- All outputs pass through `make_json_serializable()` to ensure no numpy/datetime/Path objects leak to JSON
- Session state caching avoids re-ingesting documents
- Mock mode lets users test without any LLM

### LLM Architecture

The system supports pluggable LLM backends via the `LLMInterface`:

```
rag/llm.py
├── MockLLM
│   └── Instant responses (for testing)
└── OllamaLLM (Default)
    ├── Model: llama3:8b (Meta's Llama 3, 8 billion parameters)
    ├── Endpoint: http://localhost:11434/api/generate
    ├── Cost: Free, open-source
    └── Runs: Fully local, no internet required

AppService
├── Mock Mode ON  → MockLLM
└── Mock Mode OFF → OllamaLLM (requires Ollama installed)
```

**Why Ollama?**
- ✅ **Free**: No API costs
- ✅ **Local**: All processing on your machine (privacy)
- ✅ **Open-Source**: llama3:8b from Meta
- ✅ **Fast**: 8B parameters fit in 8GB RAM
- ✅ **Offline**: Works without internet
- ✅ **Simple**: Single command to install and run

## Setup


### Prerequisites
- Python 3.11+
- pip
- Ollama (free, local LLM) - see "LLM Setup" below

### Installation

```bash
cd f1_race_intelligence
pip install -r requirements.txt
```

### LLM Setup (Ollama - Free, Local, No API Keys)

This system uses **Ollama** for all LLM operations. It's completely free and runs locally on your machine.

**1. Install Ollama**

Visit https://ollama.ai and download the installer for your OS (Mac, Linux, Windows).

**2. Pull the llama3 model**

```bash
ollama pull llama3
```

This downloads the 8B parameter model (~5GB). First run takes a few minutes.

**3. Verify Ollama is running**

Ollama auto-starts on most systems. Check:
```bash
curl http://localhost:11434/api/tags
```

If not running, explicitly start it:
```bash
ollama serve
```

The API will be available at `http://localhost:11434`.

**4. Run the Streamlit app**

With Ollama running in the background, start the app:
```bash
streamlit run app.py
```

**Note:** Turn OFF "Mock Mode" in the sidebar to use Ollama. With it ON, you get instant responses without LLM (for quick testing).

### Environment Variables (Optional)

Create a `.env` file:
```
CHROMA_DB_PATH=./chroma_db
LOG_LEVEL=INFO
OLLAMA_ENDPOINT=http://localhost:11434
```

## Usage

### 1. Start the Streamlit UI (Recommended for Local Use)

```bash
streamlit run app.py
```

This launches an interactive browser-based UI at `http://localhost:8501` with the following features:

- **Ingest PDF Tab**: Upload race documents, set optional metadata (year, GP name, session type)
- **Build Brief Tab**: Generate intelligence briefs with one click
- **Explore Results Tab**: View results in tabs:
  - **Brief**: Executive summary & claim statistics (rewritten for your audience)
  - **Claims**: Detailed claim extraction with evidence table and filterable status badges
  - **Actions**: Auto-generated recommendations and follow-ups
  - **Q&A**: Ask questions and get cited sources
  - **Export**: Download JSON/Markdown briefs

**Features:**
- ✅ Free local LLM (Ollama + llama3)
- ✅ No API keys needed
- ✅ Audience modes: Casual Fan / Analyst / Newbie
- ✅ Evidence-backed claims with confidence breakdowns
- ✅ Mock mode toggle (instant responses for testing)
- ✅ Session state caching for ingested documents
- ✅ Responsive design, tabbed interface
- ✅ JSON/Markdown downloads for integration

### 2. Start the MCP Server (For Client Integration)

```bash
python server.py
```


The server runs on `http://localhost:8000` by default.

### 3. Run the Example Client

In another terminal:

```bash
python client.py --pdf path/to/race_document.pdf
```

### Example Commands

**Ingest a PDF:**
```bash
curl -X POST http://localhost:8000/pdf_ingest \
  -F "file=@path/to/document.pdf"
```

**Generate Race Brief:**
```bash
curl -X POST http://localhost:8000/build_race_brief \
  -H "Content-Type: application/json" \
  -d '{"doc_id": "doc_123"}'
```

## Project Structure

```
f1_race_intelligence/
├── rag/
│   ├── __init__.py
│   ├── schemas.py         # Pydantic models
│   ├── prompts.py         # LLM prompt templates
│   ├── ingest.py          # PDF parsing & chunking
│   ├── embed.py           # Embedder interface
│   ├── store.py           # Vector store wrapper
│   ├── retrieve.py        # Retrieval logic
│   ├── agent.py           # Agent orchestration
│   ├── app_service.py     # Streamlit facade (NEW)
│   └── llm.py             # LLM interface
├── openf1/
│   ├── __init__.py
│   └── api.py             # OpenF1 client
├── tests/
│   ├── test_ingest.py
│   ├── test_openf1.py
│   └── test_brief_schema.py
├── app.py                 # Streamlit UI (NEW)
├── server.py              # MCP server
├── client.py              # Example client
├── requirements.txt
├── .env.example
└── README.md
```

## Features

- **Free Local LLM**: Uses Ollama (llama3:8b) - no API keys, no cost, fully offline
- **PDF Ingestion**: Robust parsing with semantic chunking
- **Vector Search**: Fast, semantic similarity matching
- **Claim Extraction**: Automatic factual claim extraction
- **Evidence Mapping**: Links claims to OpenF1 data (lap times, stints, race control messages)
- **Audience Modes**: Rewrite briefs for different audiences (fan/analyst/newbie)
- **Graceful Degradation**: Mock mode for instant testing without Ollama
- **Type Safety**: Full type hints across codebase
- **Caching**: OpenF1 responses cached to reduce API calls
- **Streamlit UI**: Interactive browser-based interface with multi-tab exploration
- **Exportable Results**: JSON/Markdown downloads with full evidence citation

## Quick Start (Streamlit UI)

### Prerequisites
1. **Install Ollama** (free, local LLM)
   ```bash
   # Download from https://ollama.ai
   # Then pull the llama3 model:
   ollama pull llama3
   ```

2. **Run Ollama** (keep it running in background)
   ```bash
   ollama serve
   ```

### Run the App

In a new terminal:

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the Streamlit app
streamlit run app.py

# 3. Browser opens at http://localhost:8501
# 4. Toggle "Use Mock Mode" OFF to use Ollama (ON = instant testing)
# 5. Upload a PDF and click "🚀 Ingest PDF"
# 6. Click "🔨 Build Race Intelligence Brief"
# 7. Explore results in "Results & Analysis" tab
```

**Expected Output:**
- ✅ Audience-specific race narratives (fan/analyst/newbie)
- ✅ Claims table with evidence and confidence badges
- ✅ Auto-generated action items and follow-ups
- ✅ Interactive Q&A with source citation
- ✅ Downloadable JSON/Markdown exports
- ✅ Confidence breakdown analysis

**No API keys needed!** Everything runs locally with Ollama.

## 🆕 OpenF1 Event Extraction (Enhanced Timeline)

**NEW FEATURE:** The timeline explorer now shows comprehensive race events from OpenF1, not just pit stops!

### Event Types Now Supported

The timeline automatically extracts and categorizes:

- 🛞 **Pit Stops** - All driver pit stop events with compounds
- 🚗 **Safety Cars** - Full safety car deployments  
- 🏁 **Virtual Safety Cars** - Yellow flag conditions
- 🟨 **Yellow Flags** - Incidents and hazards
- 🔴 **Red Flags** - Session stoppages
- ⛈️ **Weather Events** - Track condition changes
- 💥 **Incidents** - Crashes, collisions, investigations
- 📊 **Pace Changes** - Notable lap time shifts

### How to Use

1. Go to **Build Timeline** tab
2. Select year and race (e.g., 2024 Bahrain)
3. Click **"Reconstruct Timeline (OpenF1 Only)"**
4. Go to **Timeline Explorer** tab
5. View timeline table with diverse event types
6. Filter by event type, driver, or evidence source

### Features

- **Event Breakdown Display**: Debug panel shows count of each event type
- **Missing Flag Detection**: Warns if expected event types are absent
- **Real OpenF1 Evidence**: Every event linked to original race control messages
- **Smart Filtering**: Filter by event type, driver, or evidence source

### Documentation

For detailed information:
- **User Guide:** [OPENF1_EVENT_EXTRACTION_GUIDE.md](OPENF1_EVENT_EXTRACTION_GUIDE.md)
- **Event Reference:** [EVENT_TYPES_REFERENCE.md](EVENT_TYPES_REFERENCE.md)
- **Technical Details:** [OPENF1_EVENT_EXTRACTION_COMPLETE.md](OPENF1_EVENT_EXTRACTION_COMPLETE.md)
- **Implementation Docs:** [DOCUMENTATION_INDEX.md](DOCUMENTATION_INDEX.md)

---

## Race Intelligence Brief Output

```json
{
  "executive_summary": "Summary of key race insights...",
  "key_points": ["Point 1", "Point 2", ...],
  "extracted_claims": [
    {
      "claim_text": "Driver X had pace advantage in sector 2",
      "claim_type": "pace",
      "entities": {"drivers": ["X"], "teams": ["Team1"]},
      "time_scope": {"lap_start": 10, "lap_end": 30},
      "evidence": [
        {
          "source": "openf1_laps",
          "data": {...},
          "relevance_score": 0.95
        }
      ],
      "status": "supported",
      "confidence": 0.9,
      "rationale": "Sector times confirm claim..."
    }
  ],
  "timeline": [
    {
      "lap": 15,
      "time": "00:34:20",
      "event": "Pit stop for X",
      "source": "pdf"
    }
  ],
  "follow_up_questions": [
    "How did strategy choice impact final outcome?",
    "What was team radio communication about?"
  ]
}
```

## Testing

```bash
pytest tests/ -v
```

## Mock/Offline Mode

The system includes mock implementations for development without API keys:

```python
from rag.llm import MockLLM
from openf1.api import MockOpenF1Client

llm = MockLLM()
f1_client = MockOpenF1Client()
```

## Performance Notes

- First ingestion may take time; subsequent queries are cached
- Vector search returns top-k similar chunks (default k=5)
- OpenF1 API calls are cached for 24 hours
- All processing is synchronous; async mode can be added if needed

## Race Timeline Reconstruction (Gradio UI)

### Overview

The **Race Timeline** feature reconstructs a unified race timeline by combining two complementary data sources:

1. **PDF-Extracted Events**: Unstructured race events parsed from PDF documents via LLM with RAG citations
2. **OpenF1 Structured Data**: Race control messages (Safety Car, VSC, Red Flags), pit stops, and lap data

The result is an **intelligent timeline artifact** showing:
- When events occurred (lap/timestamp)
- What happened (event type + description)
- Supporting evidence (PDF snippets + OpenF1 IDs)
- Impact (drivers affected by SC/VSC/pit stops)
- Confidence scores (PDF extraction confidence)

### Architecture

**Data Flow:**
```
PDF Document
    ↓ (LLM Extraction with RAG citations)
    ↓
PDF Events (TimelineItem with PDFCitations)
    ↓
OpenF1 API (Race control + pit stops)
    ↓ (Normalization)
    ↓
OpenF1 Events (TimelineItem with OpenF1Evidence)
    ↓
Merge & Deduplicate (lap, event_type key)
    ↓
Compute Impact (SC/VSC windows, pit events)
    ↓
Unified RaceTimeline
    ↓
Gradio UI (Explore, Filter, Visualize)
```

**Key Components:**

- **TimelineBuilder** (`rag/timeline.py`): Orchestrates timeline reconstruction
  - `extract_pdf_events()`: LLM-based event extraction with RAG citations
  - `build_openf1_timeline()`: Race control + pit stop normalization
  - `merge_timelines()`: Deduplication & evidence merging
  - `compute_impact()`: Winners/losers analysis for safety car & pit stop windows

- **RaceTimeline Schema** (`rag/schemas.py`): Pydantic models
  - `TimelineItem`: lap, timestamp, event_type, title, description, pdf_citations[], openf1_evidence[], impacted_drivers[], impact_summary, confidence
  - `PDFCitation`: chunk_id, snippet, similarity_score, page_num
  - `OpenF1Evidence`: evidence_type, evidence_id, snippet, payload
  - `TimelineEventType` (Enum): SC, VSC, RED, YELLOW, PIT, WEATHER, INCIDENT, PACE, INFO

- **Gradio Blocks UI** (`ui_gradio.py`): Interactive timeline explorer
  - 5 tabs for different views (ingest, explore, details, visualization, raw)
  - Real-time filtering & search
  - Plotly interactive chart with lap axis
  - Event evidence expansion (PDF snippets + OpenF1 IDs)

### Running the Timeline UI

Start the Gradio application:
```bash
python ui_gradio.py
```

Then open your browser to `http://localhost:7860`

**Workflow:**

1. **Upload & Ingest Tab**
   - Upload a race PDF
   - Provide document ID (e.g., "2024-silverstone-fp1")
   - Enter session metadata: Year, GP name, session type (FP1/FP2/FP3/Q/R)
   - Click "Ingest PDF" to process
   - Click "Build Timeline" to extract events

2. **Timeline Explorer Tab**
   - View event statistics (total count, event types)
   - Filter by text (event type, title, driver name)
   - Browse events in dataframe (Lap, Type, Title, Drivers, Confidence)

3. **Event Details Tab**
   - Click a row in the table to expand
   - View full event description
   - See PDF citations (snippets with page numbers + similarity scores)
   - See OpenF1 evidence (IDs with payloads)

4. **Visualization Tab**
   - Interactive Plotly chart with lap axis
   - Events color-coded by type:
     - Red: Safety Car (SC)
     - Orange: Virtual Safety Car (VSC)
     - Blue: Pit stops (PIT)
     - Green: Yellow flags (YELLOW)
     - Purple: Incidents (INCIDENT)
   - Hover to see event titles
   - Pan & zoom to explore specific sections

5. **Raw Data Tab**
   - View complete timeline JSON (for debugging/export)
   - Copy-paste for external analysis

### Example Output

A timeline event with both PDF and OpenF1 evidence:

```json
{
  "lap": 12,
  "timestamp": "01:23:45",
  "event_type": "SC",
  "title": "Safety Car Deployed",
  "description": "Safety car deployed for incident at Turn 6.",
  "pdf_citations": [
    {
      "chunk_id": "doc_001_chunk_5",
      "snippet": "Safety car deployed at turn 6 after Verstappen's contact with Alonso",
      "similarity_score": 0.94,
      "page_num": 3
    }
  ],
  "openf1_evidence": [
    {
      "evidence_type": "race_control_message",
      "evidence_id": "rc_msg_42",
      "snippet": "Safety car deployed",
      "payload": {"message": "Safety car deployed", "lapTime": "01:23:45"}
    }
  ],
  "impacted_drivers": ["VER", "ALO", "LEC"],
  "impact_summary": "3 drivers pitted during SC window: VER, ALO, LEC gained 1.2s avg",
  "confidence": 0.92
}
```

### Event Types

The timeline categorizes events into:

| Type | Description | Impact Analysis |
|------|-------------|------------------|
| **SC** | Safety Car deployed | Calculates drivers who pitted in safety window |
| **VSC** | Virtual Safety Car | Calculates pit window advantage |
| **RED** | Red Flag (session halted) | Marks all drivers as impacted |
| **YELLOW** | Yellow Flag (caution) | Marks drivers in affected sector |
| **PIT** | Pit stop event | Marks driver + identifies winners/losers |
| **WEATHER** | Weather change | Informational (strategy impact) |
| **INCIDENT** | Accident/collision | Analyzes involved drivers |
| **PACE** | Notable pace change | Informational |
| **INFO** | General race information | Informational |

### Schema Details

**TimelineItem Fields:**

```python
class TimelineItem(BaseModel):
    lap: Optional[int]                    # Race lap number
    timestamp: Optional[str]               # HH:MM:SS or lap time format
    event_type: TimelineEventType         # Enum: SC, VSC, RED, etc.
    title: str                             # Event headline (max 100 chars)
    description: str                       # Event details (max 500 chars)
    pdf_citations: List[PDFCitation]      # Supporting PDF snippets
    openf1_evidence: List[OpenF1Evidence] # Race control messages, pit data
    impacted_drivers: List[str]           # Driver codes (VER, LEC, etc.)
    impact_summary: Optional[str]         # Winners/losers (max 200 chars)
    confidence: float                      # 0.0-1.0, PDF extraction confidence
```

**Evidence Models:**

```python
class PDFCitation(BaseModel):
    chunk_id: str                    # ID in vector store
    snippet: str                     # Actual text (max 300 chars)
    similarity_score: float          # 0.0-1.0, relevance to event
    page_num: Optional[int]          # PDF page number if available

class OpenF1Evidence(BaseModel):
    evidence_type: str               # "race_control_message", "pit_stop", etc.
    evidence_id: str                 # ID in OpenF1 dataset
    snippet: str                     # Extracted snippet (max 200 chars)
    payload: Dict[str, Any]          # Full OpenF1 data structure
```

### Performance & Limitations

**What Works Well:**
- ✅ SC/VSC/Red Flag detection from OpenF1 race control messages
- ✅ Pit stop extraction and driver identification
- ✅ PDF event extraction with LLM (temperature=0.3 for structured output)
- ✅ Evidence merging when PDF & OpenF1 report same event
- ✅ Impact computation for safety car windows (drivers pitted)
- ✅ Interactive filtering, search, and visualization

**Current Limitations:**
- ⚠️ Impact analysis simplified (doesn't use actual lap times yet)
- ⚠️ Stint information (tire strategies) not yet extracted
- ⚠️ Lap-by-lap grid/position data not included
- ⚠️ LLM prompt tuning needed for specific F1 event patterns

**Recommendations:**
- For best results, use clear race reports (FIA official summaries work well)
- Session metadata (year/GP name) helps contextualize events
- Confidence scores <0.7 may indicate PDF parsing issues
- Check raw JSON for OpenF1 evidence details if needed

### Testing the Timeline Feature

**Mock Mode (no OpenF1 API required):**
```bash
# ui_gradio.py auto-detects OpenF1 availability
# Falls back to mock race data if API unavailable
python ui_gradio.py
```

**Integration with AppService:**
```python
from rag.app_service import AppService

app = AppService()
timeline = app.build_timeline(
    doc_id="my_race",
    year=2024,
    gp_name="Silverstone",
    session_type="R"  # Race
)
print(timeline)  # RaceTimeline JSON
```

## Stability & Reliability

### Session State Management

The Streamlit app now implements proper session state initialization to prevent costly re-runs:

```python
# Initialize ONCE per session
def init_session_state():
    if "session_initialized" not in st.session_state:
        st.session_state.session_initialized = True
        st.session_state.app_service = AppService(use_mock=True)
        st.session_state.is_building = False
        st.session_state.is_ingesting = False
        # ... other state
```

**Benefits:**
- `AppService` persists across Streamlit reruns (no re-initialization)
- Operation flags (`is_building`, `is_ingesting`) prevent accidental re-runs
- No explicit `st.rerun()` calls (prevents infinite loops)

### Ollama Reliability & Fallback

The LLM layer now provides graceful degradation:

1. **Timeout Management**
   - Connection test: 10 seconds
   - Generation: 120 seconds (configurable)
   - Handles slow laptops/overloaded systems

2. **Robust JSON Extraction**
   - Extracts valid JSON blocks from malformed responses
   - Gracefully returns empty structure on parse failure
   - Never crashes the pipeline

3. **Ollama→Mock Fallback**
   ```python
   llm, using_fallback = get_llm(mode="ollama", fallback_on_error=True)
   if using_fallback:
       # Show warning to user
       st.sidebar.warning("Using MockLLM (Ollama unavailable)")
   ```

4. **Connection Test Non-Blocking**
   - Returns `bool` to indicate Ollama availability
   - Sets `ollama.available` flag
   - UI shows appropriate mode indicator

### UI Feedback

- Spinners during ingestion/brief building
- Operation state tracking prevents overlapping operations
- Fallback mode warning banner in sidebar
- Error messages with recovery instructions

### Testing & Validation

Run tests with:
```bash
# Pytest
pytest tests/ -v

# With coverage
pytest tests/ --cov=rag --cov=openf1
```

Mock mode is always available for offline testing without Ollama.

## Future Enhancements

- Async/streaming for large PDFs
- Multi-document fusion
- Real-time F1 session updates
- Web UI dashboard
- Advanced NLP (coreference resolution, relation extraction)
- Fine-tuned models for F1-specific language

## License

MIT

## Support

For issues or questions, refer to the inline code documentation and type hints.
