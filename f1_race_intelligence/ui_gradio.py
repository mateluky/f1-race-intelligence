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
        return "<p style='color: gray; text-align: center; padding: 40px;'>👆 Select an event from the Timeline Explorer table to see its details here.</p>"
    
    items = timeline_dict.get("timeline_items", [])
    if selected_row_idx >= len(items):
        return f"<p style='color: red;'>Invalid selection: row {selected_row_idx} (only {len(items)} events available)</p>"
    
    item = items[selected_row_idx]
    
    # Helper to safely get string values
    def safe_str(val, default="N/A"):
        if val is None:
            return default
        if isinstance(val, str):
            return val if val.strip() else default
        if isinstance(val, (list, tuple)):
            return ", ".join(str(x) for x in val) if val else default
        return str(val)
    
    # Get event type and determine color
    event_type = safe_str(item.get('event_type'), '?')
    event_colors = {
        "SC": "#FF3B30",
        "VSC": "#FF9500",
        "RED": "#8B0000",
        "YELLOW": "#FFCC00",
        "PIT": "#007AFF",
        "WEATHER": "#34C759",
        "INCIDENT": "#FF2D55",
        "PACE": "#00C7BE",
        "STRATEGY": "#5856D6",
        "INFO": "#8E8E93",
        "OVERTAKE": "#AF52DE",
        "POSITION": "#30B0C7",
        "RESULT": "#FFD700",
        "GRID": "#64D2FF",
    }
    event_color = event_colors.get(event_type.upper(), "#8E8E93")
    
    # Build HTML details with improved styling
    title = safe_str(item.get('title'), 'Event')
    lap = safe_str(item.get('lap'), '-')
    confidence = safe_str(item.get('confidence'), '?')
    description = safe_str(item.get('description'), 'No description available')
    
    # Impacted drivers
    drivers_list = item.get('impacted_drivers', [])
    if isinstance(drivers_list, list):
        drivers = ", ".join(str(d) for d in drivers_list) if drivers_list else "None"
    else:
        drivers = safe_str(drivers_list, "None")
    
    impact_summary = safe_str(item.get('impact_summary'), 'No impact analysis available')
    
    html = f"""
    <div style="padding: 24px; background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border-radius: 12px; border-left: 5px solid {event_color}; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
        <h2 style="margin: 0 0 16px 0; color: #333;">{title}</h2>
        
        <div style="display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 20px;">
            <div style="background: {event_color}; color: white; padding: 8px 16px; border-radius: 20px; font-weight: bold;">
                {event_type}
            </div>
            <div style="background: #e9ecef; padding: 8px 16px; border-radius: 20px;">
                <strong>Lap:</strong> {lap}
            </div>
            <div style="background: #e9ecef; padding: 8px 16px; border-radius: 20px;">
                <strong>Confidence:</strong> {confidence}
            </div>
        </div>
        
        <div style="background: white; padding: 16px; border-radius: 8px; margin-bottom: 16px;">
            <h4 style="margin: 0 0 8px 0; color: #555;">📝 Description</h4>
            <p style="margin: 0; line-height: 1.6;">{description}</p>
        </div>
        
        <div style="background: white; padding: 16px; border-radius: 8px; margin-bottom: 16px;">
            <h4 style="margin: 0 0 8px 0; color: #555;">🏎️ Impacted Drivers</h4>
            <p style="margin: 0; font-size: 1.1em;">{drivers}</p>
        </div>
        
        <div style="background: white; padding: 16px; border-radius: 8px; margin-bottom: 16px;">
            <h4 style="margin: 0 0 8px 0; color: #555;">📊 Impact Summary</h4>
            <p style="margin: 0; line-height: 1.6;">{impact_summary}</p>
        </div>
    """
    
    # PDF Citations section
    pdf_citations = item.get("pdf_citations", [])
    pdf_count = len(pdf_citations) if isinstance(pdf_citations, list) else 0
    
    html += f"""
        <div style="background: white; padding: 16px; border-radius: 8px; margin-bottom: 16px;">
            <h4 style="margin: 0 0 12px 0; color: #555;">📄 PDF Citations ({pdf_count})</h4>
    """
    
    if pdf_count > 0:
        html += "<ul style='margin: 0; padding-left: 20px;'>"
        for cite in pdf_citations:
            if isinstance(cite, dict):
                snippet = str(cite.get("snippet", ""))[:150]
                score = cite.get("similarity_score", 0)
                try:
                    score_str = f"{float(score):.2f}"
                except (ValueError, TypeError):
                    score_str = "?"
                html += f"<li style='margin-bottom: 8px;'><em>\"{snippet}...\"</em> <span style='color: #888;'>(score: {score_str})</span></li>"
            else:
                html += f"<li style='margin-bottom: 8px;'>{cite}</li>"
        html += "</ul>"
    else:
        html += "<p style='margin: 0; color: #888; font-style: italic;'>No PDF citations for this event</p>"
    
    html += "</div>"
    
    # OpenF1 Evidence section
    openf1_evidence = item.get("openf1_evidence", [])
    openf1_count = len(openf1_evidence) if isinstance(openf1_evidence, list) else 0
    
    html += f"""
        <div style="background: white; padding: 16px; border-radius: 8px;">
            <h4 style="margin: 0 0 12px 0; color: #555;">🔗 OpenF1 Evidence ({openf1_count})</h4>
    """
    
    if openf1_count > 0:
        html += "<ul style='margin: 0; padding-left: 20px;'>"
        for evidence in openf1_evidence:
            if isinstance(evidence, dict):
                etype = safe_str(evidence.get("evidence_type"), "?")
                eid = safe_str(evidence.get("evidence_id"), "-")
                snippet = str(evidence.get("snippet", ""))[:150]
                html += f"<li style='margin-bottom: 8px;'><strong style='color: {event_color};'>{etype}</strong> <span style='color: #888;'>({eid})</span>: <em>\"{snippet}\"</em></li>"
            else:
                html += f"<li style='margin-bottom: 8px;'>{evidence}</li>"
        html += "</ul>"
    else:
        html += "<p style='margin: 0; color: #888; font-style: italic;'>No OpenF1 evidence for this event</p>"
    
    html += """
        </div>
    </div>
    """
    
    return html


# Event type configuration for visualization
EVENT_TYPE_CONFIG = {
    "SC": {"color": "#FF3B30", "symbol": "star", "name": "Safety Car", "size": 16},
    "VSC": {"color": "#FF9500", "symbol": "star-diamond", "name": "Virtual Safety Car", "size": 14},
    "RED": {"color": "#8B0000", "symbol": "x", "name": "Red Flag", "size": 16},
    "YELLOW": {"color": "#FFCC00", "symbol": "triangle-up", "name": "Yellow Flag", "size": 12},
    "PIT": {"color": "#007AFF", "symbol": "square", "name": "Pit Stop", "size": 10},
    "STRATEGY": {"color": "#5856D6", "symbol": "diamond", "name": "Strategy/Stint", "size": 12},
    "WEATHER": {"color": "#34C759", "symbol": "circle", "name": "Weather", "size": 12},
    "INCIDENT": {"color": "#FF2D55", "symbol": "cross", "name": "Incident", "size": 14},
    "PACE": {"color": "#00C7BE", "symbol": "pentagon", "name": "Pace Update", "size": 10},
    "INFO": {"color": "#8E8E93", "symbol": "circle", "name": "Info", "size": 8},
    "OVERTAKE": {"color": "#AF52DE", "symbol": "arrow-up", "name": "Overtake", "size": 12},
    "POSITION": {"color": "#30B0C7", "symbol": "hexagon", "name": "Position", "size": 10},
    "RESULT": {"color": "#FFD700", "symbol": "star-square", "name": "Result", "size": 14},
    "GRID": {"color": "#64D2FF", "symbol": "hourglass", "name": "Grid", "size": 10},
}

# Tire compound colors
COMPOUND_COLORS = {
    "soft": "#FF3B30",
    "medium": "#FFCC00", 
    "hard": "#FFFFFF",
    "intermediate": "#34C759",
    "wet": "#007AFF",
    "unknown": "#8E8E93",
}

# Standard F1 driver mapping (2024 season + common historical drivers)
# Maps driver_number -> name_acronym
F1_DRIVER_NUMBERS = {
    1: "VER", 11: "PER",  # Red Bull
    44: "HAM", 63: "RUS",  # Mercedes
    16: "LEC", 55: "SAI",  # Ferrari
    4: "NOR", 81: "PIA",  # McLaren
    14: "ALO", 18: "STR",  # Aston Martin
    10: "GAS", 31: "OCO",  # Alpine
    23: "ALB", 2: "SAR",  # Williams
    77: "BOT", 24: "ZHO",  # Alfa Romeo / Kick Sauber
    20: "MAG", 27: "HUL",  # Haas
    22: "TSU", 3: "RIC", 30: "LAW",  # AlphaTauri / RB
    # Historical / reserve / F2 drivers
    5: "VET", 6: "LAT", 7: "RAI", 8: "GRO", 9: "MAZ",
    12: "DEV", 17: "GIO", 21: "NYK", 26: "KVY", 28: "HAR",
    35: "FIT", 38: "DRU", 39: "SHW", 40: "SVG", 41: "BEA",
    42: "MAR", 43: "FRA", 45: "DEV", 46: "COR", 47: "MSC",
    50: "IWA", 51: "BOR", 52: "HAD", 53: "DOO", 54: "ANT",
    61: "DAR", 62: "POE", 64: "BEA", 65: "MAL", 66: "VES",
    78: "AIK", 84: "MEA", 85: "SAR", 87: "SHW", 88: "KUB",
    89: "COL", 90: "VAN", 91: "POU", 92: "MAR", 93: "MIN",
    94: "PAS", 95: "MER", 96: "VER", 97: "DUC", 98: "DRO", 99: "GIO",
}

# Reverse mapping: name_acronym -> driver_number (use current numbers)
F1_DRIVER_NAMES = {
    "VER": 1, "PER": 11,
    "HAM": 44, "RUS": 63,
    "LEC": 16, "SAI": 55,
    "NOR": 4, "PIA": 81,
    "ALO": 14, "STR": 18,
    "GAS": 10, "OCO": 31,
    "ALB": 23, "SAR": 2,
    "BOT": 77, "ZHO": 24,
    "MAG": 20, "HUL": 27,
    "TSU": 22, "RIC": 3, "LAW": 30,
    "VET": 5, "LAT": 6, "RAI": 7, "GRO": 8, "MAZ": 9,
    "DEV": 12, "GIO": 17, "NYK": 21, "KVY": 26, "HAR": 28,
    "FIT": 35, "DRU": 38, "SHW": 39, "SVG": 40, "BEA": 41,
    "MAR": 42, "FRA": 43, "COR": 46, "MSC": 47,
    "IWA": 50, "BOR": 51, "HAD": 52, "DOO": 53, "ANT": 54,
    "DAR": 61, "POE": 62, "MAL": 65, "VES": 66,
    "AIK": 78, "MEA": 84, "KUB": 88, "COL": 89, "VAN": 90,
    "POU": 91, "MIN": 93, "PAS": 94, "MER": 95, "DUC": 97, "DRO": 98,
}


def create_timeline_chart(
    timeline_dict: Optional[Dict], 
    selected_types: Optional[List[str]] = None
) -> Optional[go.Figure]:
    """Create Plotly chart of timeline events with all event types and filtering.
    
    Shows:
    - Y-axis: driver names / event categories
    - X-axis: lap number
    - Different markers for each event type with distinct colors and symbols
    - Interactive legend for filtering
    
    Args:
        timeline_dict: Timeline JSON
        selected_types: List of event types to show (None = all)
        
    Returns:
        Plotly figure or None
    """
    if not timeline_dict:
        return None
    
    items = timeline_dict.get("timeline_items", [])
    if not items:
        return None
    
    # Default to all types if none selected
    if not selected_types or "All" in selected_types:
        selected_types = list(EVENT_TYPE_CONFIG.keys())
    
    try:
        fig = go.Figure()
        
        # Build driver number <-> name mapping from the data
        # Format: "NAME (##)" e.g., "VER (1)", "HAM (44)"
        driver_number_to_name = dict(F1_DRIVER_NUMBERS)  # Start with known mappings
        driver_name_to_number = dict(F1_DRIVER_NAMES)    # Start with known mappings
        
        # Scan all items for driver information from OpenF1 evidence
        for item in items:
            # Check evidence for driver details
            evidence_list = item.get("openf1_evidence", []) or item.get("evidence", [])
            for ev in evidence_list:
                if isinstance(ev, dict):
                    payload = ev.get("payload", {})
                    if isinstance(payload, dict):
                        driver_num = payload.get("driver_number")
                        driver_name = payload.get("driver_name") or payload.get("name_acronym")
                        if driver_num and driver_name:
                            driver_number_to_name[driver_num] = driver_name
                            driver_name_to_number[driver_name] = driver_num
                        # Also check for broadcast_name
                        broadcast = payload.get("broadcast_name")
                        if driver_num and broadcast and not driver_name:
                            # Extract 3-letter code from broadcast name if possible
                            parts = broadcast.upper().split()
                            if parts:
                                code = parts[-1][:3] if len(parts[-1]) >= 3 else parts[-1]
                                driver_number_to_name[driver_num] = code
                                driver_name_to_number[code] = driver_num
        
        # Track unknown drivers to assign sequential numbers
        unknown_driver_counter = 100
        unknown_name_to_number = {}
        
        def normalize_driver(driver_ref: str) -> str:
            """Normalize driver reference to 'NAME (##)' format."""
            nonlocal unknown_driver_counter
            
            if not driver_ref:
                return "Unknown"
            
            # If already in correct format (has number in parens), return as-is
            if "(" in driver_ref and ")" in driver_ref:
                return driver_ref
            
            # Handle "Driver ##" format
            if driver_ref.startswith("Driver "):
                try:
                    num = int(driver_ref.replace("Driver ", ""))
                    name = driver_number_to_name.get(num)
                    if name and not str(name).startswith("#"):
                        return f"{name} ({num})"
                    # Keep as "Driver ##" format but with actual number
                    return f"DRV ({num})"
                except:
                    return driver_ref
            
            # Handle pure number
            if driver_ref.isdigit():
                num = int(driver_ref)
                name = driver_number_to_name.get(num)
                if name and not str(name).startswith("#"):
                    return f"{name} ({num})"
                return f"DRV ({num})"
            
            # Handle name abbreviation (VER, HAM, etc.) - uppercase 3-letter codes
            driver_upper = driver_ref.upper().strip()
            
            # Check local and global mapping
            num = driver_name_to_number.get(driver_ref) or driver_name_to_number.get(driver_upper)
            if num:
                return f"{driver_upper} ({num})"
            
            # For unknown drivers, assign a sequential number if we haven't seen them
            if driver_upper not in unknown_name_to_number:
                unknown_name_to_number[driver_upper] = unknown_driver_counter
                unknown_driver_counter += 1
            
            return f"{driver_upper} ({unknown_name_to_number[driver_upper]})"
        
        # Pre-scan all drivers to build the unknown mapping consistently
        all_raw_drivers = set()
        for item in items:
            drivers = item.get("impacted_drivers", [])
            for d in drivers:
                if isinstance(d, str):
                    all_raw_drivers.add(d)
        
        # Normalize all drivers
        for d in sorted(all_raw_drivers):
            normalize_driver(d)  # This populates unknown_name_to_number
        
        # Collect all drivers and event types found in data
        all_drivers = set()
        events_by_type = {}
        
        for item in items:
            event_type = item.get("event_type", "INFO")
            drivers = item.get("impacted_drivers", [])
            for d in drivers:
                normalized = normalize_driver(d)
                all_drivers.add(normalized)
            
            if event_type not in events_by_type:
                events_by_type[event_type] = []
            events_by_type[event_type].append(item)
        
        # Sort drivers: first by name (alphabetically), handling the format "NAME (##)"
        def driver_sort_key(d):
            # Extract name part for sorting
            if "(" in d:
                name = d.split("(")[0].strip()
                return (0, name.lower())  # Named drivers first
            elif d.startswith("Driver "):
                return (1, d)  # "Driver ##" second
            return (2, d.lower())  # Others last
        
        sorted_drivers = sorted(list(all_drivers), key=driver_sort_key) if all_drivers else ["RACE"]
        
        # Track which legend entries we've added (one per event type)
        legend_added = set()
        
        # First pass: find max lap to estimate positions for events without lap
        max_lap = 1
        events_with_lap = 0
        events_without_lap = 0
        for item in items:
            lap = item.get("lap")
            if lap is not None and lap != 999:  # 999 is used for end-of-race results
                max_lap = max(max_lap, lap)
                events_with_lap += 1
            else:
                events_without_lap += 1
        
        logger.debug(f"[CHART] Events with lap: {events_with_lap}, without lap: {events_without_lap}, max_lap: {max_lap}")
        
        # Counter for distributing events without lap across the timeline
        no_lap_counter = {}
        
        # Process events by type for better layering
        for event_type in selected_types:
            if event_type not in events_by_type:
                continue
            
            config = EVENT_TYPE_CONFIG.get(event_type, EVENT_TYPE_CONFIG["INFO"])
            events = events_by_type[event_type]
            
            for idx, event in enumerate(events):
                lap = event.get("lap")
                
                # Handle events without lap - distribute them across the timeline
                if lap is None:
                    # Distribute events evenly across the race
                    if event_type not in no_lap_counter:
                        no_lap_counter[event_type] = 0
                    no_lap_counter[event_type] += 1
                    
                    # Spread events of this type across 10% to 90% of the race
                    num_events = len([e for e in events if e.get("lap") is None])
                    if num_events > 0:
                        position_fraction = 0.1 + (0.8 * no_lap_counter[event_type] / max(num_events, 1))
                        lap = int(position_fraction * max_lap)
                    else:
                        lap = max_lap // 2  # Default to mid-race
                elif lap == 999:
                    # End-of-race events (results) - place at the end
                    lap = max_lap + 1
                
                title = event.get("title", "")
                description = event.get("description", "")[:100] if event.get("description") else ""
                drivers = event.get("impacted_drivers", [])
                confidence = event.get("confidence_score", 0.5)
                evidence = event.get("evidence", [])
                has_evidence = bool(evidence)
                
                # Adjust marker based on confidence
                opacity = 0.5 + (confidence * 0.5)  # 0.5 to 1.0
                
                # Special handling for STRATEGY events - parse tire compound
                marker_color = config["color"]
                if event_type == "STRATEGY":
                    compounds_found = [c for c in COMPOUND_COLORS.keys() if c in description.lower()]
                    if compounds_found:
                        marker_color = COMPOUND_COLORS.get(compounds_found[-1], config["color"])
                
                # Add evidence indicator to marker
                marker_line = dict(width=2, color="lime") if has_evidence else dict(width=1, color="rgba(0,0,0,0.3)")
                
                # Show legend only for first occurrence of each type
                show_legend = event_type not in legend_added
                if show_legend:
                    legend_added.add(event_type)
                
                # If event has drivers, show at each driver's row
                if drivers:
                    for i, driver in enumerate(drivers):
                        # Normalize driver name to "NAME (##)" format
                        normalized_driver = normalize_driver(driver)
                        # Slight x offset for multiple events at same lap
                        x_offset = i * 0.15
                        
                        fig.add_trace(
                            go.Scatter(
                                x=[lap + x_offset],
                                y=[normalized_driver],
                                mode="markers",
                                marker=dict(
                                    size=config["size"],
                                    color=marker_color,
                                    symbol=config["symbol"],
                                    opacity=opacity,
                                    line=marker_line,
                                ),
                                name=config["name"],
                                legendgroup=event_type,
                                showlegend=show_legend and (i == 0),
                                hovertemplate=(
                                    f"<b>{title}</b><br>"
                                    f"Type: {config['name']}<br>"
                                    f"Lap: {lap}<br>"
                                    f"Driver: {normalized_driver}"
                                    f"<extra></extra>"
                                ),
                            )
                        )
                else:
                    # Race-wide event - show on "RACE" row at top
                    fig.add_trace(
                        go.Scatter(
                            x=[lap],
                            y=["🏁 RACE"],
                            mode="markers",
                            marker=dict(
                                size=config["size"] + 4,
                                color=marker_color,
                                symbol=config["symbol"],
                                opacity=opacity,
                                line=marker_line,
                            ),
                            name=config["name"],
                            legendgroup=event_type,
                            showlegend=show_legend,
                            hovertemplate=(
                                f"<b>{title}</b><br>"
                                f"Type: {config['name']}<br>"
                                f"Lap: {lap}"
                                f"<extra></extra>"
                            ),
                        )
                    )
        
        # Build y-axis category order
        y_categories = ["🏁 RACE"] + sorted_drivers
        
        # Update layout with improved styling
        fig.update_layout(
            title=dict(
                text="🏎️ Race Timeline: All Events by Lap",
                font=dict(size=20, color="#333"),
                x=0.5,
                xanchor="center",
            ),
            xaxis=dict(
                title="Lap Number",
                tickmode="linear",
                dtick=5,
                gridcolor="rgba(0,0,0,0.1)",
                showgrid=True,
                zeroline=False,
            ),
            yaxis=dict(
                title="Driver / Event Category",
                categoryorder="array",
                categoryarray=y_categories,
                gridcolor="rgba(0,0,0,0.05)",
                showgrid=True,
            ),
            hovermode="closest",
            height=max(600, len(y_categories) * 25 + 150),
            margin=dict(t=80, b=60, l=120, r=200),
            template="plotly_white",
            legend=dict(
                title=dict(text="Event Types", font=dict(size=14)),
                orientation="v",
                yanchor="top",
                y=1,
                xanchor="left",
                x=1.02,
                bgcolor="rgba(255,255,255,0.9)",
                bordercolor="rgba(0,0,0,0.1)",
                borderwidth=1,
                font=dict(size=11),
                itemsizing="constant",
            ),
            plot_bgcolor="rgba(248,249,250,1)",
            paper_bgcolor="white",
        )
        
        # Add gridlines for major laps
        fig.update_xaxes(
            showline=True,
            linewidth=1,
            linecolor="rgba(0,0,0,0.2)",
            mirror=True,
        )
        fig.update_yaxes(
            showline=True,
            linewidth=1,
            linecolor="rgba(0,0,0,0.2)",
            mirror=True,
        )
        
        return fig
    
    except Exception as e:
        logger.warning(f"Failed to create timeline chart: {e}")
        return None


def get_available_event_types(timeline_dict: Optional[Dict]) -> List[str]:
    """Get list of event types present in the timeline data.
    
    Args:
        timeline_dict: Timeline JSON
        
    Returns:
        List of event type strings found in data
    """
    if not timeline_dict:
        return []
    
    items = timeline_dict.get("timeline_items", [])
    types_found = set()
    for item in items:
        et = item.get("event_type", "INFO")
        types_found.add(et)
    
    return sorted(list(types_found))


def update_visualization_chart(
    timeline_dict: Optional[Dict],
    sc: bool, vsc: bool, red: bool, yellow: bool, pit: bool,
    strategy: bool, weather: bool, incident: bool, overtake: bool, pace: bool,
    position: bool, result: bool, grid: bool, info: bool
) -> Optional[go.Figure]:
    """Update the visualization chart based on selected event type filters.
    
    Args:
        timeline_dict: Timeline JSON data
        sc-info: Boolean filters for each event type
        
    Returns:
        Updated Plotly figure
    """
    # Build list of selected types based on checkboxes
    selected_types = []
    if sc: selected_types.append("SC")
    if vsc: selected_types.append("VSC")
    if red: selected_types.append("RED")
    if yellow: selected_types.append("YELLOW")
    if pit: selected_types.append("PIT")
    if strategy: selected_types.append("STRATEGY")
    if weather: selected_types.append("WEATHER")
    if incident: selected_types.append("INCIDENT")
    if overtake: selected_types.append("OVERTAKE")
    if pace: selected_types.append("PACE")
    if position: selected_types.append("POSITION")
    if result: selected_types.append("RESULT")
    if grid: selected_types.append("GRID")
    if info: selected_types.append("INFO")
    
    # If nothing selected, show empty chart message
    if not selected_types:
        fig = go.Figure()
        fig.add_annotation(
            text="No event types selected. Check some filters above.",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=16, color="gray")
        )
        fig.update_layout(
            height=300,
            template="plotly_white",
        )
        return fig
    
    return create_timeline_chart(timeline_dict, selected_types)


def generate_event_counts_html(timeline_dict: Optional[Dict]) -> str:
    """Generate HTML showing counts of each event type in the timeline.
    
    Args:
        timeline_dict: Timeline JSON data
        
    Returns:
        HTML string with colored badges showing event counts
    """
    if not timeline_dict:
        return "<p style='color: gray; font-style: italic;'>No timeline data available</p>"
    
    items = timeline_dict.get("timeline_items", [])
    if not items:
        return "<p style='color: gray; font-style: italic;'>No events in timeline</p>"
    
    # Count events by type
    counts = {}
    for item in items:
        et = item.get("event_type", "INFO")
        counts[et] = counts.get(et, 0) + 1
    
    # Generate badge HTML for each type
    badges = []
    for event_type, count in sorted(counts.items(), key=lambda x: -x[1]):
        config = EVENT_TYPE_CONFIG.get(event_type, EVENT_TYPE_CONFIG["INFO"])
        color = config["color"]
        name = config["name"]
        badges.append(
            f'<span style="display: inline-block; background: {color}; color: white; '
            f'padding: 4px 12px; border-radius: 12px; margin: 3px; font-size: 12px; '
            f'font-weight: bold; box-shadow: 0 1px 3px rgba(0,0,0,0.2);">'
            f'{name}: {count}</span>'
        )
    
    total = len(items)
    html = f"""
    <div style="padding: 12px; background: #f8f9fa; border-radius: 8px; margin-bottom: 10px;">
        <strong style="color: #333;">📊 Total Events: {total}</strong>
        <div style="margin-top: 8px;">
            {''.join(badges)}
        </div>
    </div>
    """
    return html


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
    if not items:
        return (
            ["Lap", "Type", "Title", "Drivers", "Impact", "Evidence", "Confidence"],
            []
        )
    
    filtered_items = []
    for item in items:
        try:
            # Type filter - handle None and empty string cases
            if filter_event_type and filter_event_type != "All":
                item_type = str(item.get("event_type", "") or "").upper().strip()
                filter_type = str(filter_event_type).upper().strip()
                if item_type != filter_type:
                    continue
            
            # Driver filter - handle None and empty string cases
            if filter_driver and str(filter_driver).strip():
                drivers = item.get("impacted_drivers") or []
                if not isinstance(drivers, list):
                    drivers = [str(drivers)] if drivers else []
                filter_driver_upper = str(filter_driver).upper().strip()
                if not any(filter_driver_upper in str(d or "").upper() for d in drivers):
                    continue
            
            # Evidence filter
            if filter_evidence_only:
                openf1_evidence = item.get("openf1_evidence") or []
                if not isinstance(openf1_evidence, list):
                    openf1_evidence = []
                if len(openf1_evidence) == 0:
                    continue
            
            filtered_items.append(item)
        except Exception as e:
            # Log but don't fail on individual item errors
            logger.warning(f"Error filtering item: {e}")
            continue
    
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
    
    CRITICAL: Never return tuples, lists, or dicts as cell values - Gradio cannot process them.
    
    Args:
        timeline_items: List of timeline item dicts
        
    Returns:
        (columns, rows) tuple where rows are lists of primitives (no objects/dicts/tuples)
    """
    columns = ["Lap", "Type", "Title", "Drivers", "Impact", "Evidence", "Confidence"]
    
    if not timeline_items:
        return (columns, [])
    
    if not isinstance(timeline_items, list):
        logger.warning(f"timeline_items is not a list: {type(timeline_items)}")
        return (columns, [])
    
    rows = []
    
    for item in timeline_items:
        try:
            if not isinstance(item, dict):
                logger.warning(f"Skipping non-dict item: {type(item)}")
                continue
                
            # Flatten all fields to primitives only - use helper to ensure string output
            def safe_str(val, default=""):
                """Safely convert any value to string, handling None, tuples, lists, dicts."""
                if val is None:
                    return default
                if isinstance(val, str):
                    return val
                if isinstance(val, (int, float, bool)):
                    return str(val)
                if isinstance(val, (list, tuple)):
                    return ", ".join(safe_str(x) for x in val)
                if isinstance(val, dict):
                    return str(val)
                # Fallback for any other type
                return str(val)
            
            # Lap - ensure it's a string
            lap_val = item.get("lap")
            lap = safe_str(lap_val, "-") if lap_val is not None else "-"
            
            # Event type - guaranteed to be a pure string
            event_type = safe_str(item.get("event_type"), "?")
            
            # Title
            title = safe_str(item.get("title"), "")
            
            # Join drivers into single string - handle various formats
            drivers_raw = item.get("impacted_drivers")
            if drivers_raw is None:
                drivers = ""
            elif isinstance(drivers_raw, str):
                drivers = drivers_raw
            elif isinstance(drivers_raw, (list, tuple)):
                drivers = ", ".join(safe_str(d) for d in drivers_raw if d)
            else:
                drivers = safe_str(drivers_raw)
            
            # Impact summary (benefited/hurt drivers)
            impact_raw = item.get("impact_summary")
            impact = safe_str(impact_raw, "").strip()
            if not impact:
                impact = "—"
            
            # Count evidence sources and represent as string
            pdf_citations = item.get("pdf_citations")
            openf1_evidence = item.get("openf1_evidence")
            pdf_count = len(pdf_citations) if isinstance(pdf_citations, list) else 0
            openf1_count = len(openf1_evidence) if isinstance(openf1_evidence, list) else 0
            evidence_str = f"PDF:{pdf_count} | OpenF1:{openf1_count}" if (pdf_count + openf1_count) > 0 else "—"
            
            # Confidence
            confidence = safe_str(item.get("confidence"), "?")
            
            # All values must be primitives (str/int/float/bool), not objects or dicts
            # Double-check all are strings to prevent tuple errors
            row = [
                str(lap),
                str(event_type),
                str(title),
                str(drivers),
                str(impact),
                str(evidence_str),
                str(confidence)
            ]
            rows.append(row)
            
        except Exception as e:
            logger.warning(f"Error converting timeline item to table row: {e}")
            # Add a placeholder row on error
            rows.append(["-", "ERROR", str(e)[:50], "", "—", "—", "?"])
    
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
            
            # Generate event counts HTML for visualization tab
            event_counts_html = generate_event_counts_html(timeline)
            
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
            
            return status, timeline, summary_text, table_rows, event_html, chart_fig, raw_json_str, openf1_badge, event_counts_html
        
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
            """Apply advanced filters to timeline table.
            
            Returns only the rows (not columns tuple) for Gradio Dataframe compatibility.
            All values are converted to primitives to avoid tuple/object errors.
            """
            if not timeline:
                return []  # Return empty list, not tuple - Gradio will use existing headers
            
            # Get filtered results as (columns, rows) tuple
            columns, rows = filter_timeline_advanced(
                timeline,
                filter_event_type=filter_event_type,
                filter_driver=filter_driver,
                filter_evidence_only=filter_evidence_only,
            )
            
            # Ensure all values in rows are primitives (str/int/float/bool)
            # This prevents "Cannot process value of type tuple" errors
            safe_rows = []
            for row in rows:
                safe_row = []
                for cell in row:
                    if cell is None:
                        safe_row.append("")
                    elif isinstance(cell, (str, int, float, bool)):
                        safe_row.append(cell)
                    elif isinstance(cell, (list, tuple)):
                        # Convert lists/tuples to comma-separated string
                        safe_row.append(", ".join(str(x) for x in cell))
                    elif isinstance(cell, dict):
                        # Convert dicts to string representation
                        safe_row.append(str(cell))
                    else:
                        # Fallback: convert to string
                        safe_row.append(str(cell))
                safe_rows.append(safe_row)
            
            return safe_rows  # Return only rows, not (columns, rows) tuple
        
        def on_table_row_select(timeline, evt: gr.SelectData):
            """Handle table row selection to show event details.
            
            Args:
                timeline: Timeline state dict
                evt: Gradio SelectData event containing row/column info
                
            Returns:
                HTML string with event details
            """
            if not timeline or evt is None:
                return "<p style='color: gray; text-align: center; padding: 40px;'>👆 Select an event from the Timeline Explorer table to see its details here.</p>"
            
            # Get the selected row index
            row_idx = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
            
            # Get event details using the existing function
            return get_event_details(timeline, row_idx)
        
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
                    choices=["All", "SC", "VSC", "RED", "YELLOW", "PIT", "WEATHER", "INCIDENT", "PACE", "STRATEGY", "OVERTAKE", "POSITION", "RESULT", "GRID", "INFO"],
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
                row_count=(10, "dynamic"),
            )
            
            # Selected row index state (for event details)
            selected_row_index = gr.State(value=-1)
        
        # ====================================================================
        # TAB 3: EVENT DETAILS
        # ====================================================================
        
        with gr.Tab("🔍 Event Details"):
            gr.Markdown("### Selected Event Details")
            gr.Markdown("*Click on a row in the Timeline Explorer table to view detailed information about that event.*")
            
            detail_output = gr.HTML(
                value="<p style='color: gray; text-align: center; padding: 40px;'>👆 Select an event from the Timeline Explorer table to see its details here.</p>",
                label="Event Details",
            )
        
        # ====================================================================
        # TAB 4: VISUALIZATION
        # ====================================================================
        
        with gr.Tab("📈 Visualization"):
            gr.Markdown("### 🏎️ Race Timeline Chart")
            gr.Markdown(
                "*Interactive visualization of all race events. Use the filters below to focus on specific event types. "
                "Hover over markers for details. Events with **green borders** have OpenF1 API evidence.*"
            )
            
            # Event type filters - organized by category with integrated color indicators
            gr.HTML("""
            <style>
                .filter-section { 
                    background: #f8f9fa; 
                    border-radius: 8px; 
                    padding: 12px 16px; 
                    margin-bottom: 10px;
                }
                .filter-title {
                    font-weight: 600;
                    font-size: 13px;
                    color: #555;
                    margin-bottom: 8px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }
            </style>
            """)
            
            # Section 1: Race Control (Safety-related)
            gr.HTML("""
            <div class="filter-section">
                <div class="filter-title">🚨 Race Control</div>
            </div>
            """)
            with gr.Row():
                viz_filter_sc = gr.Checkbox(label="🔴 Safety Car", value=True, scale=1)
                viz_filter_vsc = gr.Checkbox(label="🟠 VSC", value=True, scale=1)
                viz_filter_red = gr.Checkbox(label="🟤 Red Flag", value=True, scale=1)
                viz_filter_yellow = gr.Checkbox(label="🟡 Yellow Flag", value=True, scale=1)
                viz_filter_incident = gr.Checkbox(label="💥 Incident", value=True, scale=1)
            
            # Section 2: Strategy & Pit
            gr.HTML("""
            <div class="filter-section">
                <div class="filter-title">🔧 Strategy & Pit Stops</div>
            </div>
            """)
            with gr.Row():
                viz_filter_pit = gr.Checkbox(label="🔵 Pit Stop", value=True, scale=1)
                viz_filter_strategy = gr.Checkbox(label="💜 Stint Change", value=True, scale=1)
                viz_filter_pace = gr.Checkbox(label="🩵 Pace Update", value=True, scale=1)
                viz_filter_overtake = gr.Checkbox(label="🟣 Overtake", value=True, scale=1)
                viz_filter_weather = gr.Checkbox(label="🟢 Weather", value=True, scale=1)
            
            # Section 3: Session Info
            gr.HTML("""
            <div class="filter-section">
                <div class="filter-title">📋 Session Info</div>
            </div>
            """)
            with gr.Row():
                viz_filter_grid = gr.Checkbox(label="🏁 Starting Grid", value=True, scale=1)
                viz_filter_result = gr.Checkbox(label="🏆 Results", value=True, scale=1)
                viz_filter_position = gr.Checkbox(label="📊 Position", value=False, scale=1)
                viz_filter_info = gr.Checkbox(label="ℹ️ Info", value=False, scale=1)
            
            with gr.Row():
                viz_select_all = gr.Button("✅ Select All", size="sm", variant="secondary", scale=1)
                viz_clear_all = gr.Button("❌ Clear All", size="sm", variant="secondary", scale=1)
            
            # Event counts summary
            viz_event_counts = gr.HTML(
                value="<p style='color: gray; font-style: italic;'>Build a timeline to see event counts</p>",
                label="Event Counts",
            )
            
            # Chart output
            timeline_chart = gr.Plot(label="Timeline Chart")
            
            # Legend description
            gr.Markdown(
                """
                ---
                **Legend Notes:**
                - **Marker shapes** differ by event type (stars = SC/VSC, diamonds = strategy, squares = pit, etc.)
                - **Marker opacity** reflects confidence score (more opaque = higher confidence)
                - **Green border** indicates OpenF1 API evidence; gray border = PDF only
                - **🏁 RACE row** shows race-wide events not tied to specific drivers
                """
            )
        
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
            outputs=[build_status, timeline_state, timeline_summary, timeline_table, detail_output, timeline_chart, raw_json, openf1_status, viz_event_counts],
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
        
        # Wire table row selection to show event details
        timeline_table.select(
            fn=on_table_row_select,
            inputs=[timeline_state],
            outputs=[detail_output],
        )
        
        # ====================================================================
        # WIRE VISUALIZATION FILTERS
        # ====================================================================
        
        # List of all visualization filter checkboxes
        viz_filter_inputs = [
            timeline_state,
            viz_filter_sc, viz_filter_vsc, viz_filter_red, viz_filter_yellow, viz_filter_pit,
            viz_filter_strategy, viz_filter_weather, viz_filter_incident, viz_filter_overtake, viz_filter_pace,
            viz_filter_position, viz_filter_result, viz_filter_grid, viz_filter_info
        ]
        
        # Wire each checkbox to update the chart
        for checkbox in [
            viz_filter_sc, viz_filter_vsc, viz_filter_red, viz_filter_yellow, viz_filter_pit,
            viz_filter_strategy, viz_filter_weather, viz_filter_incident, viz_filter_overtake, viz_filter_pace,
            viz_filter_position, viz_filter_result, viz_filter_grid, viz_filter_info
        ]:
            checkbox.change(
                fn=update_visualization_chart,
                inputs=viz_filter_inputs,
                outputs=[timeline_chart],
            )
        
        # Select All button functionality
        def select_all_filters():
            return [True] * 14  # Return True for all 14 filter checkboxes
        
        viz_select_all.click(
            fn=select_all_filters,
            inputs=[],
            outputs=[
                viz_filter_sc, viz_filter_vsc, viz_filter_red, viz_filter_yellow, viz_filter_pit,
                viz_filter_strategy, viz_filter_weather, viz_filter_incident, viz_filter_overtake, viz_filter_pace,
                viz_filter_position, viz_filter_result, viz_filter_grid, viz_filter_info
            ],
        )
        
        # Clear All button functionality
        def clear_all_filters():
            return [False] * 14  # Return False for all 14 filter checkboxes
        
        viz_clear_all.click(
            fn=clear_all_filters,
            inputs=[],
            outputs=[
                viz_filter_sc, viz_filter_vsc, viz_filter_red, viz_filter_yellow, viz_filter_pit,
                viz_filter_strategy, viz_filter_weather, viz_filter_incident, viz_filter_overtake, viz_filter_pace,
                viz_filter_position, viz_filter_result, viz_filter_grid, viz_filter_info
            ],
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
