"""Timeline reconstruction combining PDF events and OpenF1 data.

This module handles:
1. Extracting events from PDF via LLM with RAG citations
2. Building normalized timeline from OpenF1 API data
3. Merging and deduplicating events
4. Computing impact (winners/losers) for key events
"""

import logging
import json
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
from datetime import datetime

from rag.schemas import (
    TimelineItem,
    TimelineEventType,
    PDFCitation,
    OpenF1Evidence,
    RaceTimeline,
)
from rag.retrieve import Retriever
from rag.llm import LLMInterface

logger = logging.getLogger(__name__)


class TimelineBuilder:
    """Orchestrates timeline reconstruction from PDF and OpenF1."""

    def __init__(self, retriever: Retriever, llm: LLMInterface):
        """Initialize timeline builder.
        
        Args:
            retriever: Vector store retriever for PDF citations
            llm: LLM instance for extracting events from PDF
        """
        self.retriever = retriever
        self.llm = llm
        # Debug info captured during build
        self.debug_info: Dict[str, Any] = {}

    def extract_pdf_events(
        self,
        doc_id: str,
        session_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[TimelineItem]:
        """Extract timeline events from PDF with RAG citations.
        
        Args:
            doc_id: Document ID in vector store
            session_metadata: Session info (year, gp, etc.) for context
            
        Returns:
            List of TimelineItem objects with PDF citations
        """
        logger.info(f"Extracting PDF events from {doc_id}")
        
        # Construct prompt for LLM
        session_context = ""
        if session_metadata:
            session_context = f"""
            Session context:
            - Year: {session_metadata.get('year', 'N/A')}
            - GP: {session_metadata.get('gp_name', 'N/A')}
            - Type: {session_metadata.get('session_type', 'RACE')}
            """
        
        extraction_prompt = f"""
        Analyze this F1 race document and extract KEY TIMELINE EVENTS.
        
        For each event, output JSON with:
        - lap: lap number (integer, null if not mentioned)
        - event_type: one of SC, VSC, RED, YELLOW, PIT, WEATHER, INCIDENT, PACE_CHANGE, INFO
        - title: short title (5-10 words)
        - description: detailed description (1-2 sentences)
        - search_query: keywords to retrieve PDF citations
        
        Look for:
        - Safety car / Virtual SC deployments
        - Red flag / Yellow flag periods
        - Pit stop strategies and timing
        - Weather changes
        - On-track incidents
        - Major pace changes or overtakes
        - Penalties or technical issues
        
        {session_context}
        
        Output as JSON array. Example:
        [
            {{"lap": 15, "event_type": "SC", "title": "Safety Car Deployed", "description": "SC deployed after incident at turn 3", "search_query": "safety car lap 15 incident"}},
            {{"lap": 18, "event_type": "PIT", "title": "Lead Driver Pits", "description": "Leader boxes for tire change", "search_query": "pit stop soft compound"}}
        ]
        
        Now analyze the document and extract events:
        """
        
        # Call LLM to extract events as JSON
        try:
            response_text = self.llm.generate(
                extraction_prompt,
                system_prompt="You are an F1 race analyst. Extract key timeline events from race documents.",
                temperature=0.3,  # Lower temp for more structured output
            )
            
            # Parse JSON from response
            events_data = self._parse_json_events(response_text)
        except Exception as e:
            logger.error(f"Failed to extract PDF events: {e}")
            return []
        
        # Convert to TimelineItems with PDF citations
        timeline_items = []
        for event_data in events_data:
            try:
                item = self._event_to_timeline_item(event_data, doc_id)
                timeline_items.append(item)
            except Exception as e:
                logger.warning(f"Failed to convert event: {e}")
                continue
        
        logger.info(f"Extracted {len(timeline_items)} PDF events")
        return timeline_items

    def _parse_json_events(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse JSON event data from LLM response.
        
        Args:
            response_text: Raw response from LLM
            
        Returns:
            List of parsed event dictionaries
        """
        # Try to extract JSON array
        if "[" not in response_text or "]" not in response_text:
            logger.warning("No JSON array found in response")
            return []
        
        start = response_text.find("[")
        end = response_text.rfind("]") + 1
        json_str = response_text[start:end]
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return []

    def _event_to_timeline_item(
        self,
        event_data: Dict[str, Any],
        doc_id: str,
    ) -> TimelineItem:
        """Convert LLM-extracted event to TimelineItem with citations.
        
        Args:
            event_data: Event dict from LLM
            doc_id: Document ID for retrieval
            
        Returns:
            TimelineItem with PDF citations
        """
        # Extract basic fields
        lap = event_data.get("lap")
        event_type_str = event_data.get("event_type", "INFO").upper()
        title = event_data.get("title", "Event")
        description = event_data.get("description", "")
        search_query = event_data.get("search_query", description)
        
        # Map event type
        try:
            event_type = TimelineEventType(event_type_str)
        except ValueError:
            event_type = TimelineEventType.INFO
        
        # Retrieve PDF citations
        pdf_citations = []
        try:
            # Query retriever with search keywords
            results = self.retriever.retrieve(search_query, top_k=3)
            
            for chunk, score in zip(results.chunks, results.scores):
                citation = PDFCitation(
                    chunk_id=chunk.id,
                    snippet=chunk.content[:200],  # Truncate to 200 chars
                    similarity_score=float(score),
                    page_num=chunk.metadata.get("page_num"),
                )
                pdf_citations.append(citation)
        except Exception as e:
            logger.warning(f"Failed to retrieve citations: {e}")
        
        # Create TimelineItem
        return TimelineItem(
            lap=lap,
            timestamp=None,  # Will be filled by OpenF1 timeline if available
            event_type=event_type,
            title=title,
            description=description,
            pdf_citations=pdf_citations,
            openf1_evidence=[],  # Will be filled by merge step
            impacted_drivers=[],  # Will be filled by impact step
            impact_summary="",
            confidence="Medium" if pdf_citations else "Low",
        )

    def build_openf1_timeline(
        self,
        openf1_client: Any,  # OpenF1APIClient type
        session_metadata: Dict[str, Any],
    ) -> List[TimelineItem]:
        """Build timeline from OpenF1 structured data.
        
        Args:
            openf1_client: OpenF1 API client
            session_metadata: Session info (year, gp, session_id)
            
        Returns:
            List of TimelineItem objects from OpenF1
        """
        logger.info("="*70)
        logger.info("=== Building OpenF1 timeline ===")
        logger.info("="*70)
        timeline_items = []
        
        year = session_metadata.get("year")
        gp_name = session_metadata.get("gp_name")
        session_type = session_metadata.get("session_type", "RACE")
        
        logger.info(f"[METADATA] Detected: year={year}, gp_name={gp_name}, session_type={session_type}")
        logger.info(f"[CLIENT] OpenF1 client type: {type(openf1_client).__name__}")
        
        if not all([year, gp_name]):
            logger.error(f"[FAIL] Missing session metadata: year={year}, gp_name={gp_name}")
            return []
        
        if gp_name.lower() == "unknown":
            logger.error(f"[FAIL] Cannot resolve OpenF1 session: gp_name is 'Unknown'. Metadata extraction likely failed.")
            return []
        
        try:
            # Test session resolution first
            logger.info(f"[SESSION] Querying OpenF1 sessions: year={year}, gp_name={gp_name}, session_type={session_type}")
            test_sessions = openf1_client.search_sessions(year=year, gp_name=gp_name, session_type=session_type)
            
            if not test_sessions:
                logger.error(f"[FAIL] Could not match OpenF1 session for {year} {gp_name} ({session_type})")
                
                # Try fallback: search without session_type filter
                logger.info(f"[FALLBACK] Trying search without session_type filter...")
                fallback_sessions = openf1_client.search_sessions(year=year, gp_name=gp_name)
                
                if fallback_sessions:
                    logger.warning(f"[FALLBACK] Found {len(fallback_sessions)} session(s) without type filter")
                    for i, sess in enumerate(fallback_sessions):
                        logger.info(f"  [{i}] {sess.get('gp_name')} ({sess.get('session_type')}) - {sess.get('session_id')}")
                    # Use the RACE session if available, otherwise first session
                    race_session = next((s for s in fallback_sessions if s.get('session_type', '').upper() == 'RACE'), fallback_sessions[0])
                    test_sessions = [race_session]
                    logger.info(f"[FALLBACK] Using: {race_session.get('gp_name')} ({race_session.get('session_type')})")
                else:
                    # Try alternative years (2024, 2023)
                    logger.info(f"[FALLBACK] Searching alternative years for {gp_name}...")
                    for alt_year in [2024, 2023, 2022]:
                        alt_sessions = openf1_client.search_sessions(year=alt_year, gp_name=gp_name)
                        if alt_sessions:
                            logger.warning(f"[FALLBACK] Found {gp_name} in year {alt_year} instead!")
                            logger.info(f"  Document may be mislabeled. Found {len(alt_sessions)} session(s) in {alt_year}")
                            test_sessions = alt_sessions
                            year = alt_year  # Update year to matched year
                            break
                
                if not test_sessions:
                    # Final fallback: get all sessions for the year and list them
                    logger.error(f"[FAIL] No sessions found for {year} {gp_name}. Getting all sessions for {year}...")
                    all_sessions_for_year = openf1_client.search_sessions(year=year)
                    available_gps = list(set([s.get('gp_name') for s in all_sessions_for_year if s.get('gp_name')]))
                    
                    logger.error(f"[FAIL] Available GPs for {year}: {available_gps}")
                    logger.error(f"[FAIL] No sessions returned from search_sessions(). GP name '{gp_name}' not found in OpenF1 database.")
                    
                    # Store debug info
                    self.debug_info = {
                        "detected_year": year,
                        "detected_gp": gp_name,
                        "detected_session_type": session_type,
                        "session_id": None,
                        "session_found": False,
                        "error": f"Session not found in OpenF1 database. Available GPs for {year}: {available_gps}"
                    }
                    return []
            
            logger.info(f"[SUCCESS] Session resolution found {len(test_sessions)} session(s)")
            
            # Get first matching session details
            session = test_sessions[0]
            session_id = session.get('session_id') or session.get('session_key')
            
            # Log each session found
            for i, sess in enumerate(test_sessions):
                sess_id = sess.get('session_id') or sess.get('session_key')
                logger.info(f"  [{i}] session_id={sess_id}, gp_name={sess.get('gp_name')}, year={sess.get('year')}, type={sess.get('session_type')}, date={sess.get('session_date')}")
            
            # Store debug info
            self.debug_info = {
                "detected_year": year,
                "detected_gp": gp_name,
                "detected_session_type": session_type,
                "session_id": session_id,
                "session_found": True,
                "matched_session": {
                    "gp_name": session.get('gp_name'),
                    "year": session.get('year'),
                    "type": session.get('session_type'),
                    "date": session.get('session_date'),
                }
            }
            logger.info(f"[DEBUG] Session resolution success: session_id={session_id}")
            logger.info(f"[DEBUG] Using GP={session.get('gp_name')}, Year={session.get('year')}, Type={session.get('session_type')}")
            
            # Fetch race control messages (SC/VSC/Red Flag)
            logger.info("[FETCH] Fetching race control events...")
            rc_items = self._extract_race_control_events(
                openf1_client, year, gp_name, session_type
            )
            timeline_items.extend(rc_items)
            logger.info(f"  > Race control events: {len(rc_items)}")
            
            # Fetch pit stop events
            logger.info("[FETCH] Fetching pit stop events...")
            pit_items = self._extract_pit_events(
                openf1_client, year, gp_name, session_type
            )
            timeline_items.extend(pit_items)
            logger.info(f"  > Pit events: {len(pit_items)}")
            
            # Fetch stint changes with compounds
            logger.info("[FETCH] Fetching stint events...")
            stint_items = self._extract_stint_events(
                openf1_client, year, gp_name, session_type
            )
            timeline_items.extend(stint_items)
            logger.info(f"  > Stint events: {len(stint_items)}")
            
            # Fetch lap-time markers (fastest lap, pace changes)
            logger.info("[FETCH] Fetching lap markers...")
            lap_items = self._extract_lap_markers(
                openf1_client, year, gp_name, session_type
            )
            timeline_items.extend(lap_items)
            logger.info(f"  > Lap markers: {len(lap_items)}")
            
            # Fetch position changes (overtakes/positional shifts)
            logger.info("[FETCH] Fetching position changes...")
            position_items = self._extract_position_changes(
                openf1_client, year, gp_name, session_type
            )
            timeline_items.extend(position_items)
            logger.info(f"  > Position changes: {len(position_items)}")
            
            # Count event types for summary
            event_type_counts = {}
            for item in timeline_items:
                event_type = item.event_type.value if hasattr(item.event_type, 'value') else str(item.event_type)
                event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1
            
            count_summary = ", ".join([f"{k}={v}" for k, v in sorted(event_type_counts.items())])
            logger.info(f"[TOTAL OPENF1] {len(timeline_items)} events extracted: {count_summary}")
        
        except Exception as e:
            logger.error(f"[ERROR] Exception building OpenF1 timeline: {e}", exc_info=True)
        
        if len(timeline_items) == 0:
            logger.warning(f"[WARNING] OpenF1 returned 0 events. Check session resolution and endpoint queries.")
        logger.info("="*70)
        return timeline_items

    def _extract_race_control_events(
        self,
        openf1_client: Any,
        year: int,
        gp_name: str,
        session_type: str,
    ) -> List[TimelineItem]:
        """Extract SC/VSC/Red Flag/Yellow/Incident/Weather events from race control messages.
        
        Categorizes all race control messages by parsing the message text for keywords:
        - "SAFETY CAR" (not VIRTUAL) -> SC
        - "VIRTUAL SAFETY CAR" or "VSC" -> VSC
        - "RED FLAG" -> RED
        - "YELLOW FLAG" or "YELLOW" (local yellow) -> YELLOW
        - "RAIN", "WET", "TRACK", "WEATHER" -> WEATHER
        - "INCIDENT", "COLLISION", "CRASH", "OFF", "DEBRIS", "INVESTIGATION", "PENALTY" -> INCIDENT
        - Other messages -> INFO (kept for context)
        
        Args:
            openf1_client: OpenF1 API client
            year, gp_name, session_type: Session identifiers
            
        Returns:
            List of race control TimelineItems
        """
        items = []
        
        try:
            # First, search for the session to get session_id
            sessions = openf1_client.search_sessions(year=year, gp_name=gp_name, session_type=session_type)
            
            if not sessions:
                logger.debug(f"[RC] No sessions found for {year} {gp_name} {session_type}")
                return items
            
            # Use the first matching session
            session = sessions[0]
            session_id = session.get("session_id") or session.get("session_key")
            
            if not session_id:
                logger.debug(f"[RC] Session found but no session_id: {session}")
                return items
            
            logger.debug(f"[RC] Using session_id {session_id}")
            
            # Get race control messages from OpenF1
            rc_messages = openf1_client.get_race_control_messages(session_id)
            logger.debug(f"[RC] OpenF1 returned {len(rc_messages)} race control messages")
            
            flag_counts = {"SC": 0, "VSC": 0, "RED": 0, "YELLOW": 0, "WEATHER": 0, "INCIDENT": 0, "INFO": 0}
            
            for msg in rc_messages:
                # Parse message for event type
                message_text = msg.get("message", "").upper()
                lap = msg.get("lap")
                
                event_type = TimelineEventType.INFO
                
                # Categorization logic with priority order
                if "RED FLAG" in message_text:
                    event_type = TimelineEventType.RED_FLAG
                    flag_counts["RED"] += 1
                elif "SAFETY CAR" in message_text and "VIRTUAL" not in message_text:
                    event_type = TimelineEventType.SAFETY_CAR
                    flag_counts["SC"] += 1
                elif "VIRTUAL SAFETY CAR" in message_text or "VSC" in message_text:
                    event_type = TimelineEventType.VIRTUAL_SC
                    flag_counts["VSC"] += 1
                elif "YELLOW FLAG" in message_text or ("YELLOW" in message_text and "FLAG" in message_text):
                    event_type = TimelineEventType.YELLOW_FLAG
                    flag_counts["YELLOW"] += 1
                elif any(word in message_text for word in ["RAIN", "WET", "TRACK CONDITIONS", "WEATHER"]):
                    event_type = TimelineEventType.WEATHER
                    flag_counts["WEATHER"] += 1
                elif any(word in message_text for word in ["INCIDENT", "COLLISION", "CRASH", "OFF TRACK", "DEBRIS", "INVESTIGATION", "PENALTY"]):
                    event_type = TimelineEventType.INCIDENT
                    flag_counts["INCIDENT"] += 1
                else:
                    # Keep all messages, not just flags
                    flag_counts["INFO"] += 1
                
                # Skip generic INFO messages for brevity (they clutter the timeline)
                # But keep if they mention specific incidents/penalties
                if event_type == TimelineEventType.INFO:
                    if not any(word in message_text for word in ["PIT LANE OPEN", "PIT LANE CLOSED", "GREEN LIGHT", "GRID PENALTY", "TYRE RULE"]):
                        continue
                
                item = TimelineItem(
                    lap=lap,
                    timestamp=msg.get("time"),
                    event_type=event_type,
                    title=f"{event_type.value}" + (f" at Lap {lap}" if lap else ""),
                    description=msg.get("message", ""),
                    pdf_citations=[],
                    openf1_evidence=[
                        OpenF1Evidence(
                            evidence_type="race_control",
                            evidence_id=msg.get("message_id"),
                            snippet=msg.get("message", ""),
                            payload=msg,
                        )
                    ],
                    impacted_drivers=[],
                    impact_summary="",
                    confidence="High",
                )
                items.append(item)
            
            # Log categorization summary
            logger.info(f"[RC] Categorized race control messages: SC={flag_counts['SC']}, VSC={flag_counts['VSC']}, RED={flag_counts['RED']}, YELLOW={flag_counts['YELLOW']}, WEATHER={flag_counts['WEATHER']}, INCIDENT={flag_counts['INCIDENT']}, INFO={flag_counts['INFO']}")
        
        except Exception as e:
            logger.warning(f"Failed to extract race control events: {e}")
        
        return items

    def _extract_pit_events(
        self,
        openf1_client: Any,
        year: int,
        gp_name: str,
        session_type: str,
    ) -> List[TimelineItem]:
        """Extract pit stop events.
        
        Args:
            openf1_client: OpenF1 API client
            year, gp_name, session_type: Session identifiers
            
        Returns:
            List of pit stop TimelineItems
        """
        items = []
        
        try:
            # First, search for the session to get session_id
            sessions = openf1_client.search_sessions(year=year, gp_name=gp_name, session_type=session_type)
            
            if not sessions:
                logger.debug(f"No sessions found for pit events: {year} {gp_name} {session_type}")
                return items
            
            session = sessions[0]
            session_id = session.get("session_id") or session.get("session_key")
            
            if not session_id:
                logger.warning(f"Session found but no session_id for pit stops: {session}")
                return items
            
            pit_stops = openf1_client.get_pit_stops(session_id)
            
            # Group by lap to avoid duplicates
            pit_by_lap = defaultdict(list)
            for pit in pit_stops:
                lap = pit.get("lap")
                if lap:
                    pit_by_lap[lap].append(pit)
            
            # Create one item per lap (representing multiple pit stops)
            for lap, pits in pit_by_lap.items():
                drivers = [p.get("driver_name", "Unknown") for p in pits]
                compounds = [p.get("compound", "Unknown") for p in pits]
                
                item = TimelineItem(
                    lap=lap,
                    timestamp=pits[0].get("time"),
                    event_type=TimelineEventType.PIT_STOP,
                    title=f"Pit Stops: Lap {lap}",
                    description=f"{len(pits)} driver(s) pitted. "
                                f"Drivers: {', '.join(drivers)}. "
                                f"Compounds: {', '.join(set(compounds))}.",
                    pdf_citations=[],
                    openf1_evidence=[
                        OpenF1Evidence(
                            evidence_type="pit_stop",
                            evidence_id=p.get("pit_stop_id"),
                            snippet=f"{p.get('driver_name')} pitted on lap {lap} for {p.get('compound')}",
                            payload=p,
                        )
                        for p in pits
                    ],
                    impacted_drivers=drivers,
                    impact_summary="",
                    confidence="High",
                )
                items.append(item)
        
        except Exception as e:
            logger.warning(f"Failed to extract pit events: {e}")
        
        return items

    def _extract_stint_events(
        self,
        openf1_client: Any,
        year: int,
        gp_name: str,
        session_type: str,
    ) -> List[TimelineItem]:
        """Extract stint changes with tire compounds.
        
        Args:
            openf1_client: OpenF1 API client
            year, gp_name, session_type: Session identifiers
            
        Returns:
            List of stint change TimelineItems
        """
        items = []
        
        try:
            # First, search for the session to get session_id
            sessions = openf1_client.search_sessions(year=year, gp_name=gp_name, session_type=session_type)
            
            if not sessions:
                logger.debug(f"No sessions found for stint events: {year} {gp_name} {session_type}")
                return items
            
            session = sessions[0]
            session_id = session.get("session_id") or session.get("session_key")
            
            if not session_id:
                logger.warning(f"Session found but no session_id for stints: {session}")
                return items
            
            stints = openf1_client.get_stints(session_id)
            
            if not stints:
                return []
            
            # Group by driver to create change events
            by_driver = defaultdict(list)
            for stint in stints:
                driver_name = stint.get("driver_name", f"Driver {stint.get('driver_number')}")
                by_driver[driver_name].append(stint)
            
            # For each driver with multiple stints, create stint change events
            for driver, driver_stints in by_driver.items():
                if len(driver_stints) > 1:
                    for i in range(len(driver_stints) - 1):
                        current = driver_stints[i]
                        next_stint = driver_stints[i + 1]
                        change_lap = next_stint.get("lap_start", 999)
                        
                        compound_from = current.get("compound", "?")
                        compound_to = next_stint.get("compound", "?")
                        
                        item = TimelineItem(
                            lap=change_lap,
                            timestamp=None,
                            event_type=TimelineEventType.PIT_STOP,
                            title=f"Stint Change: {driver}",
                            description=f"{driver} changes from {compound_from} to {compound_to} at lap {change_lap}",
                            pdf_citations=[],
                            openf1_evidence=[
                                OpenF1Evidence(
                                    evidence_type="stint_change",
                                    evidence_id=f"{driver}_{change_lap}",
                                    snippet=f"{driver}: {compound_from} → {compound_to}",
                                    payload={"driver": driver, "from": compound_from, "to": compound_to, "lap": change_lap},
                                )
                            ],
                            impacted_drivers=[driver],
                            impact_summary=f"{driver} switched from {compound_from} to {compound_to} tires",
                            confidence="High",
                        )
                        items.append(item)
        
        except Exception as e:
            logger.warning(f"Failed to extract stint events: {e}")
        
        return items

    def _extract_lap_markers(
        self,
        openf1_client: Any,
        year: int,
        gp_name: str,
        session_type: str,
    ) -> List[TimelineItem]:
        """Extract lap-time markers (fastest lap, pace changes).
        
        Args:
            openf1_client: OpenF1 API client
            year, gp_name, session_type: Session identifiers
            
        Returns:
            List of lap marker TimelineItems
        """
        items = []
        
        try:
            # First, search for the session to get session_id
            sessions = openf1_client.search_sessions(year=year, gp_name=gp_name, session_type=session_type)
            
            if not sessions:
                logger.debug(f"No sessions found for lap markers: {year} {gp_name} {session_type}")
                return items
            
            session = sessions[0]
            session_id = session.get("session_id") or session.get("session_key")
            
            if not session_id:
                logger.warning(f"Session found but no session_id for laps: {session}")
                return items
            
            laps = openf1_client.get_laps(session_id)
            
            if not laps:
                return []
            
            # Find fastest laps by driver
            fastest_by_driver = {}
            for lap in laps:
                driver_name = lap.get("driver_name", f"Driver {lap.get('driver_number')}")
                lap_time = lap.get("lap_time_ms")
                
                if not lap_time:
                    continue
                
                if driver_name not in fastest_by_driver or lap_time < fastest_by_driver[driver_name]["lap_time_ms"]:
                    fastest_by_driver[driver_name] = lap
            
            # Create events for fastest laps
            for driver_name, lap_data in fastest_by_driver.items():
                lap_num = lap_data.get("lap_number")
                lap_time = lap_data.get("lap_time_ms")
                
                if lap_num and lap_time:
                    lap_time_sec = lap_time / 1000.0
                    item = TimelineItem(
                        lap=lap_num,
                        timestamp=None,
                        event_type=TimelineEventType.PACE_CHANGE,
                        title=f"Fastest Lap: {driver_name}",
                        description=f"{driver_name} set fastest lap on lap {lap_num} ({lap_time_sec:.2f}s)",
                        pdf_citations=[],
                        openf1_evidence=[
                            OpenF1Evidence(
                                evidence_type="fastest_lap",
                                evidence_id=f"{driver_name}_lap_{lap_num}",
                                snippet=f"{driver_name} fastest: {lap_time_sec:.2f}s",
                                payload=lap_data,
                            )
                        ],
                        impacted_drivers=[driver_name],
                        impact_summary=f"{driver_name} achieved fastest lap pace",
                        confidence="High",
                    )
                    items.append(item)
        
        except Exception as e:
            logger.warning(f"Failed to extract lap markers: {e}")
        
        return items

    def _extract_position_changes(
        self,
        openf1_client: Any,
        year: int,
        gp_name: str,
        session_type: str,
    ) -> List[TimelineItem]:
        """Extract position changes (overtakes/positional shifts).
        
        Args:
            openf1_client: OpenF1 API client
            year, gp_name, session_type: Session identifiers
            
        Returns:
            List of position change TimelineItems
        """
        items = []
        
        try:
            # First, search for the session to get session_id
            sessions = openf1_client.search_sessions(year=year, gp_name=gp_name, session_type=session_type)
            
            if not sessions:
                logger.debug(f"No sessions found for position changes: {year} {gp_name} {session_type}")
                return items
            
            session = sessions[0]
            session_id = session.get("session_id") or session.get("session_key")
            
            if not session_id:
                logger.warning(f"Session found but no session_id for positions: {session}")
                return items
            
            laps = openf1_client.get_laps(session_id)
            
            if not laps:
                return []
            
            # Organize laps by lap number
            by_lap = defaultdict(list)
            for lap in laps:
                lap_num = lap.get("lap_number")
                if lap_num:
                    by_lap[lap_num].append(lap)
            
            # Compare consecutive laps for position changes (overtakes)
            lap_numbers = sorted(by_lap.keys())
            for i in range(len(lap_numbers) - 1):
                current_lap = lap_numbers[i]
                next_lap = lap_numbers[i + 1]
                
                current_positions = {lap.get("driver_number"): lap.get("position") for lap in by_lap[current_lap] if lap.get("position")}
                next_positions = {lap.get("driver_number"): lap.get("position") for lap in by_lap[next_lap] if lap.get("position")}
                
                # Find drivers who improved position
                for driver_num, next_pos in next_positions.items():
                    current_pos = current_positions.get(driver_num)
                    if current_pos and next_pos and current_pos > next_pos:
                        # Position improved (lower number = better)
                        driver_name = next(
                            (lap.get("driver_name") for lap in by_lap[next_lap] if lap.get("driver_number") == driver_num),
                            f"Driver {driver_num}"
                        )
                        
                        item = TimelineItem(
                            lap=next_lap,
                            timestamp=None,
                            event_type=TimelineEventType.INCIDENT,  # Reusing INCIDENT for positional changes
                            title=f"Position Change: {driver_name}",
                            description=f"{driver_name} advanced from P{current_pos} to P{next_pos}",
                            pdf_citations=[],
                            openf1_evidence=[
                                OpenF1Evidence(
                                    evidence_type="position_change",
                                    evidence_id=f"{driver_num}_lap_{next_lap}",
                                    snippet=f"{driver_name}: P{current_pos} → P{next_pos}",
                                    payload={"driver": driver_name, "from": current_pos, "to": next_pos, "lap": next_lap},
                                )
                            ],
                            impacted_drivers=[driver_name],
                            impact_summary=f"{driver_name} gained a position",
                            confidence="High",
                        )
                        items.append(item)
        
        except Exception as e:
            logger.warning(f"Failed to extract position changes: {e}")
        
        return items

    def merge_timelines(
        self,
        pdf_items: List[TimelineItem],
        openf1_items: List[TimelineItem],
    ) -> List[TimelineItem]:
        """Merge PDF and OpenF1 timeline items with deduplication.
        
        Args:
            pdf_items: Events extracted from PDF
            openf1_items: Events from OpenF1 API
            
        Returns:
            Deduplicated, merged timeline
        """
        logger.info(f"Merging {len(pdf_items)} PDF items with {len(openf1_items)} OpenF1 items")
        
        # Use lap + event_type + normalized description as dedup key to keep distinct events
        merged = {}  # key -> TimelineItem
        dedup_counts = {}  # Track how many items collapsed per key
        
        def normalize_description(desc: str) -> str:
            """Normalize description to first 50 chars for dedup key."""
            if not desc:
                return ""
            # Take first 50 chars of description (enough to distinguish events)
            return desc[:50].lower().strip()
        
        # Add OpenF1 items first (they are canonical)
        for item in openf1_items:
            # Use string representation of event_type to avoid enum comparison issues
            key = (item.lap, item.event_type.value if item.event_type else "UNKNOWN", normalize_description(item.description))
            dedup_counts[key] = dedup_counts.get(key, 0) + 1
            merged[key] = item
        
        # Add PDF items, merging evidence if duplicate
        for pdf_item in pdf_items:
            key = (pdf_item.lap, pdf_item.event_type.value if pdf_item.event_type else "UNKNOWN", normalize_description(pdf_item.description))
            
            if key in merged:
                # Merge: add PDF citations and evidence to existing item
                existing = merged[key]
                existing.pdf_citations.extend(pdf_item.pdf_citations)
                # Merge OpenF1 evidence (preserve existing OpenF1 data)
                existing.openf1_evidence.extend(pdf_item.openf1_evidence)
                # Bump confidence if we have PDF corroboration
                if pdf_item.confidence == "High":
                    existing.confidence = "High"
            else:
                # New item
                dedup_counts[key] = dedup_counts.get(key, 0) + 1
                merged[key] = pdf_item
        
        # Sort by lap, then by event type
        sorted_items = sorted(
            merged.values(),
            key=lambda x: (x.lap if x.lap is not None else 999999, str(x.event_type.value) if x.event_type else "UNKNOWN"),
        )
        
        # Log deduplication details
        logger.info(f"Merged timeline has {len(sorted_items)} items (dedup details)")
        for (lap, event_type_str, desc), count in sorted(dedup_counts.items()):
            if count > 1:
                logger.info(f"  Lap {lap} {event_type_str}: {count} → 1 (collapsed {count-1})")
        return sorted_items

    def compute_impact(
        self,
        timeline: List[TimelineItem],
        laps_data: Optional[List[Dict[str, Any]]] = None,
        pit_data: Optional[List[Dict[str, Any]]] = None,
    ) -> List[TimelineItem]:
        """Compute impact (winners/losers) for timeline events.
        
        Args:
            timeline: Merged timeline items
            laps_data: Optional lap times from OpenF1
            pit_data: Optional pit stop data from OpenF1
            
        Returns:
            Timeline items with computed impact
        """
        logger.info("Computing impact for timeline events")
        
        for item in timeline:
            if not item.lap:
                continue
            
            # For SC/VSC: drivers who pitted during SC window benefit
            if item.event_type in [TimelineEventType.SAFETY_CAR, TimelineEventType.VIRTUAL_SC]:
                if pit_data:
                    # Find drivers who pitted during SC (within 2 laps of SC deployment)
                    pit_drivers = [
                        p.get("driver_name")
                        for p in pit_data
                        if p.get("lap") and item.lap and item.lap - 2 <= p.get("lap") <= item.lap + 2
                    ]
                    
                    item.impacted_drivers = list(set(pit_drivers))  # Unique drivers
                    
                    if pit_drivers:
                        item.impact_summary = (
                            f"Benefited: {', '.join(sorted(set(pit_drivers)))} "
                            f"(pitted during {item.event_type.value})"
                        )
                        item.confidence = "High"  # Based on structural OpenF1 data
                    else:
                        item.impact_summary = "No drivers pitted during this period"
            
            # For pit stops: analyze timing and impact
            elif item.event_type == TimelineEventType.PIT_STOP:
                if pit_data and laps_data:
                    # Pit drivers from timeline
                    pit_drivers = item.impacted_drivers or []
                    
                    # Try to estimate impact by checking lap times before/after pit
                    benefits = []
                    loses = []
                    
                    for driver in pit_drivers:
                        pit_lap_times = [
                            lap.get("lap_time_ms") for lap in laps_data
                            if lap.get("driver_name") == driver and lap.get("lap_number") 
                            and item.lap and (item.lap - 1 <= lap.get("lap_number") <= item.lap + 3)
                        ]
                        
                        if len(pit_lap_times) > 1:
                            # Simple heuristic: if pit results in faster times after pit, benefit
                            avg_before = sum(pit_lap_times[:-1]) / len(pit_lap_times[:-1]) if len(pit_lap_times) > 1 else pit_lap_times[0]
                            last_time = pit_lap_times[-1]
                            
                            if last_time < avg_before * 0.95:  # 5% faster
                                benefits.append(driver)
                            elif last_time > avg_before * 1.05:  # 5% slower
                                loses.append(driver)
                    
                    impact_parts = []
                    if benefits:
                        impact_parts.append(f"Benefited: {', '.join(benefits)}")
                    if loses:
                        impact_parts.append(f"Hurt: {', '.join(loses)}")
                    
                    if impact_parts:
                        item.impact_summary = " | ".join(impact_parts)
                    else:
                        item.impact_summary = f"{len(pit_drivers)} driver(s) pitted; mixed impact"
                    
                    item.confidence = "Medium" if impact_parts else "Low"
                else:
                    item.impact_summary = f"{len(item.impacted_drivers)} driver(s) pitted; tire strategy change"
                    item.confidence = "High"
            
            # For incident/position changes: mark drivers involved
            elif item.event_type in [TimelineEventType.INCIDENT, TimelineEventType.PACE_CHANGE, TimelineEventType.PIT_STOP]:
                if item.impacted_drivers:
                    item.impact_summary = f"{', '.join(item.impacted_drivers)} affected"
                    item.confidence = "High"
                else:
                    item.confidence = "Medium"
            
            # For race control messages without specific drivers
            elif not item.impacted_drivers:
                item.impact_summary = "Track condition change; check driver strategies"
                item.confidence = "High"
        
        logger.info("Computed impact for timeline")
        return timeline

    def build_race_timeline(
        self,
        doc_id: str,
        openf1_client: Any,
        retriever: Retriever,
        session_metadata: Dict[str, Any],
        laps_data: Optional[List[Dict[str, Any]]] = None,
        pit_data: Optional[List[Dict[str, Any]]] = None,
    ) -> RaceTimeline:
        """Orchestrate complete timeline reconstruction.
        
        Args:
            doc_id: Document ID
            openf1_client: OpenF1 API client
            retriever: Vector store retriever
            session_metadata: Session info
            laps_data: Optional lap times data
            pit_data: Optional pit stop data
            
        Returns:
            Complete RaceTimeline object
        """
        logger.info(f"\n" + "="*70)
        logger.info(f"BUILD RACE TIMELINE: {doc_id}")
        logger.info(f"="*70)
        logger.info(f"[METADATA] {session_metadata}")
        
        # Step 1: Extract PDF events
        logger.info(f"[STEP 1/4] Extract PDF events...")
        pdf_items = self.extract_pdf_events(doc_id, session_metadata)
        logger.info(f"  > PDF events: {len(pdf_items)}")
        
        # Step 2: Build OpenF1 timeline
        logger.info("[STEP 2/4] Build OpenF1 timeline...")
        openf1_items = self.build_openf1_timeline(openf1_client, session_metadata)
        logger.info(f"  > OpenF1 events: {len(openf1_items)}")
        
        # Step 3: Merge and deduplicate
        logger.info("[STEP 3/4] Merge and deduplicate timelines...")
        merged_timeline = self.merge_timelines(pdf_items, openf1_items)
        logger.info(f"  > Merged timeline: {len(merged_timeline)} events")
        
        # Step 4: Compute impact
        logger.info("[STEP 4/4] Compute impact analysis...")
        final_timeline = self.compute_impact(merged_timeline, laps_data, pit_data)
        logger.info(f"  > Final timeline: {len(final_timeline)} events")
        
        # Log final summary
        logger.info(f"\n[FINAL SUMMARY]")
        logger.info(f"  PDF events:     {len(pdf_items)}")
        logger.info(f"  OpenF1 events:  {len(openf1_items)}")
        logger.info(f"  Merged:         {len(merged_timeline)}")
        logger.info(f"  Final:          {len(final_timeline)}")
        
        if len(final_timeline) == 0:
            logger.error(f"[ERROR] Final timeline is EMPTY. No events will be displayed to user.")
        
        # Step 5: Aggregate statistics
        event_counts = defaultdict(int)
        drivers_involved = set()
        
        for item in final_timeline:
            event_counts[item.event_type.value] += 1
            drivers_involved.update(item.impacted_drivers)
        
        # Create RaceTimeline object
        race_timeline = RaceTimeline(
            document_id=doc_id,
            session_info=session_metadata,
            timeline_items=final_timeline,
            event_counts=dict(event_counts),
            drivers_involved=sorted(list(drivers_involved)),
            debug_info=self.debug_info,  # Include debug info from timeline builder
        )
        
        logger.info(f"Built race timeline with {len(final_timeline)} items")
        return race_timeline
