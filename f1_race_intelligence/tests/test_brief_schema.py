"""Tests for Pydantic schemas and brief generation."""

import json
import pytest
from datetime import datetime

from rag.schemas import (
    Claim, ClaimType, ClaimEntity, Evidence, EvidenceStatus,
    RaceBrief, RaceEvent, TimeScope, SessionInfo, Chunk,
    DocumentMetadata,
)


class TestClaimSchema:
    """Test Claim schema."""

    def test_claim_creation(self):
        """Test creating a claim."""
        claim = Claim(
            claim_text="Driver had pace advantage",
            claim_type=ClaimType.PACE,
            confidence=0.85,
            rationale="Sector times support this",
        )
        
        assert claim.claim_text == "Driver had pace advantage"
        assert claim.claim_type == ClaimType.PACE
        assert claim.confidence == 0.85

    def test_claim_with_entities(self):
        """Test claim with entities."""
        entities = ClaimEntity(
            drivers=["Max Verstappen"],
            teams=["Red Bull Racing"],
        )
        
        claim = Claim(
            claim_text="Max was faster",
            claim_type=ClaimType.PACE,
            entities=entities,
            confidence=0.9,
            rationale="Test",
        )
        
        assert len(claim.entities.drivers) == 1
        assert len(claim.entities.teams) == 1

    def test_claim_with_time_scope(self):
        """Test claim with time scope."""
        time_scope = TimeScope(lap_start=10, lap_end=25)
        
        claim = Claim(
            claim_text="Consistent pace",
            claim_type=ClaimType.PACE,
            time_scope=time_scope,
            confidence=0.8,
            rationale="Test",
        )
        
        assert claim.time_scope.lap_start == 10
        assert claim.time_scope.lap_end == 25

    def test_claim_with_evidence(self):
        """Test claim with evidence."""
        evidence = Evidence(
            source="openf1_laps",
            data={"lap_times": [102.1, 102.2, 102.3]},
            relevance_score=0.95,
            interpretation="Consistent lap times",
        )
        
        claim = Claim(
            claim_text="Test claim",
            claim_type=ClaimType.PACE,
            evidence=[evidence],
            confidence=0.85,
            rationale="Test",
        )
        
        assert len(claim.evidence) == 1
        assert claim.evidence[0].relevance_score == 0.95

    def test_claim_confidence_bounds(self):
        """Test that confidence is bounded 0-1."""
        with pytest.raises(ValueError):
            Claim(
                claim_text="Test",
                claim_type=ClaimType.PACE,
                confidence=1.5,  # Invalid
                rationale="Test",
            )


class TestRaceBriefSchema:
    """Test RaceBrief schema."""

    def test_brief_creation(self):
        """Test creating a brief."""
        brief = RaceBrief(
            id="brief_1",
            document_id="doc_1",
            executive_summary="Race summary",
        )
        
        assert brief.id == "brief_1"
        assert brief.document_id == "doc_1"

    def test_brief_with_claims(self):
        """Test brief with claims."""
        claim = Claim(
            claim_text="Test claim",
            claim_type=ClaimType.PACE,
            confidence=0.8,
            rationale="Test",
        )
        
        brief = RaceBrief(
            id="brief_1",
            document_id="doc_1",
            executive_summary="Summary",
            extracted_claims=[claim],
        )
        
        assert len(brief.extracted_claims) == 1

    def test_brief_with_timeline(self):
        """Test brief with timeline."""
        event = RaceEvent(
            lap=15,
            event="Pit stop",
            source="pdf",
        )
        
        brief = RaceBrief(
            id="brief_1",
            document_id="doc_1",
            executive_summary="Summary",
            timeline=[event],
        )
        
        assert len(brief.timeline) == 1

    def test_brief_with_follow_ups(self):
        """Test brief with follow-up questions."""
        brief = RaceBrief(
            id="brief_1",
            document_id="doc_1",
            executive_summary="Summary",
            follow_up_questions=[
                "What was the strategy?",
                "How did weather affect pace?",
            ],
        )
        
        assert len(brief.follow_up_questions) == 2

    def test_brief_json_serialization(self):
        """Test that brief can be JSON serialized."""
        brief = RaceBrief(
            id="brief_1",
            document_id="doc_1",
            executive_summary="Summary",
        )
        
        # Should not raise
        json_str = brief.model_dump_json()
        assert isinstance(json_str, str)
        
        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["id"] == "brief_1"


class TestChunkSchema:
    """Test Chunk schema."""

    def test_chunk_creation(self):
        """Test creating a chunk."""
        chunk = Chunk(
            id="chunk_1",
            document_id="doc_1",
            content="This is a test chunk.",
            chunk_index=0,
        )
        
        assert chunk.id == "chunk_1"
        assert chunk.content == "This is a test chunk."

    def test_chunk_with_embedding(self):
        """Test chunk with embedding."""
        embedding = [0.1, 0.2, 0.3] * 128  # 384-dim
        
        chunk = Chunk(
            id="chunk_1",
            document_id="doc_1",
            content="Test",
            embedding=embedding,
            chunk_index=0,
        )
        
        assert chunk.embedding is not None
        assert len(chunk.embedding) == 384

    def test_chunk_with_metadata(self):
        """Test chunk with metadata."""
        chunk = Chunk(
            id="chunk_1",
            document_id="doc_1",
            content="Test",
            metadata={"page": 1, "section": "introduction"},
            chunk_index=0,
        )
        
        assert chunk.metadata["page"] == 1


class TestEvidenceStatus:
    """Test EvidenceStatus enum."""

    def test_status_values(self):
        """Test that all status values are valid."""
        statuses = [
            EvidenceStatus.SUPPORTED,
            EvidenceStatus.CONTRADICTED,
            EvidenceStatus.UNCLEAR,
            EvidenceStatus.INSUFFICIENT_DATA,
        ]
        
        assert len(statuses) == 4
        
        for status in statuses:
            assert isinstance(status.value, str)


class TestSessionInfo:
    """Test SessionInfo schema."""

    def test_session_info_creation(self):
        """Test creating session info."""
        session = SessionInfo(
            year=2023,
            gp_name="Monaco Grand Prix",
            session_type="RACE",
            session_id="session_1",
        )
        
        assert session.year == 2023
        assert "Monaco" in session.gp_name
        assert session.session_type == "RACE"
