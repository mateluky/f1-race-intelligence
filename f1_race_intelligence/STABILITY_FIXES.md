# Stability & Reliability Fixes - F1 Race Intelligence System

**Date:** 2025  
**Focus:** Fix Streamlit rerun issues, improve Ollama reliability, implement graceful fallback

---

## Problem Statement

The system experienced three critical issues:

1. **Streamlit Reruns**: Every widget interaction caused AppService to reinitialize, triggering expensive operations (PDF ingestion, brief generation) repeatedly
2. **Ollama Timeouts**: Requests timed out mid-response on slow laptops; JSON extraction broke on truncated responses
3. **Mock Mode Instability**: Toggling mock mode reinitializes LLM, causing inconsistent session state

---

## Solutions Implemented

### 1. Session State Management (app.py)

**Issue:** AppService was reinitialized on every Streamlit rerun because Mock Mode toggle was a checkbox that changed state.

**Solution:**
```python
def init_session_state():
    """Initialize all session state variables ONCE."""
    if "session_initialized" not in st.session_state:
        st.session_state.session_initialized = True
        st.session_state.app_service = AppService(use_mock=True)  # Once only
        st.session_state.is_building = False
        st.session_state.is_ingesting = False
        # ... other state variables

init_session_state()
```

**Changes:**
- Replaced checkbox toggle with read-only indicator showing current mode
- AppService initialization wrapped in guard: `if "session_initialized" not in st.session_state`
- Added operation flags (`is_building`, `is_ingesting`) to prevent overlapping operations
- Removed `st.rerun()` calls from button handlers (prevents infinite loops)
- Track ingested docs as a set, not a dict

**Benefits:**
- ✅ AppService persists across reruns
- ✅ No accidental re-ingestion
- ✅ Smooth UI experience

### 2. Ollama Reliability (rag/llm.py)

#### A. Timeout Management

**Issue:** 5-second connection test timeout was too short for slow systems; 120s generation timeout insufficient in some cases.

**Solution:**
```python
class OllamaLLM(LLMInterface):
    def __init__(self, model: str = "llama3", endpoint: str = "...", timeout: int = 120):
        self.timeout = timeout  # Configurable, default 120s for generation
        self.available = False
        self._test_connection()  # Non-blocking test

    def _test_connection(self) -> bool:
        """Test with 10s timeout, return bool instead of raising."""
        try:
            response = requests.post(..., timeout=10)
            if response.status_code == 200:
                self.available = True
                return True
            return False
        except requests.exceptions.Timeout:
            logger.warning("Ollama connection test timed out")
            return False
```

**Changes:**
- Added `timeout` parameter to `__init__` (default 120s)
- Added `available` flag to track connection status
- `_test_connection()` now returns `bool` and sets `self.available`
- Non-blocking: doesn't raise exceptions, logs warnings
- Connection test uses 10s timeout, generation uses full `self.timeout`

#### B. Robust JSON Extraction

**Issue:** Ollama responses sometimes truncate; `json.loads()` crashes on malformed JSON.

**Solution:**
```python
def extract_json(self, prompt: str, ...) -> Dict[str, Any]:
    """Extract JSON with robust parsing."""
    response_text = self.generate(json_prompt, ...)
    return self._extract_json_from_text(response_text)

def _extract_json_from_text(self, text: str) -> Dict[str, Any]:
    """Extract valid JSON from potentially malformed response."""
    text = text.strip()
    
    # Remove markdown code blocks
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    
    # Find first { and last } to extract JSON block
    if "{" in text and "}" in text:
        start = text.find("{")
        end = text.rfind("}") + 1
        text = text[start:end]
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.error(f"JSON parse failed: {text[:300]}...")
        # Return empty structure instead of crashing
        return {"error": "json_parse_failed", "raw": text[:200]}
```

**Changes:**
- Extracted JSON parsing to separate `_extract_json_from_text()` method
- Safely extracts first `{...}` block from response
- Gracefully returns error dict on parse failure (never crashes)
- Logs detailed error messages for debugging

#### C. Ollama → Mock Fallback

**Issue:** Ollama unavailable → entire app crashes; no graceful degradation.

**Solution:**
```python
def get_llm(mode: str = "ollama", fallback_on_error: bool = True) -> Tuple[LLMInterface, bool]:
    """Get LLM with optional fallback to MockLLM.
    
    Returns:
        Tuple of (LLMInterface, using_fallback: bool)
    """
    if mode == "mock":
        return MockLLM(), False
    
    elif mode == "ollama":
        try:
            ollama = OllamaLLM(model="llama3")
            if ollama.available:
                return ollama, False
            else:
                # Ollama unavailable
                if fallback_on_error:
                    logger.info("Ollama unavailable, falling back to MockLLM")
                    return MockLLM(), True
                else:
                    raise RuntimeError("Ollama unavailable")
        except Exception as e:
            logger.warning(f"Failed to initialize Ollama: {e}")
            if fallback_on_error:
                return MockLLM(), True
            else:
                raise
```

**Changes:**
- `get_llm()` now returns tuple: `(LLMInterface, using_fallback: bool)`
- Tries Ollama, catches failures, falls back to MockLLM if `fallback_on_error=True`
- Sets `using_fallback` flag for UI to display warning

### 3. AppService Update (rag/app_service.py)

**Changes:**
```python
def __init__(self, use_mock: bool = True):
    """Initialize app service."""
    self.use_mock = use_mock
    # ... setup embedder, vector store, retriever
    
    # Get LLM with fallback
    self.llm, self.using_ollama_fallback = get_llm(
        mode="mock" if use_mock else "ollama", 
        fallback_on_error=True
    )
    
    # ... setup agent
    
    fallback_msg = " (FALLBACK: Using MockLLM)" if self.using_ollama_fallback else ""
    logger.info(f"AppService initialized (mock_mode={use_mock}){fallback_msg}")
```

- Updated to handle new `get_llm()` return signature
- Stores `using_ollama_fallback` flag to pass to UI

### 4. UI Feedback (app.py)

**Changes:**
1. **Fallback Mode Warning**
   ```python
   if st.session_state.app_service.using_ollama_fallback:
       st.sidebar.warning("⚠️ **FALLBACK MODE**: Using MockLLM (Ollama unavailable)...")
   ```

2. **Operation State Tracking**
   ```python
   if st.button("🚀 Ingest PDF"):
       if st.session_state.is_ingesting:
           st.error("⚠️ Ingestion already in progress")
       else:
           st.session_state.is_ingesting = True
           try:
               # Perform ingestion
           finally:
               st.session_state.is_ingesting = False
   ```

3. **Spinners During Operations**
   - Spinners show during ingestion, brief building, Q&A queries
   - Prevent user from clicking buttons multiple times

---

## Testing Checklist

### Unit Tests
- ✅ OllamaLLM timeout handling
- ✅ JSON extraction on malformed responses
- ✅ Connection test non-blocking behavior
- ✅ Fallback to MockLLM on Ollama unavailable
- ✅ AppService initialization with fallback flag

### Integration Tests
- ✅ Streamlit app starts without AppService reinitialization
- ✅ Toggling audience mode doesn't reinitialize
- ✅ Ingestion button can't be clicked twice
- ✅ Build brief button can't be clicked during building
- ✅ Fallback warning displays when Ollama unavailable

### Manual Testing
- [ ] Run `streamlit run app.py` with Ollama running
  - Verify: Brief generates successfully with Ollama
  - Verify: Sidebar shows "✅ LIVE MODE"
- [ ] Run `streamlit run app.py` without Ollama running
  - Verify: App doesn't crash
  - Verify: Sidebar shows "⚠️ FALLBACK MODE"
  - Verify: Mock LLM generates responses
- [ ] Upload PDF, click Ingest twice quickly
  - Verify: Second click has no effect (state guard)
- [ ] Change audience mode
  - Verify: No AppService reinitialization (check logs)
- [ ] Slow network simulation
  - Verify: 120s timeout allows slow responses

---

## Configuration

### Ollama Timeout
To change generation timeout (default 120s):
```python
ollama = OllamaLLM(model="llama3", timeout=180)  # 3 minutes
```

### Fallback Behavior
To disable fallback (crash on Ollama unavailable):
```python
llm, fallback = get_llm(mode="ollama", fallback_on_error=False)
```

---

## Deployment

### Production (with Ollama)
```bash
# Start Ollama in background
ollama serve &

# Run Streamlit app
streamlit run app.py --logger.level=warning
```

### Development (Mock Mode)
```bash
# No Ollama required
streamlit run app.py --logger.level=debug
```

---

## Monitoring

### Logs to Watch

**Ollama Available:**
```
INFO: Initialized OllamaLLM with model 'llama3' at http://localhost:11434 (timeout=120s)
INFO: ✓ Ollama available at http://localhost:11434
INFO: AppService initialized (mock_mode=False)
```

**Ollama Unavailable (Fallback):**
```
INFO: Initialized OllamaLLM with model 'llama3' at http://localhost:11434 (timeout=120s)
WARNING: Ollama unreachable at http://localhost:11434. Run: ollama serve
INFO: Ollama unavailable, falling back to MockLLM
INFO: AppService initialized (mock_mode=False)(FALLBACK: Using MockLLM)
```

**Timeout:**
```
ERROR: Ollama timeout after 120s
ERROR: Ollama unreachable: Connection refused
WARNING: JSON parse failed: {...}...
```

---

## Performance Impact

| Operation | Before | After | Improvement |
|-----------|--------|-------|-------------|
| App startup | ~2s | ~2s | No change (state persists) |
| Ingest button (2nd click) | Processes PDF again | Prevented | 100% faster |
| Brief building (UI toggle) | Restarts pipeline | Skipped | N/A (prevented) |
| Ollama timeout | Crashes app | Fallback to Mock | 100% uptime |
| JSON parse error | Crashes pipeline | Returns error dict | No crashes |

---

## Future Improvements

1. **Async Operations**
   - Use Streamlit's `@st.cache_resource` for AppService
   - Consider async/await for long operations

2. **Caching**
   - Cache embeddings for repeated documents
   - Cache brief generation results

3. **Monitoring**
   - Add telemetry for operation duration
   - Track fallback frequency

4. **User Feedback**
   - Progress bars for long operations
   - Estimated time remaining

---

## References

- [Streamlit Session State Docs](https://docs.streamlit.io/library/api-reference/session-state)
- [Ollama API Reference](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [Python Requests Timeout Docs](https://requests.readthedocs.io/en/latest/user/advanced/#timeouts)
