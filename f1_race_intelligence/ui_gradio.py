"""Gradio UI for F1 Race Intelligence System - Timeline-focused interface.

This is a Python-only UI using Gradio Blocks, focusing on race timeline reconstruction
combining PDF events and OpenF1 structured data.

Run: python ui_gradio.py
"""

import gradio as gr
import json
import logging
import tempfile
import httpx
import asyncio
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

# ============================================================================
# OLLAMA HEALTH CHECK (Startup Gate)
# ============================================================================

async def check_ollama_availability() -> bool:
    """Check if Ollama is running at http://localhost:11434.
    
    Returns:
        True if Ollama is available, False otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://localhost:11434/api/tags")
            return response.status_code == 200
    except (httpx.ConnectError, httpx.ReadTimeout, httpx.RequestError, Exception):
        return False


def get_ollama_status() -> bool:
    """Synchronous wrapper for Ollama availability check.
    
    Returns:
        True if Ollama is available, False otherwise
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(check_ollama_availability())
        loop.close()
        return result
    except Exception:
        return False


def initialize_app_service(use_mock: bool = False) -> None:
    """Initialize AppService (run once at app startup).
    
    Args:
        use_mock: Whether to use mock mode (default: False for Live Mode)
    """
    global app_service
    if app_service is None:
        app_service = AppService(use_mock=use_mock)
        logger.info(f"Initialized AppService (use_mock={use_mock})")


def ingest_pdf_gradio(
    pdf_file,
    doc_id: str,
    ollama_ready: bool,
) -> Tuple[str, bool]:
    """Ingest PDF and return status message.
    
    Args:
        pdf_file: Uploaded PDF file object
        doc_id: Document identifier
        ollama_ready: Whether Ollama is available
        
    Returns:
        (status_message, success_bool)
    """
    global app_service
    
    if not ollama_ready:
        return "❌ Error: Ollama is not available. Cannot ingest document.", False
    
    if app_service is None:
        initialize_app_service(use_mock=False)
    
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


def format_timeline_for_table(timeline_dict: Optional[Dict]) -> List[Dict]:
    """Convert timeline JSON to table rows.
    
    Args:
        timeline_dict: Timeline JSON from build_timeline
        
    Returns:
        List of dicts for table display (all values are primitives for Gradio compatibility)
    """
    if not timeline_dict:
        return []
    
    items = timeline_dict.get("timeline_items", [])
    rows = []
    
    for item in items:
        lap = str(item.get("lap", "-")) if item.get("lap") is not None else "-"
        
        # event_type is now guaranteed to be a pure string (e.g., "YELLOW", "PIT", "SC")
        # thanks to make_json_serializable converting all Enums before returning
        event_type = str(item.get("event_type", "?"))
        
        title = str(item.get("title", ""))
        confidence = str(item.get("confidence", "?"))
        
        # Join drivers into single string (no objects)
        drivers_list = item.get("impacted_drivers", [])
        drivers = ", ".join([str(d) for d in drivers_list]) if drivers_list else ""
        
        # Count evidence sources
        pdf_citations = item.get("pdf_citations", [])
        openf1_evidence = item.get("openf1_evidence", [])
        pdf_count = len(pdf_citations) if isinstance(pdf_citations, list) else 0
        openf1_count = len(openf1_evidence) if isinstance(openf1_evidence, list) else 0
        evidence_str = f"PDF:{pdf_count} | OpenF1:{openf1_count}" if (pdf_count + openf1_count) > 0 else "—"
        
        rows.append({
            "Lap": lap,
            "Type": event_type,
            "Title": title,
            "Drivers": drivers,
            "Confidence": confidence,
            "Evidence": evidence_str,
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
    """Create Plotly chart of timeline events with driver stints and event overlays.
    
    Shows:
    - Y-axis: driver names
    - X-axis: lap number
    - Stint bars: colored by compound (soft=red, medium=yellow, hard=blue)
    - Event markers: SC/VSC/RED/YELLOW/PIT/STRATEGY overlaid on stints
    
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
    
    try:
        # Separate stints from events
        stint_events = [i for i in items if i.get("event_type") == "STRATEGY"]
        other_events = [i for i in items if i.get("event_type") != "STRATEGY"]
        
        fig = go.Figure()
        
        # Color map for tire compounds
        compound_colors = {
            "soft": "#ff4444",
            "medium": "#ffdd44",
            "hard": "#4466ff",
            "intermediate": "#44dd44",
            "wet": "#4499ff",
        }
        
        # Add stint bars for each driver
        drivers_with_stints = set()
        for event in stint_events:
            drivers = event.get("impacted_drivers", [])
            for driver in drivers:
                drivers_with_stints.add(driver)
        
        # Extract stint data from description
        for event in stint_events:
            drivers = event.get("impacted_drivers", [])
            if not drivers:
                continue
            
            driver = drivers[0]
            lap = event.get("lap", 0)
            description = event.get("description", "")
            
            # Parse compound from description (e.g. "changed from soft to hard")
            compounds_in_desc = [c for c in compound_colors.keys() if c in description.lower()]
            if len(compounds_in_desc) >= 2:
                compound_to = compounds_in_desc[-1]  # Last compound mentioned (after "to")
            elif len(compounds_in_desc) == 1:
                compound_to = compounds_in_desc[0]
            else:
                compound_to = "unknown"
            
            # Draw a marker for stint change
            fig.add_trace(
                go.Scatter(
                    x=[lap],
                    y=[driver],
                    mode="markers",
                    marker=dict(
                        size=10,
                        color=compound_colors.get(compound_to, "#cccccc"),
                        symbol="diamond",
                        line=dict(width=2, color="black"),
                    ),
                    name=f"{driver} ({compound_to})",
                    hovertemplate=f"<b>{driver}</b><br>Lap {lap}<br>Tire: {compound_to}<extra></extra>",
                    showlegend=False,
                )
            )
        
        # Add event markers (SC/VSC/RED/YELLOW/PIT)
        event_colors = {
            "SC": "red",
            "VSC": "orange",
            "RED": "darkred",
            "YELLOW": "gold",
            "PIT": "blue",
            "PACE": "green",
            "WEATHER": "gray",
            "INCIDENT": "darkred",
            "INFO": "lightblue",
        }
        
        for event in other_events:
            lap = event.get("lap")
            if not lap:
                continue
            
            event_type = event.get("event_type", "INFO")
            title = event.get("title", "")
            drivers = event.get("impacted_drivers", [])
            
            # If event has drivers, show at driver's row; otherwise at bottom
            if drivers:
                for i, driver in enumerate(drivers):
                    y_pos = driver
                    offset = i * 0.1  # Slight vertical offset for multiple drivers
                    
                    fig.add_trace(
                        go.Scatter(
                            x=[lap + offset * 0.5],
                            y=[y_pos],
                            mode="markers",
                            marker=dict(
                                size=8,
                                color=event_colors.get(event_type, "lightblue"),
                                symbol="star",
                            ),
                            name=event_type,
                            hovertemplate=f"<b>{title}</b><br>Lap {lap}<br>{driver}<extra></extra>",
                            showlegend=False,
                        )
                    )
            else:
                # Event with no specific driver - show at top
                fig.add_trace(
                    go.Scatter(
                        x=[lap],
                        y=["RACE"],
                        mode="markers+text",
                        marker=dict(
                            size=8,
                            color=event_colors.get(event_type, "lightblue"),
                            symbol="star",
                        ),
                        text=event_type,
                        textposition="top center",
                        name=event_type,
                        hovertemplate=f"<b>{title}</b><br>Lap {lap}<extra></extra>",
                        showlegend=False,
                    )
                )
        
        # Update layout
        fig.update_layout(
            title="Race Timeline: Driver Stints & Events (by Lap Number)",
            xaxis_title="Lap",
            yaxis_title="Driver / Event",
            hovermode="closest",
            height=500,
            margin=dict(t=100, b=80, l=150, r=50),
            template="plotly_white",
        )
        
        return fig
    
    except Exception as e:
        logger.warning(f"Failed to create timeline chart: {e}")
        return None


def filter_timeline_table(timeline_dict: Optional[Dict], filter_text: str) -> List[Dict]:
    """Filter timeline table by event type or driver (legacy simple filter).
    
    Args:
        timeline_dict: Timeline JSON
        filter_text: Filter text (event type or driver name)
        
    Returns:
        Filtered rows with all primitive values (no objects)
    """
    all_rows = format_timeline_for_table(timeline_dict)
    
    if not filter_text:
        return all_rows
    
    filter_lower = filter_text.lower()
    return [
        row for row in all_rows
        if filter_lower in str(row.get("Type", "")).lower()
        or filter_lower in str(row.get("Title", "")).lower()
        or filter_lower in str(row.get("Drivers", "")).lower()
    ]


def filter_timeline_advanced(
    timeline_dict: Optional[Dict],
    filter_event_type: str = "All",
    filter_driver: str = "",
    filter_evidence_only: bool = False,
) -> Tuple[List[str], List[List]]:
    """Filter timeline with multiple criteria: type, driver, evidence.
    
    Args:
        timeline_dict: Timeline JSON
        filter_event_type: Event type filter ("All" or specific type)
        filter_driver: Driver name partial match
        filter_evidence_only: Only show events with OpenF1 evidence
        
    Returns:
        (columns, filtered_rows) tuple for Gradio Dataframe
    """
    if not timeline_dict:
        return (
            ["Lap", "Type", "Title", "Drivers", "Impact", "Evidence", "Confidence"],
            []
        )
    
    items = timeline_dict.get("timeline_items", [])
    
    filtered_items = []
    for item in items:
        # Type filter
        if filter_event_type != "All":
            if str(item.get("event_type", "")).upper() != filter_event_type.upper():
                continue
        
        # Driver filter
        if filter_driver:
            drivers = item.get("impacted_drivers", [])
            if not any(filter_driver.upper() in str(d).upper() for d in drivers):
                continue
        
        # Evidence filter
        if filter_evidence_only:
            openf1_evidence = item.get("openf1_evidence", [])
            if not openf1_evidence or len(openf1_evidence) == 0:
                continue
        
        filtered_items.append(item)
    
    # Convert to table format
    return timeline_items_to_table(filtered_items)


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


def timeline_items_to_table(timeline_items: Optional[List[Dict]]) -> Tuple[List[str], List[List]]:
    """Convert TimelineItem objects to flattened table rows (all primitives).
    
    Reason for flattening: Gradio's Dataframe component stringifies nested objects/dicts,
    causing "[object Object]" display. This function ensures all cell values are primitives
    (str/int/float/bool) that render correctly.
    
    Args:
        timeline_items: List of timeline item dicts
        
    Returns:
        (columns, rows) tuple where rows are lists of primitives (no objects/dicts)
    """
    if not timeline_items:
        return (
            ["Lap", "Type", "Title", "Drivers", "Impact", "Evidence", "Confidence"],
            []
        )
    
    columns = ["Lap", "Type", "Title", "Drivers", "Impact", "Evidence", "Confidence"]
    rows = []
    
    for item in timeline_items:
        # Flatten all fields to primitives only
        lap = str(item.get("lap", "-")) if item.get("lap") is not None else "-"
        # event_type is guaranteed to be a pure string (e.g., "YELLOW", "PIT") from make_json_serializable
        event_type = str(item.get("event_type", "?"))
        title = str(item.get("title", ""))
        
        # Join drivers into single string
        drivers_list = item.get("impacted_drivers", [])
        drivers = ", ".join([str(d) for d in drivers_list]) if drivers_list else ""
        
        # Impact summary (benefited/hurt drivers)
        impact = str(item.get("impact_summary", "")).strip()
        if not impact or impact == "":
            impact = "—"
        
        # Count evidence sources and represent as string
        pdf_citations = item.get("pdf_citations", [])
        openf1_evidence = item.get("openf1_evidence", [])
        pdf_count = len(pdf_citations) if isinstance(pdf_citations, list) else 0
        openf1_count = len(openf1_evidence) if isinstance(openf1_evidence, list) else 0
        evidence_str = f"PDF:{pdf_count} | OpenF1:{openf1_count}" if (pdf_count + openf1_count) > 0 else "—"
        
        confidence = str(item.get("confidence", "?"))
        
        # All values must be primitives (str/int/float/bool), not objects or dicts
        row = [lap, event_type, title, drivers, impact, evidence_str, confidence]
        rows.append(row)
    
    return columns, rows


def get_openf1_debug_info(timeline: Optional[Dict]) -> str:
    """Extract OpenF1 debugging information from timeline.
    
    Shows:
    - Event count
    - Event type breakdown
    - Evidence sources (PDF vs OpenF1)
    - Warnings if expected flag types are missing
    - Warnings if 0 events
    
    Args:
        timeline: Timeline dict from build_timeline
        
    Returns:
        HTML-formatted debug panel
    """
    if not timeline:
        return "<p style='color: gray;'>No timeline data</p>"
    
    items = timeline.get("timeline_items", [])
    if not items:
        return "<p style='color: red;'><b>⚠️ WARNING:</b> Timeline has <b>0 events</b>. OpenF1 may have returned no data or GP name may not match. Check logs for details.</p>"
    
    # Count event types
    event_counts = {}
    pdf_count = 0
    openf1_count = 0
    
    for item in items:
        event_type = str(item.get("event_type", "UNKNOWN"))
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
        
        # Count sources
        if item.get("pdf_citations"):
            pdf_count += len(item.get("pdf_citations", []))
        if item.get("openf1_evidence"):
            openf1_count += len(item.get("openf1_evidence", []))
    
    # Build HTML
    event_str = ", ".join([f"<b>{k}</b>={v}" for k, v in sorted(event_counts.items())])
    
    html = "<div style='background-color: #f5f5f5; padding: 10px; border-left: 4px solid #0066cc; border-radius: 4px;'>"
    html += "<b>🔍 OpenF1 Debug Info:</b><br/>"
    html += f"<b>Events:</b> {len(items)} total | {event_str}<br/>"
    html += f"<b>Sources:</b> PDF={pdf_count}, OpenF1={openf1_count}<br/>"
    
    # Check for expected flag types that are missing
    expected_flags = ["SC", "VSC", "YELLOW", "RED"]
    missing_flags = []
    for flag in expected_flags:
        if flag not in event_counts:
            missing_flags.append(flag)
    
    if missing_flags and openf1_count > 0:
        # Only warn if we have OpenF1 evidence but are missing flags
        html += f"<span style='color: #ff9800;'>⚠️ <b>Note:</b> No {', '.join(missing_flags)} events found. "
        html += "Check if race control messages include these flag types or if parsing rules need adjustment.</span><br/>"
    
    html += "</div>"
    
    return html


def get_openf1_session_info(result: Optional[Dict]) -> str:
    """Extract and format OpenF1 session resolution info for UI display.
    
    Args:
        result: Result dict from app_service.build_timeline
        
    Returns:
        HTML-formatted session resolution info
    """
    if not result:
        return "<p style='color: gray;'>No session information</p>"
    
    client_type = result.get("openf1_client_type", "unknown")
    debug_info = result.get("debug_info", {})
    
    if not debug_info:
        return "<p style='color: gray;'>No session debug info</p>"
    
    html = "<div style='background-color: #fff9e6; padding: 12px; border-left: 4px solid #ff9800; border-radius: 4px; margin-bottom: 10px;'>"
    html += "<b>🔧 OpenF1 Session Resolution Debug</b><br/>"
    html += f"<b>Client Type:</b> {client_type}<br/>"
    
    # Detected metadata
    html += f"<b>Detected:</b> Year={debug_info.get('detected_year')}, "
    html += f"GP={debug_info.get('detected_gp')}, "
    html += f"Type={debug_info.get('detected_session_type')}<br/>"
    
    # Session resolution result
    session_id = debug_info.get('session_id')
    if session_id:
        html += f"<span style='color: green;'>✓ <b>Session Found:</b> {session_id}</span><br/>"
        matched = debug_info.get('matched_session', {})
        if matched:
            html += f"<b>Matched:</b> {matched.get('gp_name')} {matched.get('year')} "
            html += f"({matched.get('type')}) - {matched.get('date')}<br/>"
    else:
        error = debug_info.get('error', 'Unknown error')
        html += f"<span style='color: red;'>✗ <b>Session NOT Found:</b> {error}</span><br/>"
    
    html += "</div>"
    return html


def openf1_health_check() -> Dict[str, Any]:
    """Check if OpenF1 API is reachable and working.
    
    Args:
        None
        
    Returns:
        Dict with keys: ok (bool), message (str), base_url (str)
    """
    try:
        import httpx
        
        base_url = "https://api.openf1.org"
        
        # Quick health check: fetch a single driver (lightweight endpoint)
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{base_url}/v1/drivers?limit=1")
            ok = response.status_code == 200
        
        if ok:
            return {
                "ok": True,
                "message": "✅ OpenF1 connected",
                "base_url": base_url,
            }
        else:
            return {
                "ok": False,
                "message": f"❌ OpenF1 unreachable (HTTP {response.status_code})",
                "base_url": base_url,
            }
    
    except Exception as e:
        return {
            "ok": False,
            "message": f"❌ OpenF1 check failed: {str(e)}",
            "base_url": "https://api.openf1.org",
        }


def extract_metadata_gradio(doc_id: str, ollama_ready: bool) -> Dict[str, Any]:
    """Extract race metadata from ingested PDF using Ollama LLM.
    
    Args:
        doc_id: Document ID
        ollama_ready: Whether Ollama is available
        
    Returns:
        Dict with metadata extraction result
    """
    global app_service
    
    if not ollama_ready:
        return {
            "success": False,
            "error": "Ollama is not available.",
        }
    
    if app_service is None:
        return {
            "success": False,
            "error": "AppService not initialized.",
        }
    
    try:
        result = app_service.extract_race_metadata(doc_id)
        
        if result["success"]:
            # Build display text with warning if needed
            display_text = f"✅ {result['message']}"
            
            # Show why detection failed if using Unknown
            if result.get("gp_name") == "Unknown":
                reason = result.get("reasoning", "")
                path = result.get("extraction_path", "unknown")
                display_text = f"⚠️ {result['message']}\n[Why: {path} - {reason}]"
                display_text += "\n⚠️ Could not reliably detect GP name. Timeline will show 0 OpenF1 events."
            elif result.get("warning"):
                # Low confidence detection
                display_text = f"✅ {result['message']}\n[{result['warning']}]"
            
            return {
                "success": True,
                "year": result["year"],
                "gp_name": result["gp_name"],
                "session_type": result["session_type"],
                "display_text": display_text,
                "extraction_path": result.get("extraction_path", "unknown"),
                "reasoning": result.get("reasoning", ""),
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Metadata extraction failed"),
            }
    
    except Exception as e:
        logger.error(f"Metadata extraction failed: {e}")
        return {
            "success": False,
            "error": f"Error: {str(e)}",
        }


def build_timeline_gradio(
    doc_id: str,
    year: Optional[int],
    gp_name: Optional[str],
    session_type: str,
    ollama_ready: bool,
) -> Tuple[str, Optional[Dict], Optional[Dict]]:
    """Build timeline with auto-extracted metadata.
    
    If year and gp_name are not provided (or are None), uses auto-extraction.
    
    Args:
        doc_id: Document ID
        year: Optional year (if None, will be auto-extracted)
        gp_name: Optional GP name (if None, will be auto-extracted)
        session_type: Session type
        ollama_ready: Whether Ollama is available
        
    Returns:
        (status_message, timeline_dict, result_dict)  # result_dict contains debug info
    """
    global app_service
    
    if not ollama_ready:
        return "❌ Error: Ollama is not available. Cannot build timeline.", None, None
    
    if app_service is None:
        return "❌ Error: AppService not initialized.", None, None
    
    if not doc_id:
        return "❌ No document selected", None, None
    
    try:
        # Call build_timeline with auto_extract_metadata=True
        # This will auto-extract year and gp_name from PDF if not provided
        result = app_service.build_timeline(
            doc_id=doc_id,
            year=int(year) if year else None,
            gp_name=gp_name if gp_name else None,
            session_type=session_type,
            auto_extract_metadata=True,
        )
        
        if result["success"]:
            timeline = result.get("timeline", {})
            
            # Explicit check: fail if timeline is empty (0 events)
            timeline_items = timeline.get("timeline_items", [])
            if len(timeline_items) == 0:
                error_msg = (
                    "❌ FAILED: Timeline build returned 0 events. "
                    "Possible causes:\n"
                    "1. GP name not found in OpenF1 database (check spelling)\n"
                    "2. OpenF1 endpoint returned no data\n"
                    "3. Session resolution failed\n"
                    "Check application logs for detailed debugging info."
                )
                logger.error(f"[FAIL] Empty timeline after build: {result}")
                return error_msg, None, result
            
            msg = f"✅ {result['message']}"
            return msg, timeline, result
        else:
            return f"❌ {result.get('error', 'Failed to build timeline')}", None, result
    
    except Exception as e:
        logger.error(f"Timeline build failed: {e}")
        return f"❌ Error: {str(e)}", None, None


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
        ollama_ready = gr.State(value=get_ollama_status())
        timeline_state = gr.State(None)
        
        # ====================================================================
        # EVENT HANDLER FUNCTIONS (defined here to capture ollama_ready in closure)
        # ====================================================================
        
        def ingest_click(pdf, doc_id):
            """Ingest PDF - triggered by button click.
            After ingestion, automatically extract race metadata.
            """
            status, success = ingest_pdf_gradio(pdf, doc_id, ollama_ready.value)
            
            # If ingestion succeeds, try to extract metadata
            detected_race = "Metadata extraction pending..."
            if success:
                metadata = extract_metadata_gradio(doc_id, ollama_ready.value)
                if metadata["success"]:
                    detected_race = metadata["display_text"]
                else:
                    detected_race = f"⚠️ {metadata.get('error', 'Could not detect race metadata')}"
            
            return status, detected_race
        
        def build_click(doc_id, year, gp_name, session_type):
            """Build timeline - triggered by button click.
            
            This is the ONLY entry point for timeline generation.
            Result is stored in timeline_state for UI components to consume.
            Uses live Ollama inference (no fallback to mock).
            Uses auto-extracted metadata if available.
            """
            status, timeline, result = build_timeline_gradio(
                doc_id, year, gp_name, session_type, ollama_ready.value
            )
            
            # Prepare outputs for all dependent components
            summary_text = update_summary_from_state(timeline)
            
            # Use flattened table rendering (avoids "[object Object]" display)
            if timeline:
                timeline_items = timeline.get("timeline_items", [])
                columns, table_rows = timeline_items_to_table(timeline_items)
            else:
                columns, table_rows = [], []
            
            event_html = get_event_details(timeline, 0) if (timeline and timeline.get("timeline_items")) else "<p>No events in timeline</p>"
            chart_fig = create_timeline_chart(timeline) if timeline else go.Figure().add_annotation(text="Build a timeline to see chart")
            raw_json_str = json.dumps(timeline, indent=2) if timeline else "{}"
            
            # Build OpenF1 debug info with session resolution details
            openf1_status = openf1_health_check()
            openf1_badge = openf1_status.get("message", "❌ OpenF1 status unknown")
            openf1_badge += "<br/>"
            
            # Add session resolution debug info
            session_info = get_openf1_session_info(result)
            openf1_badge += session_info
            
            # Add debug panel with event counts
            openf1_debug = get_openf1_debug_info(timeline)
            openf1_badge += openf1_debug
            
            return status, timeline, summary_text, table_rows, event_html, chart_fig, raw_json_str, openf1_badge
        
        def filter_and_update_table(filter_text, timeline):
            """Apply filter to timeline table."""
            if not timeline:
                return []
            return filter_timeline_table(timeline, filter_text)
        
        def filter_timeline_advanced_handler(
            timeline,
            filter_event_type,
            filter_driver,
            filter_evidence_only,
        ):
            """Apply advanced filters to timeline table."""
            if not timeline:
                return (["Lap", "Type", "Title", "Drivers", "Impact", "Evidence", "Confidence"], [])
            return filter_timeline_advanced(
                timeline,
                filter_event_type=filter_event_type,
                filter_driver=filter_driver,
                filter_evidence_only=filter_evidence_only,
            )
        
        # ====================================================================
        # PRE-DEFINE ALL OUTPUT COMPONENTS (needed for button click handler)
        # ====================================================================
        # We need to define these here so the build_click function can output to them
        
        # Tab 1 outputs
        ingest_status = None
        build_status = None
        detected_metadata = None
        openf1_status = None
        
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
        # TAB 1: UPLOAD & INGEST & AUTO-BUILD
        # ====================================================================
        
        with gr.Tab("📥 Upload & Auto-Build"):
            gr.Markdown(
                "**🟢 Live Mode Active** — Using Ollama for intelligent analysis. "
                "No mock data or fallback modes available."
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
            
            gr.Markdown("### Step 2: Auto-Reconstruct Timeline")
            gr.Markdown("Metadata is automatically detected from your PDF using AI. Timeline reconstruction happens with one click.")
            
            detected_metadata = gr.Textbox(
                label="Auto-Detected Race",
                interactive=False,
                value="Upload PDF and ingest to detect race metadata",
                info="Race year, GP name, and session type (read-only)",
            )
            
            with gr.Row():
                build_btn = gr.Button("🔨 Reconstruct Timeline", variant="primary", scale=1)
                build_status = gr.Textbox(
                    label="Build Status",
                    interactive=False,
                    value="Ready",
                )
            
            openf1_status = gr.Textbox(
                label="OpenF1 Status",
                interactive=False,
                value="🔄 Checking OpenF1 connectivity...",
                info="API health and event counts (PDF + OpenF1 sources)",
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
            
            with gr.Row():
                filter_type = gr.Dropdown(
                    label="Event Type",
                    choices=["All", "SC", "VSC", "RED", "YELLOW", "PIT", "WEATHER", "INCIDENT", "PACE", "STRATEGY", "INFO"],
                    value="All",
                    info="Filter by event type",
                )
                
                filter_driver = gr.Textbox(
                    label="Driver Filter",
                    placeholder="e.g., VER, HAM",
                    info="Leave empty to show all",
                    value="",
                )
                
                filter_evidence_only = gr.Checkbox(
                    label="Only OpenF1 Evidence",
                    value=False,
                    info="Show only events with OpenF1 data",
                )
            
            gr.Markdown("### Timeline Table (click row for details)")
            timeline_table = gr.Dataframe(
                headers=["Lap", "Type", "Title", "Drivers", "Impact", "Evidence", "Confidence"],
                interactive=False,
                wrap=True,
                visible=True,
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
        
        ingest_btn.click(
            fn=ingest_click,
            inputs=[pdf_file, doc_id_input],
            outputs=[ingest_status, detected_metadata],
        )
        
        build_btn.click(
            fn=build_click,
            inputs=[doc_id_input, gr.State(value=None), gr.State(value=None), gr.State(value="RACE")],
            outputs=[build_status, timeline_state, timeline_summary, timeline_table, detail_output, timeline_chart, raw_json, openf1_status],
        )
        
        # Wire advanced timeline filters
        filter_type.change(
            fn=filter_timeline_advanced_handler,
            inputs=[timeline_state, filter_type, filter_driver, filter_evidence_only],
            outputs=[timeline_table],
        )
        
        filter_driver.change(
            fn=filter_timeline_advanced_handler,
            inputs=[timeline_state, filter_type, filter_driver, filter_evidence_only],
            outputs=[timeline_table],
        )
        
        filter_evidence_only.change(
            fn=filter_timeline_advanced_handler,
            inputs=[timeline_state, filter_type, filter_driver, filter_evidence_only],
            outputs=[timeline_table],
        )
        
        # Footer: Live Mode indicator
        gr.Markdown(
            "---\n"
            "**🟢 Live Mode Active**  \n"
            "All analysis uses Ollama for real-time inference. "
            "No mock data or fallback modes available."
        )
    
    return demo


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    # Check Ollama availability at startup (BLOCKING GATE)
    print("\n" + "=" * 70)
    print("F1 Race Intelligence - Checking Ollama...")
    print("=" * 70)
    
    ollama_available = get_ollama_status()
    
    if not ollama_available:
        print("\n❌ STARTUP FAILED: Ollama is not running")
        print("\nStart Ollama with one of these commands:")
        print("  ollama serve")
        print("  ollama run llama3")
        print("\nThen restart this application.")
        print("\n" + "=" * 70 + "\n")
        exit(1)
    
    print("\n✅ Ollama is available. Starting F1 Race Intelligence UI...")
    
    # Create and launch UI
    demo = create_ui()
    
    logger.info("Starting F1 Race Intelligence Gradio UI (Live Mode)...")
    print("\n" + "=" * 70)
    print("🏎️  F1 Race Intelligence - Timeline Reconstruction")
    print("=" * 70)
    print("\nMode: 🟢 LIVE (Ollama-powered inference)")
    # Find available port dynamically
    import socket
    import os
    
    def find_available_port(start_port=7860, max_attempts=50):
        """Find an available port starting from start_port, with wider range and better fallback."""
        # First check environment variable for explicit port override
        env_port = os.environ.get('GRADIO_SERVER_PORT')
        if env_port:
            try:
                port = int(env_port)
                print(f"Using port from GRADIO_SERVER_PORT env var: {port}")
                return port
            except (ValueError, TypeError):
                pass
        
        for port in range(start_port, start_port + max_attempts):
            try:
                # Test both localhost and 0.0.0.0 with SO_REUSEADDR to handle TIME_WAIT
                for addr in ["127.0.0.1", "0.0.0.0"]:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind((addr, port))
                    sock.close()
                
                print(f"Found available port: {port}")
                return port
            except OSError as e:
                continue
        
        # If all specific ports fail, print warning and let OS choose (port 0)
        print("WARNING: Could not find free port in range, using OS-assigned port (0)")
        return 0
    
    available_port = find_available_port()
    if available_port == 0:
        print("\nAll specific ports busy, using OS-assigned port...")
    
    print(f"\nOpen http://localhost in your browser (or check console for actual port)")
    print("\nFeatures:")
    print("  • PDF upload with LLM event extraction")
    print("  • OpenF1 race control & pit stop data integration")
    print("  • Interactive timeline explorer with filters")
    print("  • Evidence visualization (PDF citations + OpenF1 data)")
    print("  • Impact analysis with Ollama inference")
    print("\nStop with Ctrl+C")
    print("=" * 70 + "\n")
    
    demo.launch(
        server_name="0.0.0.0",
        server_port=available_port if available_port > 0 else None,
        share=False,
        show_error=True,
        quiet=False,
    )
