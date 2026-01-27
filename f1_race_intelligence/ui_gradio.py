"""Gradio UI for F1 Race Intelligence System - Timeline-focused interface.

This is a Python-only UI using Gradio Blocks, focusing on race timeline reconstruction
combining PDF events and OpenF1 structured data.

Run: python ui_gradio.py
"""

import gradio as gr
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import plotly.graph_objects as go
import plotly.express as px

from rag.app_service import AppService, make_json_serializable

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global app service instance (initialized at startup)
app_service: Optional[AppService] = None


def initialize_app_service(mock_mode: bool) -> None:
    """Initialize AppService (run once at app startup)."""
    global app_service
    if app_service is None:
        app_service = AppService(use_mock=mock_mode)
        logger.info(f"Initialized AppService (mock_mode={mock_mode})")


def ingest_pdf_gradio(
    pdf_file,
    doc_id: str,
    mock_mode: bool,
) -> Tuple[str, bool]:
    """Ingest PDF and return status message.
    
    Args:
        pdf_file: Uploaded PDF file object
        doc_id: Document identifier
        mock_mode: Whether to use mock mode
        
    Returns:
        (status_message, success_bool)
    """
    global app_service
    
    if app_service is None:
        initialize_app_service(mock_mode)
    
    if not pdf_file:
        return "❌ No PDF selected", False
    
    try:
        # In Gradio 6, pdf_file is a path string (NamedString)
        # In earlier versions, it was a file-like object
        if isinstance(pdf_file, str):
            # It's already a file path
            temp_path = Path(pdf_file)
        elif hasattr(pdf_file, 'name') and isinstance(pdf_file.name, str):
            # Gradio 6 NamedString object
            temp_path = Path(str(pdf_file))
        else:
            # It's a file-like object, write to temp
            temp_path = Path(tempfile.gettempdir()) / getattr(pdf_file, 'name', 'temp.pdf')
            with open(temp_path, "wb") as f:
                if hasattr(pdf_file, "read"):
                    f.write(pdf_file.read())
                else:
                    f.write(pdf_file)
        
        # Ingest
        result = app_service.ingest_pdf(str(temp_path), doc_id)
        
        # Only delete if it was a file-like object that we created as temp
        if not isinstance(pdf_file, str) and hasattr(pdf_file, 'name'):
            temp_path.unlink()
        
        if result["success"]:
            return f"✅ {result['message']}", True
        else:
            return f"❌ {result.get('error', 'Unknown error')}", False
    
    except Exception as e:
        logger.error(f"Ingest failed: {e}")
        return f"❌ Error: {str(e)}", False


def build_timeline_gradio(
    doc_id: str,
    year: Optional[int],
    gp_name: str,
    session_type: str,
    mock_mode: bool,
) -> Tuple[str, Optional[Dict]]:
    """Build race timeline and return JSON.
    
    Args:
        doc_id: Document ID
        year: F1 year
        gp_name: GP name
        session_type: Session type
        mock_mode: Mock mode flag
        
    Returns:
        (status_message, timeline_dict)
    """
    global app_service
    
    if app_service is None:
        initialize_app_service(mock_mode)
    
    if not doc_id:
        return "❌ No document selected", None
    
    try:
        result = app_service.build_timeline(
            doc_id=doc_id,
            year=year,
            gp_name=gp_name if gp_name else None,
            session_type=session_type,
        )
        
        if result["success"]:
            timeline = result.get("timeline", {})
            msg = f"✅ {result['message']}"
            return msg, timeline
        else:
            return f"❌ {result.get('error', 'Failed to build timeline')}", None
    
    except Exception as e:
        logger.error(f"Timeline build failed: {e}")
        return f"❌ Error: {str(e)}", None


def format_timeline_for_table(timeline_dict: Optional[Dict]) -> List[Dict]:
    """Convert timeline JSON to table rows.
    
    Args:
        timeline_dict: Timeline JSON from build_timeline
        
    Returns:
        List of dicts for table display
    """
    if not timeline_dict:
        return []
    
    items = timeline_dict.get("timeline_items", [])
    rows = []
    
    for item in items:
        lap = item.get("lap", "-")
        event_type = item.get("event_type", "?")
        title = item.get("title", "")
        description = item.get("description", "")
        confidence = item.get("confidence", "?")
        drivers = ", ".join(item.get("impacted_drivers", []))
        
        rows.append({
            "Lap": lap,
            "Type": event_type,
            "Title": title,
            "Drivers": drivers,
            "Confidence": confidence,
        })
    
    return rows


def get_event_details(timeline_dict: Optional[Dict], selected_row_idx: int) -> str:
    """Get detailed info for selected event.
    
    Args:
        timeline_dict: Timeline JSON
        selected_row_idx: Row index
        
    Returns:
        Formatted HTML string with details
    """
    if not timeline_dict or selected_row_idx < 0:
        return "Select an event to view details"
    
    items = timeline_dict.get("timeline_items", [])
    if selected_row_idx >= len(items):
        return "Invalid selection"
    
    item = items[selected_row_idx]
    
    # Build HTML details
    html = f"""
    <div style="padding: 20px; background: #f5f5f5; border-radius: 8px;">
        <h3>{item.get('title', 'Event')}</h3>
        
        <p><strong>Type:</strong> {item.get('event_type', '-')}</p>
        <p><strong>Lap:</strong> {item.get('lap', '-')}</p>
        <p><strong>Confidence:</strong> {item.get('confidence', '-')}</p>
        
        <h4>Description</h4>
        <p>{item.get('description', 'N/A')}</p>
        
        <h4>Impacted Drivers</h4>
        <p>{', '.join(item.get('impacted_drivers', [])) or 'None'}</p>
        
        <h4>Impact Summary</h4>
        <p>{item.get('impact_summary', 'No impact analysis available')}</p>
        
        <h4>PDF Citations ({len(item.get('pdf_citations', []))})</h4>
        <ul>
    """
    
    for cite in item.get("pdf_citations", []):
        snippet = cite.get("snippet", "")[:100]
        score = cite.get("similarity_score", 0)
        html += f"<li><em>{snippet}...</em> (score: {score:.2f})</li>"
    
    html += """
        </ul>
        
        <h4>OpenF1 Evidence</h4>
        <ul>
    """
    
    for evidence in item.get("openf1_evidence", []):
        etype = evidence.get("evidence_type", "?")
        eid = evidence.get("evidence_id", "-")
        snippet = evidence.get("snippet", "")[:100]
        html += f"<li><strong>{etype}</strong> ({eid}): <em>{snippet}</em></li>"
    
    html += "</ul></div>"
    
    return html


def create_timeline_chart(timeline_dict: Optional[Dict]) -> Optional[go.Figure]:
    """Create Plotly chart of timeline events.
    
    Args:
        timeline_dict: Timeline JSON
        
    Returns:
        Plotly figure or None
    """
    if not timeline_dict:
        return None
    
    items = timeline_dict.get("timeline_items", [])
    if not items:
        return None
    
    # Prepare data
    laps = []
    titles = []
    colors = []
    event_types = []
    
    color_map = {
        "SC": "red",
        "VSC": "orange",
        "RED": "darkred",
        "YELLOW": "gold",
        "PIT": "blue",
        "WEATHER": "gray",
        "INCIDENT": "darkred",
        "PACE": "green",
        "INFO": "lightblue",
    }
    
    for item in items:
        lap = item.get("lap")
        if lap:
            laps.append(lap)
            titles.append(item.get("title", ""))
            event_type = item.get("event_type", "INFO")
            event_types.append(event_type)
            colors.append(color_map.get(event_type, "lightblue"))
    
    if not laps:
        return None
    
    # Create figure
    fig = go.Figure()
    
    fig.add_trace(
        go.Scatter(
            x=laps,
            y=[1] * len(laps),
            mode="markers+text",
            marker=dict(size=12, color=colors),
            text=titles,
            textposition="top center",
            hoverinfo="text",
            showlegend=False,
        )
    )
    
    fig.update_layout(
        title="Race Timeline (by Lap Number)",
        xaxis_title="Lap",
        yaxis=dict(visible=False),
        hovermode="closest",
        height=400,
        margin=dict(t=100, b=50, l=50, r=50),
    )
    
    return fig


def filter_timeline_table(timeline_dict: Optional[Dict], filter_text: str) -> List[Dict]:
    """Filter timeline table by event type or driver.
    
    Args:
        timeline_dict: Timeline JSON
        filter_text: Filter text (event type or driver name)
        
    Returns:
        Filtered rows
    """
    all_rows = format_timeline_for_table(timeline_dict)
    
    if not filter_text:
        return all_rows
    
    filter_lower = filter_text.lower()
    return [
        row for row in all_rows
        if filter_lower in row["Type"].lower()
        or filter_lower in row["Title"].lower()
        or filter_lower in row["Drivers"].lower()
    ]


def update_summary_from_state(timeline: Optional[Dict]) -> str:
    """Generate summary text from timeline state.
    
    Args:
        timeline: Timeline JSON dict
        
    Returns:
        Formatted summary string (Markdown)
    """
    if not timeline:
        return "No timeline built yet. Click 'Reconstruct Timeline' to build one."
    
    items = timeline.get("timeline_items", [])
    event_counts = timeline.get("event_counts", {})
    drivers = timeline.get("drivers_involved", [])
    
    if not items:
        return "Timeline is empty"
    
    summary = f"**Total Events:** {len(items)}\n\n"
    
    if event_counts:
        summary += "**Event Breakdown:**\n"
        for event_type, count in sorted(event_counts.items()):
            summary += f"  • {event_type}: {count}\n"
        summary += "\n"
    
    if drivers:
        summary += f"**Drivers Involved:** {', '.join(sorted(drivers))}"
    
    return summary


# ============================================================================
# GRADIO UI DEFINITION
# ============================================================================

def create_ui():
    """Create Gradio Blocks UI with proper event wiring.
    
    Event Pattern:
    - Buttons (.click()) trigger state updates
    - gr.State ONLY stores data (no .change() calls)
    - UI components (.change()) trigger re-renders from stored state
    - No hidden reruns (deterministic, user-triggered)
    """
    
    with gr.Blocks(
        title="F1 Race Intelligence - Timeline",
        theme=gr.themes.Soft(),
    ) as demo:
        
        gr.Markdown(
            """
            # 🏎️ F1 Race Intelligence - Timeline Reconstruction
            
            **Combines PDF events (LLM-extracted with citations) + OpenF1 structured data**
            
            Build a unified race timeline with evidence, impact analysis, and interactive exploration.
            """
        )
        
        # State storage (PASSIVE - no events attached directly)
        timeline_state = gr.State(None)
        
        # ====================================================================
        # PRE-DEFINE ALL OUTPUT COMPONENTS (needed for button click handler)
        # ====================================================================
        # We need to define these here so the build_click function can output to them
        
        # Tab 1 outputs
        ingest_status = None
        build_status = None
        
        # Tab 2 outputs
        timeline_summary = None
        timeline_table = None
        filter_input = None
        
        # Tab 3 outputs
        detail_output = None
        
        # Tab 4 outputs
        timeline_chart = None
        
        # Tab 5 outputs
        raw_json = None
        
        # ====================================================================
        # TAB 1: UPLOAD & INGEST & BUILD
        # ====================================================================
        
        with gr.Tab("📥 Upload & Build"):
            with gr.Row():
                mock_mode = gr.Checkbox(
                    value=True,
                    label="Mock Mode",
                    info="Disable for real OpenF1 API + Ollama",
                )
            
            gr.Markdown("### Step 1: Upload PDF")
            with gr.Row():
                pdf_file = gr.File(
                    label="Race Document (PDF)",
                    file_types=[".pdf"],
                    file_count="single",
                )
                doc_id_input = gr.Textbox(
                    label="Document ID",
                    value="race_2024_01_01",
                    info="Unique identifier for this document",
                )
            
            with gr.Row():
                ingest_btn = gr.Button("🚀 Ingest PDF", variant="primary", scale=1)
                ingest_status = gr.Textbox(
                    label="Ingest Status",
                    interactive=False,
                    value="Ready",
                )
            
            gr.Markdown("### Step 2: Build Timeline")
            with gr.Row():
                year_input = gr.Number(
                    label="Year",
                    value=2024,
                    precision=0,
                    info="F1 season year",
                )
                gp_name_input = gr.Textbox(
                    label="GP Name",
                    value="",
                    info="e.g., Monaco, Silverstone (optional)",
                )
            
            with gr.Row():
                session_type_input = gr.Dropdown(
                    choices=["RACE", "QUALIFYING", "FP1", "FP2", "FP3"],
                    value="RACE",
                    label="Session Type",
                )
            
            with gr.Row():
                build_btn = gr.Button("🔨 Reconstruct Timeline", variant="primary", scale=1)
                build_status = gr.Textbox(
                    label="Build Status",
                    interactive=False,
                    value="Ready",
                )
        
        # ====================================================================
        # TAB 2: TIMELINE EXPLORER
        # ====================================================================
        
        with gr.Tab("📊 Timeline Explorer"):
            gr.Markdown("### Event Summary")
            
            timeline_summary = gr.Textbox(
                label="Timeline Stats",
                interactive=False,
                value="Build a timeline to see stats",
                lines=3,
            )
            
            gr.Markdown("### Filter Events")
            filter_input = gr.Textbox(
                label="Filter by type, title, or driver",
                placeholder="e.g., SC, PIT, Hamilton",
                info="Leave empty to show all",
                value="",
            )
            
            gr.Markdown("### Timeline Table")
            timeline_table = gr.Dataframe(
                headers=["Lap", "Type", "Title", "Drivers", "Confidence"],
                interactive=False,
                wrap=True,
            )
        
        # ====================================================================
        # TAB 3: EVENT DETAILS
        # ====================================================================
        
        with gr.Tab("🔍 Event Details"):
            gr.Markdown("### First Event Details (sample)")
            
            detail_output = gr.HTML(
                value="<p>Build a timeline to see event details</p>",
                label="Event Details",
            )
        
        # ====================================================================
        # TAB 4: VISUALIZATION
        # ====================================================================
        
        with gr.Tab("📈 Visualization"):
            gr.Markdown("### Race Timeline Chart (by Lap)")
            
            timeline_chart = gr.Plot(label="Timeline Chart")
        
        # ====================================================================
        # TAB 5: RAW DATA
        # ====================================================================
        
        with gr.Tab("📋 Raw Data"):
            gr.Markdown("### Timeline JSON (for debugging/export)")
            
            raw_json = gr.Textbox(
                label="Raw Timeline JSON",
                interactive=False,
                lines=20,
                max_lines=50,
                value="{}",
            )
        
        # ====================================================================
        # NOW WIRE THE EVENTS (all components defined above)
        # ====================================================================
        
        # Event handler for ingest button
        def ingest_click(pdf, doc_id, mock):
            """Ingest PDF - triggered by button click."""
            status, success = ingest_pdf_gradio(pdf, doc_id, mock)
            return status
        
        ingest_btn.click(
            fn=ingest_click,
            inputs=[pdf_file, doc_id_input, mock_mode],
            outputs=[ingest_status],
        )
        
        # Event handler for build button
        def build_click(doc_id, year, gp_name, session_type, mock):
            """Build timeline - triggered by button click.
            
            This is the ONLY entry point for timeline generation.
            Result is stored in timeline_state for UI components to consume.
            """
            status, timeline = build_timeline_gradio(
                doc_id, int(year) if year else None, gp_name, session_type, mock
            )
            
            # Prepare outputs for all dependent components
            summary_text = update_summary_from_state(timeline)
            table_rows = format_timeline_for_table(timeline) if timeline else []
            event_html = get_event_details(timeline, 0) if (timeline and timeline.get("timeline_items")) else "<p>No events in timeline</p>"
            chart_fig = create_timeline_chart(timeline) if timeline else go.Figure().add_annotation(text="Build a timeline to see chart")
            raw_json_str = json.dumps(timeline, indent=2) if timeline else "{}"
            
            return status, timeline, summary_text, table_rows, event_html, chart_fig, raw_json_str
        
        build_btn.click(
            fn=build_click,
            inputs=[doc_id_input, year_input, gp_name_input, session_type_input, mock_mode],
            outputs=[build_status, timeline_state, timeline_summary, timeline_table, detail_output, timeline_chart, raw_json],
        )
        
        # Event handler for filter input
        def filter_and_update_table(filter_text, timeline):
            """Apply filter to timeline table."""
            if not timeline:
                return []
            return filter_timeline_table(timeline, filter_text)
        
        filter_input.change(
            fn=filter_and_update_table,
            inputs=[filter_input, timeline_state],
            outputs=[timeline_table],
        )
    
    return demo


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    # Create and launch UI
    demo = create_ui()
    
    logger.info("Starting F1 Race Intelligence Gradio UI...")
    print("\n" + "=" * 70)
    print("🏎️  F1 Race Intelligence - Timeline Reconstruction")
    print("=" * 70)
    print("\nOpen http://localhost:7860 in your browser")
    print("\nFeatures:")
    print("  • PDF upload with automatic event extraction")
    print("  • OpenF1 race control & pit stop data integration")
    print("  • Interactive timeline explorer with filters")
    print("  • Evidence visualization (PDF citations + OpenF1 data)")
    print("  • Impact analysis for SC/VSC/PIT events")
    print("\nStop with Ctrl+C")
    print("=" * 70 + "\n")
    
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        quiet=False,
    )
