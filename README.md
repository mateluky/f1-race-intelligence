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
┌─────────────────────────────────────────────────────────────────────┐
│                         GRADIO UI (ui_gradio.py)                    │
│  • PDF Upload Tab                                                   │
│  • Timeline Explorer Tab (filterable table)                         │
│  • Event Details Tab                                                │
│  • Visualization Tab (Plotly chart with 14 event type filters)      │
│  • Raw Data Tab                                                     │
└───────────────────────────────────┬─────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    APP SERVICE (rag/app_service.py)                 │
│  • Orchestrates all components                                      │
│  • Coordinates PDF ingestion + OpenF1 data fetching                 │
│  • Metadata extraction (year, GP name, session type)                │
└───────────────┬───────────────────────────────────────┬─────────────┘
                │                                       │
                ▼                                       ▼
┌───────────────────────────┐           ┌─────────────────────────────┐
│   RAG PIPELINE            │           │     OPENF1 CLIENT           │
│                           │           │     (openf1/api.py)         │
│  ┌─────────────────────┐  │           │                             │
│  │ Ingest (ingest.py)  │  │           │  • Sessions lookup          │
│  │ • PDF text extract  │  │           │  • Race control messages    │
│  │ • Chunking          │  │           │  • Pit stops & stints       │
│  └─────────┬───────────┘  │           │  • Position changes         │
│            │              │           │  • Weather data             │
│            ▼              │           │  • Overtakes detection      │
│  ┌─────────────────────┐  │           │  • Starting grid            │
│  │ Embed (embed.py)    │  │           │  • Session results          │
│  │ • Vector embeddings │  │           │                             │
│  └─────────┬───────────┘  │           └─────────────────────────────┘
│            │              │
│            ▼              │
│  ┌─────────────────────┐  │
│  │ Store (store.py)    │  │
│  │ • Vector store      │  │
│  └─────────┬───────────┘  │
│            │              │
│            ▼              │
│  ┌─────────────────────┐  │
│  │ Retrieve (retrieve) │  │
│  │ • Similarity search │  │
│  └─────────┬───────────┘  │
│            │              │
│            ▼              │
│  ┌─────────────────────┐  │
│  │ LLM (llm.py)        │  │
│  │ • Ollama (llama3)   │  │
│  │ • Event extraction  │  │
│  └─────────────────────┘  │
└───────────────────────────┘

                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 TIMELINE BUILDER (rag/timeline.py)                  │
│  • Merges PDF events + OpenF1 events                                │
│  • Deduplication & conflict resolution                              │
│  • Impact analysis scoring                                          │
│  • Event categorization into 14 types                               │
└─────────────────────────────────────────────────────────────────────┘
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

```bash
cd f1_race_intelligence
pip install -r requirements.txt
```

### Running the App

```bash
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

- **Frontend**: Gradio 6.x with Plotly charts
- **Backend**: Python with Pydantic schemas
- **LLM**: Ollama (llama3 model)
- **Data Sources**: PDF documents + OpenF1 API
- **Vector Store**: In-memory with sentence embeddings

## License

MIT License
