# F1 Race Intelligence System

An intelligent Formula 1 race analysis application that combines PDF document parsing with real-time OpenF1 API data to reconstruct comprehensive race timelines with interactive visualizations.

## What is it?

F1 Race Intelligence is a **Retrieval-Augmented Generation (RAG)** system that analyzes F1 race documents (Wikipedia articles, race reports, etc.) and enriches them with live telemetry data from the OpenF1 API. It automatically extracts race events, pit stops, safety car periods, weather changes, overtakes, and more—then presents everything in an interactive timeline visualization.

## Key Features

- **📄 PDF Upload & Parsing** – Upload race documents and extract key events using LLM-powered analysis
- **🔌 OpenF1 API Integration** – Automatically fetches real telemetry: pit stops, stints, race control messages, position changes, overtakes
- **🏎️ Timeline Reconstruction** – Merges PDF-extracted events with API data into a unified, chronological timeline
- **📊 Interactive Visualization** – Plotly-powered chart showing all events by lap and driver with color-coded event types
- **🔍 Advanced Filtering** – Filter by event type, driver, or evidence source
- **🎨 14 Event Type Categories** – Safety Car, VSC, Red Flag, Yellow Flag, Pit Stop, Strategy, Weather, Incident, Overtake, Pace, Position, Result, Grid, Info

## Architecture

```
                                 EXTERNAL SERVICES
                    ┌────────────────────┐    ┌────────────────────┐
                    │   OLLAMA SERVER    │    │   OPENF1 API       │
                    │  localhost:11434   │    │ api.openf1.org     │
                    │  • llama3 model    │    │  • Live telemetry  │
                    └─────────┬──────────┘    └─────────┬──────────┘
                              │                         │
══════════════════════════════╪═════════════════════════╪══════════════════════
                              │       APPLICATION       │
                              │                         │
┌─────────────────────────────┼─────────────────────────┼─────────────────────┐
│                             │    USER INTERFACES      │                     │
│  ┌──────────────────────────┴─────────────────────────┴──────────────────┐  │
│  │                      GRADIO UI (ui_gradio.py)                         │  │
│  │  • 📄 PDF Upload Tab        • 📈 Visualization Tab (Plotly)           │  │
│  │  • 🔎 Timeline Explorer     • 📋 Raw Data Tab                         │  │
│  │  • 📝 Event Details Tab     • 14 Event Type Filters                   │  │
│  └───────────────────────────────────┬───────────────────────────────────┘  │
│                                      │                                      │
│  ┌───────────────────────────────────┼───────────────────────────────────┐  │
│  │              MCP SERVER (server.py) + CLIENT (client.py)              │  │
│  │  • FastAPI-based Model Context Protocol server                        │  │
│  │  • Exposes tools: ingest_pdf, build_timeline, query_timeline          │  │
│  │  • Enables AI assistant integration                                   │  │
│  └───────────────────────────────────┬───────────────────────────────────┘  │
│                                      │                                      │
└──────────────────────────────────────┼──────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                       APP SERVICE (rag/app_service.py)                       │
│  • Orchestrates all components      • Metadata extraction (year, GP, session)│
│  • Coordinates PDF ingestion        • JSON serialization                     │
└──────────────────┬───────────────────────────────────────┬───────────────────┘
                   │                                       │
                   ▼                                       ▼
┌──────────────────────────────────┐    ┌──────────────────────────────────────┐
│       RAG PIPELINE               │    │       OPENF1 CLIENT (openf1/api.py)  │
│                                  │    │                                      │
│  ┌────────────────────────────┐  │    │  • Sessions lookup & resolution      │
│  │   Ingest (ingest.py)       │  │    │  • Race control messages (SC, VSC)   │
│  │   • PDF text extraction    │  │    │  • Pit stops & stint data            │
│  │   • Text chunking          │  │    │  • Position changes tracking         │
│  └─────────────┬──────────────┘  │    │  • Weather data                      │
│                ▼                 │    │  • Overtakes detection               │
│  ┌────────────────────────────┐  │    │  • Starting grid positions           │
│  │   Embed (embed.py)         │  │    │  • Session results                   │
│  │   • Sentence embeddings    │  │    │  • Rate limiting & caching           │
│  └─────────────┬──────────────┘  │    │                                      │
│                ▼                 │    └──────────────────────────────────────┘
│  ┌────────────────────────────┐  │
│  │   Store (store.py)         │  │
│  │   • In-memory vector store │  │
│  └─────────────┬──────────────┘  │
│                ▼                 │
│  ┌────────────────────────────┐  │
│  │   Retrieve (retrieve.py)   │  │
│  │   • Similarity search      │  │
│  │   • Top-K retrieval        │  │
│  └─────────────┬──────────────┘  │
│                ▼                 │
│  ┌────────────────────────────┐  │
│  │   LLM (llm.py)             │  │
│  │   • Ollama interface       │  │
│  │   • Event extraction       │  │
│  │   • Prompts (prompts.py)   │  │
│  └────────────────────────────┘  │
│                                  │
│  ┌────────────────────────────┐  │
│  │   Agent (agent.py)         │  │
│  │   • Query orchestration    │  │
│  └────────────────────────────┘  │
└──────────────────┬───────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                     TIMELINE BUILDER (rag/timeline.py)                       │
│  • Merges PDF events + OpenF1 events    • Impact analysis scoring            │
│  • Deduplication & conflict resolution  • Event categorization (14 types)    │
│  • Schemas (rag/schemas.py): TimelineEvent, TimelineEventType, etc.          │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
f1_race_intelligence/
├── ui_gradio.py          # Main Gradio web interface
├── server.py             # FastAPI MCP server
├── client.py             # MCP client
├── requirements.txt      # Python dependencies
├── pytest.ini            # Test configuration
│
├── openf1/               # OpenF1 API client
│   ├── __init__.py
│   └── api.py            # API client with caching & rate limiting
│
├── rag/                  # RAG pipeline components
│   ├── __init__.py
│   ├── app_service.py    # Main orchestration service
│   ├── timeline.py       # Timeline builder & merger
│   ├── schemas.py        # Pydantic models (TimelineEvent, etc.)
│   ├── ingest.py         # PDF parsing & chunking
│   ├── embed.py          # Text embeddings
│   ├── store.py          # Vector storage
│   ├── retrieve.py       # Similarity search
│   ├── llm.py            # Ollama LLM interface
│   ├── prompts.py        # LLM prompt templates
│   └── agent.py          # Agent orchestration
│
├── output/               # Generated outputs
│   ├── race_brief.json
│   └── race_brief.md
│
└── tests/                # Test files
```

## Quick Start

### Prerequisites

1. **Python 3.10+**
2. **Ollama** with `llama3` model:
   ```bash
   ollama pull llama3
   ollama serve
   ```

### Installation

1. **Navigate to the project folder:**
   ```powershell
   cd path\to\Text Mining and NLP
   ```

2. **Activate the virtual environment:**
   ```powershell
   .\.venv\Scripts\activate
   ```
   
   > If activation is blocked, run once:
   > ```powershell
   > Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
   > ```

3. **Install dependencies (first run only):**
   ```powershell
   python -m pip install -r f1_race_intelligence\requirements.txt
   ```

### Running the App

```powershell
cd f1_race_intelligence
python ui_gradio.py
```

Open `http://localhost:7860` (or the port shown in the terminal).

### Usage

1. **Upload PDF** – Go to "📄 Ingest" tab and upload a race document
2. **Build Timeline** – Click "Build Timeline" to extract events and fetch OpenF1 data
3. **Explore** – Use the "🔎 Timeline" tab to browse events with filters
4. **Visualize** – Go to "📈 Visualization" to see the interactive chart
5. **Filter** – Use the category filters (Race Control, Strategy, Session Info) to focus on specific event types

## Event Types

| Category | Events |
|----------|--------|
| 🚨 Race Control | Safety Car, VSC, Red Flag, Yellow Flag, Incident |
| 🔧 Strategy | Pit Stop, Stint Change, Pace Update, Overtake, Weather |
| 📋 Session Info | Starting Grid, Results, Position, Info |

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Frontend** | Gradio 6.x | Web UI with tabs for upload, timeline, visualization |
| **Visualization** | Plotly | Interactive timeline charts |
| **API Server** | FastAPI | MCP (Model Context Protocol) server |
| **Data Validation** | Pydantic | Schemas for TimelineEvent, EventType, etc. |
| **LLM Runtime** | Ollama (localhost:11434) | Local LLM inference |
| **LLM Model** | llama3 | Event extraction & text analysis |
| **Embeddings** | Sentence Transformers | Text vectorization |
| **Vector Store** | In-memory | Similarity search & Top-K retrieval |
| **PDF Parsing** | PyPDF / pdfplumber | Document text extraction & chunking |
| **External API** | OpenF1 API | Live telemetry, pit stops, race control data |
| **Caching** | In-memory | Rate limiting & API response caching |
| **Language** | Python 3.10+ | Core application runtime |

## License

MIT License
