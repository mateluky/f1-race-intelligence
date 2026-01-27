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
        - event_type: one of SC, VSC, RED, YELLOW, PIT, WEATHER, INCIDENT, PACE, INFO
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
        logger.info("Building OpenF1 timeline")
        timeline_items = []
        
        year = session_metadata.get("year")
        gp_name = session_metadata.get("gp_name")
        session_type = session_metadata.get("session_type", "RACE")
        
        if not all([year, gp_name]):
            logger.warning("Missing session metadata for OpenF1 query")
            return []
        
        try:
            # Fetch race control messages (SC/VSC/Red Flag)
            rc_items = self._extract_race_control_events(
                openf1_client, year, gp_name, session_type
            )
            timeline_items.extend(rc_items)
            
            # Fetch pit stop events
            pit_items = self._extract_pit_events(
                openf1_client, year, gp_name, session_type
            )
            timeline_items.extend(pit_items)
            
            # Fetch stint changes (optional)
            stint_items = self._extract_stint_events(
                openf1_client, year, gp_name, session_type
            )
            timeline_items.extend(stint_items)
        
        except Exception as e:
            logger.error(f"Failed to build OpenF1 timeline: {e}")
        
        logger.info(f"Built {len(timeline_items)} OpenF1 timeline items")
        return timeline_items

    def _extract_race_control_events(
        self,
        openf1_client: Any,
        year: int,
        gp_name: str,
        session_type: str,
    ) -> List[TimelineItem]:
        """Extract SC/VSC/Red Flag events from race control messages.
        
        Args:
            openf1_client: OpenF1 API client
            year, gp_name, session_type: Session identifiers
            
        Returns:
            List of race control TimelineItems
        """
        items = []
        
        try:
            # Get race control messages from OpenF1
            rc_messages = openf1_client.get_race_control_messages(
                year=year,
                gp_name=gp_name,
                session_type=session_type,
            )
            
            for msg in rc_messages:
                # Parse message for event type
                message_text = msg.get("message", "").upper()
                lap = msg.get("lap")
                
                event_type = TimelineEventType.INFO
                if "SAFETY CAR" in message_text and "VIRTUAL" not in message_text:
                    event_type = TimelineEventType.SAFETY_CAR
                elif "VIRTUAL SAFETY CAR" in message_text or "VSC" in message_text:
                    event_type = TimelineEventType.VIRTUAL_SC
                elif "RED FLAG" in message_text:
                    event_type = TimelineEventType.RED_FLAG
                elif "YELLOW FLAG" in message_text:
                    event_type = TimelineEventType.YELLOW_FLAG
                else:
                    continue  # Skip other messages for now
                
                item = TimelineItem(
                    lap=lap,
                    timestamp=msg.get("time"),
                    event_type=event_type,
                    title=f"{event_type.value} at Lap {lap}" if lap else event_type.value,
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
            pit_stops = openf1_client.get_pit_stops(
                year=year,
                gp_name=gp_name,
                session_type=session_type,
            )
            
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
        """Extract stint changes (optional - can be sparse).
        
        Args:
            openf1_client: OpenF1 API client
            year, gp_name, session_type: Session identifiers
            
        Returns:
            List of stint change TimelineItems
        """
        # For now, return empty (stints are less critical than SC/pit stops)
        # Can be enhanced later
        return []

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
        
        # Use lap + event_type as dedup key
        merged = {}  # key -> TimelineItem
        
        # Add OpenF1 items first (they are canonical)
        for item in openf1_items:
            key = (item.lap, item.event_type)
            merged[key] = item
        
        # Add PDF items, merging evidence if duplicate
        for pdf_item in pdf_items:
            key = (pdf_item.lap, pdf_item.event_type)
            
            if key in merged:
                # Merge: add PDF citations and evidence to existing item
                existing = merged[key]
                existing.pdf_citations.extend(pdf_item.pdf_citations)
                # Bump confidence if we have PDF corroboration
                if pdf_item.confidence == "High":
                    existing.confidence = "High"
            else:
                # New item
                merged[key] = pdf_item
        
        # Sort by lap, then by event type
        sorted_items = sorted(
            merged.values(),
            key=lambda x: (x.lap if x.lap else 999999, str(x.event_type)),
        )
        
        logger.info(f"Merged timeline has {len(sorted_items)} items")
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
            
            # For SC/VSC: drivers who pitted during SC window
            if item.event_type in [TimelineEventType.SAFETY_CAR, TimelineEventType.VIRTUAL_SC]:
                if pit_data:
                    item.impacted_drivers = [
                        p.get("driver_name")
                        for p in pit_data
                        if p.get("lap") == item.lap or (
                            item.lap and item.lap - 2 <= p.get("lap", -1) <= item.lap + 2
                        )
                    ]
                    if item.impacted_drivers:
                        item.impact_summary = (
                            f"Drivers {', '.join(item.impacted_drivers)} benefited from pit "
                            f"opportunity during safety car period."
                        )
            
            # For pit stops: mark drivers who pitted
            elif item.event_type == TimelineEventType.PIT_STOP:
                item.impact_summary = (
                    f"Pit stop window on lap {item.lap}: "
                    f"{len(item.impacted_drivers)} driver(s) changed tires."
                )
            
            # For incidents: analyze lap time deltas
            elif item.event_type == TimelineEventType.INCIDENT:
                if laps_data:
                    # Find drivers with unusual lap time deltas around incident lap
                    incident_lap = item.lap
                    window_start = incident_lap - 2 if incident_lap else 0
                    window_end = incident_lap + 2 if incident_lap else 0
                    
                    # Simplified: just log that we considered lap data
                    logger.debug(f"Analyzed lap times in window {window_start}-{window_end}")
        
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
        logger.info(f"Building race timeline for {doc_id}")
        
        # Step 1: Extract PDF events
        pdf_items = self.extract_pdf_events(doc_id, session_metadata)
        
        # Step 2: Build OpenF1 timeline
        openf1_items = self.build_openf1_timeline(openf1_client, session_metadata)
        
        # Step 3: Merge and deduplicate
        merged_timeline = self.merge_timelines(pdf_items, openf1_items)
        
        # Step 4: Compute impact
        final_timeline = self.compute_impact(merged_timeline, laps_data, pit_data)
        
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
        )
        
        logger.info(f"Built race timeline with {len(final_timeline)} items")
        return race_timeline
