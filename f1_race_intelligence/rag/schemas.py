"""Pydantic models and schemas for F1 race intelligence."""

from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class ClaimType(str, Enum):
    """Types of claims that can be extracted from race documents."""
    PACE = "pace"
    STRATEGY = "strategy"
    INCIDENT = "incident"
    TYRES = "tyres"
    PIT_STOP = "pit_stop"
    DRIVER_PERFORMANCE = "driver_performance"
    TEAM_RADIO = "team_radio"
    WEATHER = "weather"
    TECHNICAL = "technical"
    OTHER = "other"


class EvidenceStatus(str, Enum):
    """Status of a claim against its evidence."""
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNCLEAR = "unclear"
    INSUFFICIENT_DATA = "insufficient_data"


class TimeScope(BaseModel):
    """Time scope for a claim (lap range or absolute time)."""
    lap_start: Optional[int] = Field(None, description="Starting lap number")
    lap_end: Optional[int] = Field(None, description="Ending lap number")
    time_start: Optional[str] = Field(None, description="Starting time (ISO format)")
    time_end: Optional[str] = Field(None, description="Ending time (ISO format)")


class Evidence(BaseModel):
    """Evidence from OpenF1 or other sources supporting/refuting a claim."""
    source: str = Field(
        ...,
        description="Source of evidence (e.g., 'openf1_laps', 'openf1_race_control', 'pdf')"
    )
    data: Dict[str, Any] = Field(..., description="Raw evidence data")
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    interpretation: str = Field(..., description="How this evidence relates to the claim")


class ClaimEntity(BaseModel):
    """Named entities mentioned in a claim."""
    drivers: List[str] = Field(default_factory=list, description="Driver identifiers/names")
    teams: List[str] = Field(default_factory=list, description="Team names")
    sessions: List[str] = Field(default_factory=list, description="Race session types (RACE, QUALI, FP)")
    keywords: List[str] = Field(default_factory=list, description="Other relevant keywords")


class Claim(BaseModel):
    """A factual claim extracted from a race document."""
    id: Optional[str] = Field(None, description="Unique claim identifier")
    claim_text: str = Field(..., description="The claim statement")
    claim_type: ClaimType = Field(..., description="Type of claim")
    entities: ClaimEntity = Field(default_factory=ClaimEntity)
    time_scope: Optional[TimeScope] = Field(None)
    evidence: List[Evidence] = Field(default_factory=list)
    status: EvidenceStatus = Field(default=EvidenceStatus.UNCLEAR)
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the claim")
    rationale: str = Field(..., description="Explanation of confidence and evidence")
    source_location: Optional[str] = Field(None, description="Where in the PDF this came from")


class RaceEvent(BaseModel):
    """A discrete event in the race timeline."""
    lap: Optional[int] = Field(None)
    time: Optional[str] = Field(None, description="Time in HH:MM:SS or relative format")
    event: str = Field(..., description="Description of the event")
    source: str = Field(..., description="Source: 'pdf' or 'openf1'")
    affected_drivers: List[str] = Field(default_factory=list)


class RaceBrief(BaseModel):
    """The final Race Intelligence Brief output."""
    id: str = Field(..., description="Unique brief identifier")
    document_id: str = Field(..., description="Source document ID")
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Core content
    executive_summary: str = Field(..., description="High-level summary of race insights")
    key_points: List[str] = Field(default_factory=list, description="Bullet points of key takeaways")
    
    # Claims with evidence
    extracted_claims: List[Claim] = Field(default_factory=list)
    
    # Timeline
    timeline: List[RaceEvent] = Field(
        default_factory=list,
        description="Chronological list of race events"
    )
    
    # Follow-ups
    follow_up_questions: List[str] = Field(
        default_factory=list,
        description="Questions for further analysis"
    )
    
    # Metadata
    session_info: Dict[str, Any] = Field(
        default_factory=dict,
        description="Session metadata (year, gp, session type)"
    )
    claim_stats: Dict[str, int] = Field(
        default_factory=dict,
        description="Statistics on claims (total, supported, unclear, etc.)"
    )


class DocumentMetadata(BaseModel):
    """Metadata about an ingested document."""
    id: str = Field(..., description="Document ID")
    filename: str = Field(...)
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    chunk_count: int = Field(...)
    size_bytes: int = Field(...)


class Chunk(BaseModel):
    """A text chunk from a document."""
    id: str = Field(..., description="Chunk ID")
    document_id: str = Field(...)
    content: str = Field(...)
    embedding: Optional[List[float]] = Field(None)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    chunk_index: int = Field(...)


class SessionInfo(BaseModel):
    """Information about an F1 session from OpenF1."""
    year: int
    gp_name: str
    session_type: str  # RACE, QUALI, FP1, FP2, FP3
    session_id: str
    location: Optional[str] = None
    date: Optional[str] = None


class RetrievalResult(BaseModel):
    """Result of a retrieval query."""
    chunks: List[Chunk]
    scores: List[float]
    query: str


class PDFCitation(BaseModel):
    """Citation from the PDF for a timeline event."""
    chunk_id: str = Field(..., description="Chunk ID in vector store")
    snippet: str = Field(..., description="Text snippet from PDF")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Similarity to event")
    page_num: Optional[int] = Field(None, description="Page number if available")


class OpenF1Evidence(BaseModel):
    """Evidence from OpenF1 API for a timeline event."""
    evidence_type: str = Field(..., description="e.g., 'race_control', 'pit_stop', 'lap_time'")
    evidence_id: Optional[str] = Field(None, description="ID in OpenF1 (e.g., message ID)")
    snippet: str = Field(..., description="Summary of the evidence")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Full OpenF1 data object")


class TimelineEventType(str, Enum):
    """Types of events in a race timeline."""
    SAFETY_CAR = "SC"
    VIRTUAL_SC = "VSC"
    RED_FLAG = "RED"
    YELLOW_FLAG = "YELLOW"
    PIT_STOP = "PIT"
    WEATHER = "WEATHER"
    INCIDENT = "INCIDENT"
    PACE_CHANGE = "PACE"
    INFO = "INFO"


class TimelineItem(BaseModel):
    """A single event in the reconstructed race timeline."""
    lap: Optional[int] = Field(None, description="Lap number when event occurred")
    timestamp: Optional[str] = Field(None, description="Absolute timestamp (ISO format)")
    event_type: TimelineEventType = Field(..., description="Type of timeline event")
    title: str = Field(..., description="Short title of event")
    description: str = Field(..., description="Detailed description")
    
    # Evidence
    pdf_citations: List[PDFCitation] = Field(
        default_factory=list,
        description="Citations from ingested PDF"
    )
    openf1_evidence: List[OpenF1Evidence] = Field(
        default_factory=list,
        description="Evidence from OpenF1 API"
    )
    
    # Impact
    impacted_drivers: List[str] = Field(
        default_factory=list,
        description="Drivers affected by this event"
    )
    impact_summary: str = Field(
        default="",
        description="Plain-language summary of impact"
    )
    
    # Quality
    confidence: str = Field(
        default="Medium",
        description="High/Medium/Low based on evidence availability"
    )


class RaceTimeline(BaseModel):
    """Complete reconstructed race timeline combining PDF and OpenF1."""
    document_id: str = Field(..., description="Source document ID")
    session_info: Dict[str, Any] = Field(..., description="Session metadata from OpenF1")
    timeline_items: List[TimelineItem] = Field(
        default_factory=list,
        description="Ordered list of timeline events"
    )
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Metadata
    event_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of events by type"
    )
    drivers_involved: List[str] = Field(
        default_factory=list,
        description="All drivers mentioned in timeline"
    )
    debug_info: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Debug information about timeline construction (OpenF1 session resolution, endpoint counts, etc.)"
    )


class ExtractedEntities(BaseModel):
    """Entities extracted from a document."""
    drivers: Dict[str, List[int]] = Field(
        default_factory=dict,
        description="Driver names to driver numbers"
    )
    teams: List[str] = Field(default_factory=list)
    session_info: Optional[SessionInfo] = Field(None)
    incident_count: int = Field(default=0)
