# Project Documentation Index

## Quick Navigation

### 🚀 Getting Started
- **[QUICK_START_STABLE.md](QUICK_START_STABLE.md)** ⭐ START HERE
  - Quick reference for running the app
  - Troubleshooting guide
  - Key improvements explained

- **[README.md](README.md)**
  - Full project overview
  - Architecture explanation
  - LLM setup instructions

### 📋 Implementation Details

- **[COMPLETION_REPORT.md](COMPLETION_REPORT.md)** ✅ PHASE 4 COMPLETE
  - Executive summary
  - All issues resolved
  - Verification checklist
  - Production-ready status

- **[STABILITY_FIXES.md](STABILITY_FIXES.md)** 🔧 TECHNICAL DEEP DIVE
  - Comprehensive problem analysis
  - Detailed solution explanations
  - Code examples and patterns
  - Performance impact analysis

- **[CHANGES_SUMMARY.md](CHANGES_SUMMARY.md)** 📝 CHANGE LOG
  - File-by-file modifications
  - Before/after architecture
  - API changes documented
  - Testing status

### 💾 Code Files

#### Core Files (Modified in Phase 4)
- **[app.py](app.py)** - Streamlit UI (session state refactoring)
- **[rag/llm.py](rag/llm.py)** - LLM backends (timeout/fallback improvements)
- **[rag/app_service.py](rag/app_service.py)** - AppService facade (fallback integration)

#### Original Files (Unchanged)
- **[rag/agent.py](rag/agent.py)** - Agentic workflow
- **[rag/ingest.py](rag/ingest.py)** - PDF ingestion
- **[rag/embed.py](rag/embed.py)** - Text embedding
- **[rag/retrieve.py](rag/retrieve.py)** - Vector search
- **[rag/store.py](rag/store.py)** - Vector database
- **[rag/schemas.py](rag/schemas.py)** - Data models
- **[openf1/api.py](openf1/api.py)** - OpenF1 client
- **[server.py](server.py)** - MCP server
- **[client.py](client.py)** - MCP client

#### Tests
- **[tests/test_ingest.py](tests/test_ingest.py)**
- **[tests/test_openf1.py](tests/test_openf1.py)**
- **[tests/test_brief_schema.py](tests/test_brief_schema.py)**

---

## What's New in Phase 4 (Stability & Reliability)

### 🎯 Problems Fixed
1. ✅ **Streamlit Reruns** - AppService no longer reinitializes
2. ✅ **Ollama Timeouts** - Robust handling for slow systems
3. ✅ **JSON Parsing** - Graceful extraction from malformed responses
4. ✅ **Mock Mode** - Now read-only configuration (startup only)
5. ✅ **Ollama Unavailable** - Graceful fallback to MockLLM

### 🚀 Key Improvements
- Session state guard prevents re-initialization
- Timeout management (10s connection, 120s generation)
- JSON extraction helper with fallback
- Ollama→Mock fallback mechanism
- UI operation locks prevent double-clicks
- Fallback mode warning banner
- Comprehensive error messages

---

## Running the App

### Prerequisites
```bash
# Python 3.10+ required
python --version

# Install dependencies
pip install -r requirements.txt

# Optional: Install Ollama (for production mode)
# From: https://ollama.ai
# Then: ollama pull llama3
```

### Start the App

**With Ollama (Recommended):**
```bash
# Terminal 1: Start Ollama
ollama serve

# Terminal 2: Run Streamlit
streamlit run app.py
```

**Without Ollama (Testing):**
```bash
streamlit run app.py
# App will automatically use MockLLM
```

---

## Key Features

### 📊 UI Capabilities
- PDF upload and ingestion
- Race intelligence brief generation
- Claims analysis with evidence mapping
- Filterable claims display
- Interactive Q&A with source citation
- Auto-generated action items and follow-ups
- Confidence breakdown analysis
- JSON/Markdown export

### 🔄 Processing Pipeline
1. **Ingest** - Extract, chunk, and embed PDF text
2. **Extract** - Identify factual claims using LLM
3. **Validate** - Map claims to OpenF1 data
4. **Brief** - Generate race intelligence summary
5. **Query** - Semantic search + LLM answer generation

### 🎯 Architecture Highlights
- **Agentic RAG** - Multi-step reasoning with planning
- **Vector DB** - ChromaDB for semantic search
- **MCP Server** - FastAPI with tool abstractions
- **Pluggable LLM** - MockLLM or Ollama with fallback
- **Session Caching** - Streamlit state management

---

## Support & Troubleshooting

### Common Issues

**"FALLBACK MODE" in sidebar:**
→ Ollama not running. Run: `ollama serve`

**"Ingest button unresponsive":**
→ Operation already in progress. Wait for spinner.

**"Ollama timeout after 120s":**
→ Increase timeout in code or check Ollama performance

**"AppService reinitialized":**
→ This is fixed in Phase 4! Check app.py for proper session state

### Getting Help
1. Check [QUICK_START_STABLE.md](QUICK_START_STABLE.md) for quick fixes
2. Review [STABILITY_FIXES.md](STABILITY_FIXES.md) for technical details
3. Check inline code comments for implementation
4. Review logs: `streamlit run app.py --logger.level=debug`

---

## Project Structure

```
f1_race_intelligence/
├── app.py                      # Streamlit UI (Phase 4 refactored)
├── requirements.txt            # Dependencies
├── README.md                   # Full documentation
├── QUICK_START_STABLE.md       # Quick reference (START HERE)
├── COMPLETION_REPORT.md        # Phase 4 completion status
├── STABILITY_FIXES.md          # Technical deep dive
├── CHANGES_SUMMARY.md          # Change log
│
├── rag/                        # RAG pipeline
│   ├── llm.py                  # LLM backends (Phase 4 refactored)
│   ├── app_service.py          # UI facade (Phase 4 updated)
│   ├── agent.py                # Agentic workflow
│   ├── ingest.py               # PDF processing
│   ├── embed.py                # Text embedding
│   ├── retrieve.py             # Semantic search
│   ├── store.py                # Vector database
│   └── schemas.py              # Data models
│
├── openf1/                     # OpenF1 API integration
│   └── api.py                  # OpenF1 client
│
├── tests/                      # Test suite
│   ├── test_ingest.py
│   ├── test_openf1.py
│   └── test_brief_schema.py
│
├── data/                       # Sample data (ignored in .gitignore)
├── output/                     # Output cache
└── server.py / client.py       # MCP server/client (alternative interfaces)
```

---

## Phase Progression

### ✅ Phase 1: Initial UI (COMPLETE)
- Streamlit app with PDF upload
- Basic ingestion workflow
- AppService facade

### ✅ Phase 2: Enhanced UX (COMPLETE)
- Audience-aware narratives
- Claims analysis with filtering
- Auto-generated actions & questions
- Q&A with source citation
- Export functionality

### ✅ Phase 3: Free LLM (COMPLETE)
- Replaced OpenAI with Ollama
- Added MockLLM for testing
- Removed API key dependencies

### ✅ Phase 4: Stability (COMPLETE) ⭐ YOU ARE HERE
- Fixed rerun issues
- Improved Ollama reliability
- Graceful fallback mechanism
- Operation locking
- Comprehensive documentation

### 🔄 Phase 5: Performance (PLANNED)
- Async operations
- Caching layer
- Progress tracking
- Telemetry

---

## Version History

| Version | Date | Phase | Status |
|---------|------|-------|--------|
| 1.0 | - | 1 | ✅ Complete |
| 1.1 | - | 2 | ✅ Complete |
| 1.2 | - | 3 | ✅ Complete |
| 2.0 | 2025 | 4 | ✅ **CURRENT** |
| 3.0 | TBD | 5 | 🔄 Planned |

---

## Key Technologies

- **Streamlit 1.28.1** - Web framework
- **Ollama** - Local LLM (free, offline)
- **ChromaDB 0.4.21** - Vector database
- **Sentence-Transformers 2.2.2** - Embeddings
- **Pydantic 2.5.0** - Data validation
- **FastAPI 0.104.1** - MCP server
- **Python 3.10+** - Required

---

## Next Steps

### For Users
1. Read [QUICK_START_STABLE.md](QUICK_START_STABLE.md)
2. Install Ollama (recommended)
3. Run `streamlit run app.py`
4. Upload a race document and explore

### For Developers
1. Review [CHANGES_SUMMARY.md](CHANGES_SUMMARY.md) for API changes
2. Update any code calling `get_llm()` to handle tuple
3. Run `pytest tests/ -v` to verify
4. Review code comments in modified files

### For Maintainers
1. Monitor [COMPLETION_REPORT.md](COMPLETION_REPORT.md) for Phase 4 details
2. Plan Phase 5 work (performance optimization)
3. Consider telemetry collection
4. Track Ollama performance metrics

---

**Last Updated:** 2025  
**Status:** ✅ Production Ready  
**Phase:** 4/5 (Stability Complete)  
**Next Phase:** 5 (Performance Optimization)

---

## Quick Links

| Resource | Purpose | Audience |
|----------|---------|----------|
| [QUICK_START_STABLE.md](QUICK_START_STABLE.md) | Quick reference | **All Users** ⭐ |
| [README.md](README.md) | Full docs | Developers |
| [COMPLETION_REPORT.md](COMPLETION_REPORT.md) | Status summary | Project Managers |
| [STABILITY_FIXES.md](STABILITY_FIXES.md) | Technical details | Developers |
| [CHANGES_SUMMARY.md](CHANGES_SUMMARY.md) | Change log | Maintainers |

---

**Ready to get started? → Go to [QUICK_START_STABLE.md](QUICK_START_STABLE.md)**
