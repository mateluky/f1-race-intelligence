"""Enhanced Streamlit UI for F1 Race Intelligence System - Improved UX & Architecture."""

import streamlit as st
import pandas as pd
import json
import tempfile
from pathlib import Path
import logging
from datetime import datetime

import plotly.graph_objects as go
import plotly.express as px

from rag.app_service import AppService, make_json_serializable

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page config
st.set_page_config(
    page_title="F1 Race Intelligence",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================================
# Session State Initialization - FIX: Initialize once, never reinitialize
# ============================================================================

def init_session_state():
    """Initialize all session state variables once."""
    if "session_initialized" not in st.session_state:
        st.session_state.session_initialized = True
        st.session_state.mock_mode = True  # Startup mode (startup only)
        st.session_state.app_service = AppService(use_mock=True)
        st.session_state.current_doc_id = None
        st.session_state.ingested_docs = set()
        st.session_state.brief_data = None
        st.session_state.audience = "fan"
        st.session_state.current_step = "upload"
        st.session_state.is_building = False
        st.session_state.is_ingesting = False
        logger.info("✓ Session state initialized")

init_session_state()

# ============================================================================
# Sidebar: Settings & Navigation
# ============================================================================

st.sidebar.title("⚙️ Settings")

# Display current mode (READ-ONLY - set at startup only)
if st.session_state.app_service.using_ollama_fallback:
    st.sidebar.warning(
        "⚠️ **FALLBACK MODE**: Using MockLLM (Ollama unavailable)\n\n"
        "To use Ollama:\n"
        "1. Install: https://ollama.ai\n"
        "2. Run: `ollama pull llama3`\n"
        "3. Run: `ollama serve`\n"
        "4. Restart this app"
    )
else:
    st.sidebar.success(
        f"✅ **LIVE MODE**: Using {'MockLLM (testing)' if st.session_state.mock_mode else 'Ollama (production)'}"
    )

st.sidebar.divider()

# Audience selector
st.session_state.audience = st.sidebar.radio(
    "👥 Audience Mode",
    options=["fan", "analyst", "newbie"],
    index=["fan", "analyst", "newbie"].index(st.session_state.audience),
    help="Adjust explanations for different audiences",
    format_func=lambda x: {
        "fan": "🏆 Casual Fan",
        "analyst": "📊 Analyst",
        "newbie": "🆕 Newbie",
    }[x],
)

st.sidebar.divider()

# Ingested docs
st.sidebar.subheader("📄 Documents")
ingested = st.session_state.app_service.get_ingested_docs()
if ingested:
    st.sidebar.write(f"**Total:** {len(ingested)}")
    for doc_id in ingested:
        if st.sidebar.button(f"✓ {doc_id}", key=f"select_{doc_id}", use_container_width=True):
            st.session_state.current_doc_id = doc_id
            st.session_state.current_step = "explore"
else:
    st.sidebar.write("No documents yet")

st.sidebar.divider()
st.sidebar.caption("🏎️ F1 Race Intelligence v1.0")

# ============================================================================
# Main Header
# ============================================================================

st.title("🏎️ F1 Race Intelligence System")
st.markdown(
    """
    **Extract insights from F1 race documents** using agentic RAG with OpenF1 API integration.
    
    Upload → Ingest → Build → Explore
    """
)


st.divider()

# ============================================================================
# Visual Stepper
# ============================================================================

col1, col2, col3, col4 = st.columns(4)

steps = ["Upload", "Ingest", "Build", "Explore"]
step_values = ["upload", "ingest", "build", "explore"]
step_status = {
    "upload": "⏳" if st.session_state.current_step == "upload" else "✅",
    "ingest": "⏳" if st.session_state.current_step == "ingest" else ("✅" if st.session_state.current_doc_id else "⭕"),
    "build": "⏳" if st.session_state.current_step == "build" else ("✅" if st.session_state.brief_data else "⭕"),
    "explore": "⏳" if st.session_state.current_step == "explore" else ("✅" if st.session_state.brief_data else "⭕"),
}

with col1:
    st.markdown(f"### {step_status['upload']} Upload")
with col2:
    st.markdown(f"### {step_status['ingest']} Ingest")
with col3:
    st.markdown(f"### {step_status['build']} Build")
with col4:
    st.markdown(f"### {step_status['explore']} Explore")

st.divider()

# ============================================================================
# STEP 1: Upload & Ingest
# ============================================================================

tab_upload, tab_results = st.tabs(["📥 Upload & Ingest", "📊 Results & Analysis"])

with tab_upload:
    col_left, col_right = st.columns([2, 1])
    
    with col_left:
        st.subheader("1️⃣ Upload a Race Document")
        uploaded_file = st.file_uploader(
            "Choose a PDF",
            type="pdf",
            help="Race report, FIA document, telemetry analysis, etc.",
            key="pdf_uploader",
        )
        
        if uploaded_file:
            col1, col2 = st.columns(2)
            with col1:
                doc_id_input = st.text_input("Document ID", value="race_doc_" + datetime.now().strftime("%Y%m%d"))
            with col2:
                st.write("")  # spacer
                st.write("")
                if st.button("🚀 Ingest PDF", type="primary", use_container_width=True, key="ingest_button"):
                    if st.session_state.is_ingesting:
                        st.error("⚠️ Ingestion already in progress")
                    else:
                        st.session_state.is_ingesting = True
                        try:
                            with st.spinner("⏳ Ingesting PDF..."):
                                temp_dir = Path(tempfile.gettempdir())
                                temp_path = temp_dir / uploaded_file.name
                                temp_path.write_bytes(uploaded_file.getbuffer())
                                
                                result = st.session_state.app_service.ingest_pdf(str(temp_path), doc_id_input)
                                temp_path.unlink()
                                
                                if result["success"]:
                                    st.session_state.current_doc_id = doc_id_input
                                    st.session_state.ingested_docs.add(doc_id_input)
                                    st.success(f"✅ {result['message']}")
                                    st.session_state.current_step = "ingest"
                                else:
                                    st.error(f"❌ {result['error']}")
                        finally:
                            st.session_state.is_ingesting = False
    
    with col_right:
        st.subheader("2️⃣ Optional Metadata")
        year = st.number_input("Year", value=2024, min_value=2000, max_value=2030)
        gp_name = st.text_input("GP", value="", placeholder="Monaco")
        session_type = st.selectbox("Session", ["RACE", "QUALIFYING", "FP1", "FP2", "FP3"])
    
    st.divider()
    
    st.subheader("3️⃣ Build Brief")
    
    if not st.session_state.current_doc_id:
        st.warning("⚠️ Ingest a document first to build a brief")
        disabled_build = True
    else:
        disabled_build = False
    
    if st.button(
        "🔨 Build Race Intelligence Brief",
        type="primary",
        use_container_width=True,
        disabled=disabled_build,
        key="build_brief_button",
    ):
        if st.session_state.is_building:
            st.error("⚠️ Brief building already in progress")
        else:
            st.session_state.is_building = True
            try:
                with st.spinner("⏳ Generating brief (extracting claims, mapping evidence...)"):
                    result = st.session_state.app_service.build_brief(
                        st.session_state.current_doc_id,
                        year=year if gp_name else None,
                        gp_name=gp_name or None,
                        session_type=session_type if gp_name else None,
                    )
                    
                    if result["success"]:
                        st.session_state.brief_data = result["brief"]
                        st.session_state.current_step = "explore"
                        st.success("✅ Brief generated! Go to **Results & Analysis** tab.")
                    else:
                        st.error(f"❌ {result['error']}")
            finally:
                st.session_state.is_building = False

# ============================================================================
# STEP 2: Results & Analysis (Tabbed)
# ============================================================================

with tab_results:
    if st.session_state.brief_data is None:
        st.info("ℹ️ Build a brief first in the **Upload & Ingest** tab.")
    else:
        brief = st.session_state.brief_data
        
        # Sub-tabs
        tab_brief, tab_claims, tab_actions, tab_qa, tab_exports = st.tabs(
            ["📄 Brief", "📋 Claims", "💡 Actions", "❓ Q&A", "📥 Export"]
        )
        
        # =====================================================================
        # TAB: BRIEF (Audience-Specific Narrative)
        # =====================================================================
        
        with tab_brief:
            st.subheader(f"Race Intelligence Brief ({st.session_state.audience.title()} View)")
            
            # Generate audience-specific narrative
            col_story, col_stats = st.columns([2, 1])
            
            with col_story:
                with st.spinner("✨ Personalizing narrative..."):
                    story = st.session_state.app_service.generate_race_story(
                        st.session_state.current_doc_id,
                        brief,
                        audience=st.session_state.audience,
                    )
                    st.markdown(story)
            
            with col_stats:
                st.subheader("📊 Statistics")
                stats = brief.get("claim_stats", {})
                
                st.metric("Total Claims", stats.get("total", 0))
                st.metric("✅ Supported", stats.get("supported", 0))
                st.metric("❓ Unclear", stats.get("unclear", 0))
                st.metric("❌ Contradicted", stats.get("contradicted", 0))
            
            st.divider()
            
            # Follow-up questions
            st.subheader("Suggested Follow-ups")
            followups = brief.get("follow_up_questions", [])
            if followups:
                for i, q in enumerate(followups, 1):
                    st.write(f"{i}. {q}")
            else:
                st.write("No follow-up questions generated")
        
        # =====================================================================
        # TAB: CLAIMS (Filterable, Evidence-Backed)
        # =====================================================================
        
        with tab_claims:
            st.subheader("Claim Analysis & Evidence")
            
            claims = brief.get("extracted_claims", [])
            
            if not claims:
                st.info("No claims extracted")
            else:
                # Filters
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    status_filter = st.multiselect(
                        "Status",
                        options=["supported", "unclear", "contradicted", "insufficient_data"],
                        default=None,
                        help="Filter by evidence status",
                    )
                
                with col2:
                    type_filter = st.multiselect(
                        "Type",
                        options=sorted(set(c.get("claim_type", "other") for c in claims)),
                        default=None,
                        help="Filter by claim type",
                    )
                
                with col3:
                    confidence_min = st.slider(
                        "Min Confidence",
                        0.0,
                        1.0,
                        0.0,
                        step=0.1,
                        help="Filter by minimum confidence",
                    )
                
                # Filter claims
                filtered_claims = claims
                if status_filter:
                    filtered_claims = [c for c in filtered_claims if c.get("status") in status_filter]
                if type_filter:
                    filtered_claims = [c for c in filtered_claims if c.get("claim_type") in type_filter]
                filtered_claims = [c for c in filtered_claims if c.get("confidence", 0) >= confidence_min]
                
                st.write(f"**Showing {len(filtered_claims)} of {len(claims)} claims**")
                st.divider()
                
                # Display claims
                for i, claim in enumerate(filtered_claims[:20]):  # Limit to 20
                    with st.expander(
                        f"{'✅' if claim.get('status') == 'supported' else '❓' if claim.get('status') == 'unclear' else '❌'} "
                        f"Claim {i+1}: {claim.get('claim_text', '')[:70]}...",
                        expanded=(i == 0),
                    ):
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            conf = claim.get("confidence", 0)
                            conf_level = "🔴 Low" if conf < 0.5 else "🟡 Medium" if conf < 0.75 else "🟢 High"
                            st.metric("Confidence", f"{conf:.2f}", delta=conf_level)
                        
                        with col2:
                            st.metric("Type", claim.get("claim_type", "unknown").upper())
                        
                        with col3:
                            st.metric("Status", claim.get("status", "unknown").upper())
                        
                        st.write(f"**Claim:** {claim.get('claim_text')}")
                        st.write(f"**Rationale:** {claim.get('rationale', 'N/A')}")
                        
                        # Evidence breakdown
                        evidence = claim.get("evidence", [])
                        if evidence:
                            st.write(f"**Evidence ({len(evidence)} sources):**")
                            
                            for ev in evidence:
                                with st.expander(f"📌 {ev.get('source', 'unknown')} (score: {ev.get('relevance_score', 0):.2f})"):
                                    st.write(f"**Interpretation:** {ev.get('interpretation', 'N/A')}")
                                    if isinstance(ev.get("data"), dict):
                                        st.json(ev.get("data"))
                                    else:
                                        st.write(str(ev.get("data", ""))[:500])
        
        # =====================================================================
        # TAB: ACTIONS (Auto-Generated Recommendations)
        # =====================================================================
        
        with tab_actions:
            st.subheader("Recommended Actions & Investigations")
            
            with st.spinner("🔍 Analyzing unclear claims for action items..."):
                action_items = st.session_state.app_service.action_items(
                    st.session_state.current_doc_id,
                    brief,
                )
            
            if action_items:
                for i, item in enumerate(action_items, 1):
                    with st.expander(f"Action {i}: {item.get('issue', 'Unknown')[:60]}...", expanded=(i == 1)):
                        st.write(f"**Issue:** {item.get('issue', '')}")
                        st.write(f"**Likely Cause:** {item.get('likely_cause', '')}")
                        st.write(f"**Recommended Action:** {item.get('recommended_action', '')}")
            else:
                st.info("No action items generated")
            
            st.divider()
            
            st.subheader("Auto-Suggested Follow-ups")
            
            with st.spinner("💡 Generating questions..."):
                auto_qs = st.session_state.app_service.auto_questions(
                    st.session_state.current_doc_id,
                    brief,
                )
            
            if auto_qs:
                for q in auto_qs:
                    col_q, col_ev = st.columns([3, 1])
                    with col_q:
                        st.write(f"**Q:** {q.get('question', '')}")
                        st.caption(f"💡 {q.get('why_relevant', '')}")
                    with col_ev:
                        st.caption(f"Evidence: {q.get('suggested_evidence', 'both').upper()}")
            else:
                st.info("No suggested questions")
        
        # =====================================================================
        # TAB: Q&A (Interactive RAG Query)
        # =====================================================================
        
        with tab_qa:
            st.subheader("🔍 Ask a Question")
            st.write("Query the race document using semantic search + LLM generation")
            
            question = st.text_area(
                "Your question:",
                placeholder="e.g., What was the pit stop strategy? How did tire choice affect performance?",
                height=80,
            )
            
            if st.button("🚀 Get Answer", type="primary", use_container_width=True):
                if not question.strip():
                    st.warning("⚠️ Please enter a question")
                else:
                    with st.spinner("⏳ Searching & generating answer..."):
                        result = st.session_state.app_service.query(question, st.session_state.current_doc_id)
                    
                    if result["success"]:
                        st.subheader("📌 Answer")
                        st.write(result.get("answer", "N/A"))
                        
                        st.divider()
                        
                        st.subheader("📚 Supporting Sources")
                        sources = result.get("sources", [])
                        if sources:
                            for i, source in enumerate(sources, 1):
                                with st.expander(f"Source {i} (similarity: {source.get('score', 0):.2f})"):
                                    st.write(source.get("content", ""))
                                    st.caption(f"Chunk: {source.get('chunk_id')}")
                        else:
                            st.write("No supporting sources found")
                    else:
                        st.error(f"❌ {result.get('error', 'Query failed')}")
        
        # =====================================================================
        # TAB: EXPORT (Downloads)
        # =====================================================================
        
        with tab_exports:
            st.subheader("📥 Export Results")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**JSON Export**")
                json_str = json.dumps(brief, indent=2, default=str)
                st.download_button(
                    label="📥 Download JSON",
                    data=json_str,
                    file_name=f"brief_{st.session_state.current_doc_id}.json",
                    mime="application/json",
                )
            
            with col2:
                st.write("**Markdown Export**")
                md_str = f"""# Race Intelligence Brief

**Document:** {st.session_state.current_doc_id}  
**Generated:** {datetime.now().isoformat()}  
**Audience:** {st.session_state.audience.title()}

## Executive Summary

{brief.get('executive_summary', '')}

## Claims & Evidence

"""
                for i, claim in enumerate(brief.get("extracted_claims", [])[:10], 1):
                    md_str += f"### {i}. {claim.get('claim_text', '')}\n\n"
                    md_str += f"- **Type:** {claim.get('claim_type', 'unknown')}\n"
                    md_str += f"- **Confidence:** {claim.get('confidence', 0):.2f}\n"
                    md_str += f"- **Status:** {claim.get('status', 'unknown')}\n\n"
                
                st.download_button(
                    label="📥 Download Markdown",
                    data=md_str,
                    file_name=f"brief_{st.session_state.current_doc_id}.md",
                    mime="text/markdown",
                )
            
            st.divider()
            
            st.subheader("📊 Confidence Breakdown")
            with st.spinner("🔬 Analyzing confidence..."):
                conf_breakdown = st.session_state.app_service.claim_confidence_breakdown(
                    st.session_state.current_doc_id,
                    brief,
                )
            
            if conf_breakdown:
                # Create table
                table_data = []
                for cb in conf_breakdown:
                    table_data.append({
                        "Claim": cb.get("claim_text", "")[:50] + "...",
                        "PDF Support": cb.get("pdf_support_score", 0),
                        "OpenF1 Support": cb.get("openf1_support_score", 0),
                        "Confidence": cb.get("confidence_level", "Unknown"),
                        "Final Score": cb.get("final_confidence", 0),
                    })
                
                df_conf = pd.DataFrame(table_data)
                st.dataframe(df_conf, use_container_width=True, hide_index=True)
            else:
                st.info("No confidence breakdown available")

# ============================================================================
# Footer
# ============================================================================

st.divider()
st.markdown(
    """
    ---
    **F1 Race Intelligence System** | Agentic RAG + Evidence Mapping  
    *Extracts claims → Plans evidence retrieval → Maps to OpenF1 data → Generates briefs*
    """
)
