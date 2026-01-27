"""Agent orchestration for claim extraction, planning, and evidence mapping."""

import json
import logging
import re
import uuid
from typing import List, Optional, Dict, Any

from rag.schemas import (
    Claim, ClaimType, ClaimEntity, Evidence, EvidenceStatus, RaceBrief,
    TimeScope, RaceEvent, ExtractedEntities, SessionInfo,
)
from rag.llm import LLMInterface
from rag.retrieve import Retriever
from rag.prompts import (
    EXTRACT_CLAIMS_SYSTEM_PROMPT, EXTRACT_CLAIMS_USER_TEMPLATE,
    EXTRACT_SESSION_SYSTEM_PROMPT, EXTRACT_SESSION_USER_TEMPLATE,
    GENERATE_SUMMARY_SYSTEM_PROMPT, GENERATE_SUMMARY_USER_TEMPLATE,
    MAP_EVIDENCE_SYSTEM_PROMPT, MAP_EVIDENCE_USER_TEMPLATE,
    GENERATE_FOLLOWUPS_SYSTEM_PROMPT, GENERATE_FOLLOWUPS_USER_TEMPLATE,
)
from openf1.api import OpenF1ClientInterface

logger = logging.getLogger(__name__)


class ClaimExtractor:
    """Extracts claims from documents using LLM."""

    def __init__(self, llm: LLMInterface):
        """Initialize claim extractor.
        
        Args:
            llm: LLM interface for generation
        """
        self.llm = llm

    def extract_claims(
        self,
        document_text: str,
        max_claims: int = 10,
    ) -> List[Claim]:
        """Extract claims from document text.
        
        Args:
            document_text: Text to extract claims from
            max_claims: Maximum number of claims to extract
            
        Returns:
            List of Claim objects
        """
        # Use document excerpt (limit to avoid token limits)
        excerpt = document_text[:4000]
        
        prompt = EXTRACT_CLAIMS_USER_TEMPLATE.format(document_excerpt=excerpt)
        
        try:
            response_json = self.llm.extract_json(
                prompt,
                system_prompt=EXTRACT_CLAIMS_SYSTEM_PROMPT,
            )
            
            claims = []
            raw_claims = response_json.get("claims", [])
            
            for raw_claim in raw_claims[:max_claims]:
                try:
                    claim = Claim(
                        id=str(uuid.uuid4()),
                        claim_text=raw_claim.get("claim_text", ""),
                        claim_type=ClaimType(raw_claim.get("claim_type", "other")),
                        entities=ClaimEntity(
                            drivers=raw_claim.get("drivers", []),
                            teams=raw_claim.get("teams", []),
                        ),
                        time_scope=TimeScope(
                            lap_start=raw_claim.get("lap_start"),
                            lap_end=raw_claim.get("lap_end"),
                        ) if raw_claim.get("lap_start") or raw_claim.get("lap_end") else None,
                        confidence=raw_claim.get("confidence", 0.5),
                        rationale=raw_claim.get("rationale", ""),
                    )
                    claims.append(claim)
                except Exception as e:
                    logger.warning(f"Failed to parse claim: {e}")
            
            logger.info(f"Extracted {len(claims)} claims")
            return claims
        
        except Exception as e:
            logger.error(f"Error extracting claims: {e}")
            return []


class EntityExtractor:
    """Extracts session and entity information from documents."""

    def __init__(self, llm: LLMInterface):
        """Initialize entity extractor.
        
        Args:
            llm: LLM interface for generation
        """
        self.llm = llm

    def extract_session_info(self, document_text: str) -> Optional[SessionInfo]:
        """Extract session information from document.
        
        Args:
            document_text: Text to extract from
            
        Returns:
            SessionInfo or None if not found
        """
        excerpt = document_text[:2000]
        
        prompt = EXTRACT_SESSION_USER_TEMPLATE.format(document_excerpt=excerpt)
        
        try:
            response_json = self.llm.extract_json(
                prompt,
                system_prompt=EXTRACT_SESSION_SYSTEM_PROMPT,
            )
            
            session = SessionInfo(
                year=response_json.get("year", 2023),
                gp_name=response_json.get("gp_name", "Unknown"),
                session_type=response_json.get("session_type", "RACE"),
                session_id="",  # Will be set by agent
                location=response_json.get("location"),
                date=response_json.get("date"),
            )
            
            logger.info(f"Extracted session: {session.gp_name} {session.year}")
            return session
        
        except Exception as e:
            logger.error(f"Error extracting session info: {e}")
            return None

    def extract_entities(self, document_text: str) -> ExtractedEntities:
        """Extract drivers, teams, and other entities.
        
        Args:
            document_text: Text to extract from
            
        Returns:
            ExtractedEntities
        """
        entities = ExtractedEntities()
        
        # Simple pattern matching for driver numbers
        driver_pattern = r'(Driver|P\d|Car)\s*#?(\d{1,3})'
        matches = re.findall(driver_pattern, document_text, re.IGNORECASE)
        
        # Extract common F1 team names
        teams = set()
        team_pattern = r'(Red Bull|Mercedes|Ferrari|McLaren|Aston Martin|Alpine|Williams|Alfa Romeo|Haas|AlphaTauri)'
        team_matches = re.findall(team_pattern, document_text)
        teams.update(team_matches)
        
        entities.teams = list(teams)
        
        logger.info(f"Extracted entities: {len(entities.teams)} teams")
        return entities


class EvidencePlanner:
    """Plans which OpenF1 API calls to make based on claims."""

    def plan_evidence_retrieval(
        self,
        claims: List[Claim],
        session_info: Optional[SessionInfo] = None,
    ) -> Dict[str, List[str]]:
        """Plan which OpenF1 endpoints to call.
        
        Args:
            claims: List of extracted claims
            session_info: Session information
            
        Returns:
            Dict mapping claim_id to list of evidence types to retrieve
        """
        plan = {}
        
        for claim in claims:
            evidence_types = set()
            
            # Based on claim type, decide what evidence to get
            if claim.claim_type == ClaimType.PACE:
                evidence_types.update(["laps", "stints"])
            elif claim.claim_type == ClaimType.STRATEGY:
                evidence_types.update(["pit_stops", "stints", "laps"])
            elif claim.claim_type == ClaimType.INCIDENT:
                evidence_types.update(["race_control", "laps"])
            elif claim.claim_type == ClaimType.TYRES:
                evidence_types.update(["stints", "laps"])
            elif claim.claim_type == ClaimType.PIT_STOP:
                evidence_types.update(["pit_stops", "laps"])
            elif claim.claim_type == ClaimType.DRIVER_PERFORMANCE:
                evidence_types.update(["laps", "stints", "race_control"])
            else:
                evidence_types.update(["race_control", "laps"])
            
            plan[claim.id] = list(evidence_types)
        
        logger.info(f"Planned evidence retrieval for {len(claims)} claims")
        return plan


class EvidenceMapper:
    """Maps claims to supporting/contradicting evidence."""

    def __init__(self, llm: LLMInterface):
        """Initialize evidence mapper.
        
        Args:
            llm: LLM interface for generation
        """
        self.llm = llm

    def map_evidence_to_claim(
        self,
        claim: Claim,
        evidence_data: Dict[str, Any],
    ) -> Claim:
        """Map evidence to a claim and update status.
        
        Args:
            claim: The claim to evaluate
            evidence_data: Evidence from OpenF1
            
        Returns:
            Updated claim with evidence and status
        """
        if not evidence_data or not any(evidence_data.values()):
            claim.status = EvidenceStatus.INSUFFICIENT_DATA
            claim.evidence = []
            return claim
        
        # Format evidence for LLM
        evidence_str = json.dumps(evidence_data, default=str, indent=2)[:2000]
        
        prompt = MAP_EVIDENCE_USER_TEMPLATE.format(
            claim_text=claim.claim_text,
            evidence_data=evidence_str,
        )
        
        try:
            response_json = self.llm.extract_json(
                prompt,
                system_prompt=MAP_EVIDENCE_SYSTEM_PROMPT,
            )
            
            # Update claim with evaluation
            claim.status = EvidenceStatus(response_json.get("status", "unclear"))
            claim.confidence = response_json.get("confidence", claim.confidence)
            claim.rationale = response_json.get("rationale", claim.rationale)
            
            # Add evidence objects
            for source, data in evidence_data.items():
                if data:  # Only add if data exists
                    evidence = Evidence(
                        source=source,
                        data=data if isinstance(data, dict) else {"raw": str(data)},
                        relevance_score=response_json.get("confidence", 0.5),
                        interpretation=response_json.get("rationale", ""),
                    )
                    claim.evidence.append(evidence)
        
        except Exception as e:
            logger.warning(f"Error mapping evidence: {e}")
            claim.status = EvidenceStatus.UNCLEAR
        
        return claim


class SummaryGenerator:
    """Generates executive summaries and follow-up questions."""

    def __init__(self, llm: LLMInterface):
        """Initialize summary generator.
        
        Args:
            llm: LLM interface for generation
        """
        self.llm = llm

    def generate_summary(
        self,
        document_text: str,
        claims: List[Claim],
    ) -> str:
        """Generate executive summary.
        
        Args:
            document_text: Original document text
            claims: Extracted claims
            
        Returns:
            Summary text
        """
        # Prepare claims summary
        claims_summary = "\n".join([
            f"- {c.claim_text} ({c.claim_type.value}, confidence={c.confidence:.2f})"
            for c in claims[:5]  # Top 5 claims
        ])
        
        excerpt = document_text[:2000]
        
        prompt = GENERATE_SUMMARY_USER_TEMPLATE.format(
            claims_summary=claims_summary,
            document_excerpt=excerpt,
        )
        
        try:
            summary = self.llm.generate(
                prompt,
                system_prompt=GENERATE_SUMMARY_SYSTEM_PROMPT,
            )
            logger.info("Generated executive summary")
            return summary
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return "Summary generation failed."

    def generate_follow_up_questions(
        self,
        summary: str,
        claims: List[Claim],
        timeline: List[RaceEvent],
    ) -> List[str]:
        """Generate follow-up questions.
        
        Args:
            summary: Executive summary
            claims: Extracted claims
            timeline: Timeline of events
            
        Returns:
            List of follow-up questions
        """
        claims_summary = ", ".join([c.claim_text[:50] + "..." for c in claims[:3]])
        timeline_summary = f"{len(timeline)} key events identified"
        
        prompt = GENERATE_FOLLOWUPS_USER_TEMPLATE.format(
            summary=summary[:500],
            claims_summary=claims_summary,
            timeline_summary=timeline_summary,
        )
        
        try:
            response_json = self.llm.extract_json(
                prompt,
                system_prompt=GENERATE_FOLLOWUPS_SYSTEM_PROMPT,
            )
            
            questions = response_json.get("questions", [])
            logger.info(f"Generated {len(questions)} follow-up questions")
            return questions
        
        except Exception as e:
            logger.error(f"Error generating follow-ups: {e}")
            return [
                "What external factors influenced the race outcome?",
                "How could different strategic decisions have changed the result?",
            ]


class RaceAgent:
    """Main agent orchestrating the entire race intelligence pipeline."""

    def __init__(
        self,
        llm: LLMInterface,
        retriever: Retriever,
        openf1_client: OpenF1ClientInterface,
    ):
        """Initialize race agent.
        
        Args:
            llm: LLM interface
            retriever: Retriever for document chunks
            openf1_client: OpenF1 API client
        """
        self.llm = llm
        self.retriever = retriever
        self.openf1_client = openf1_client
        
        self.claim_extractor = ClaimExtractor(llm)
        self.entity_extractor = EntityExtractor(llm)
        self.evidence_planner = EvidencePlanner()
        self.evidence_mapper = EvidenceMapper(llm)
        self.summary_generator = SummaryGenerator(llm)

    def build_race_brief(
        self,
        document_text: str,
        document_id: str,
    ) -> RaceBrief:
        """Build complete race intelligence brief.
        
        This is the main orchestration method that:
        1. Extracts entities and session info
        2. Extracts claims from the document
        3. Plans OpenF1 API calls based on claims
        4. Retrieves evidence from OpenF1
        5. Maps evidence to claims
        6. Generates summary and follow-ups
        7. Assembles final brief
        
        Args:
            document_text: Full document text
            document_id: Document ID
            
        Returns:
            Complete RaceBrief
        """
        logger.info("Starting race brief generation pipeline")
        
        # Step 1: Extract session and entities
        session_info = self.entity_extractor.extract_session_info(document_text)
        entities = self.entity_extractor.extract_entities(document_text)
        
        # Step 2: Extract claims
        claims = self.claim_extractor.extract_claims(document_text)
        
        # Step 3: Plan evidence retrieval
        plan = self.evidence_planner.plan_evidence_retrieval(claims, session_info)
        
        # Step 4: Search for OpenF1 session
        session_id = None
        if session_info:
            sessions = self.openf1_client.search_sessions(
                year=session_info.year,
                gp_name=session_info.gp_name,
                session_type=session_info.session_type,
            )
            if sessions:
                session_id = sessions[0].get("session_id")
                session_info.session_id = session_id
                logger.info(f"Found OpenF1 session: {session_id}")
        
        # Step 5: Retrieve evidence for each claim
        if session_id:
            for claim in claims:
                evidence_types = plan.get(claim.id, [])
                evidence_data = {}
                
                # Fetch relevant evidence types
                if "race_control" in evidence_types:
                    evidence_data["race_control"] = self.openf1_client.get_race_control_messages(session_id)[:10]
                
                if "laps" in evidence_types:
                    # Get lap data for relevant drivers
                    for driver in claim.entities.drivers[:2]:  # Limit to 2 drivers
                        try:
                            laps = self.openf1_client.get_laps(session_id)
                            evidence_data[f"laps_{driver}"] = laps[:20]  # Top 20 laps
                        except:
                            pass
                
                if "stints" in evidence_types:
                    stints = self.openf1_client.get_stints(session_id)
                    evidence_data["stints"] = stints[:10]
                
                if "pit_stops" in evidence_types:
                    pit_stops = self.openf1_client.get_pit_stops(session_id)
                    evidence_data["pit_stops"] = pit_stops[:10]
                
                # Map evidence to claim
                claim = self.evidence_mapper.map_evidence_to_claim(claim, evidence_data)
        
        # Step 6: Generate summary
        summary = self.summary_generator.generate_summary(document_text, claims)
        
        # Step 7: Build timeline
        timeline = self._build_timeline(document_text, claims, session_id)
        
        # Step 8: Generate follow-up questions
        followups = self.summary_generator.generate_follow_up_questions(summary, claims, timeline)
        
        # Step 9: Assemble brief
        brief = RaceBrief(
            id=str(uuid.uuid4()),
            document_id=document_id,
            executive_summary=summary,
            extracted_claims=claims,
            timeline=timeline,
            follow_up_questions=followups,
            session_info={
                "year": session_info.year if session_info else None,
                "gp_name": session_info.gp_name if session_info else None,
                "session_type": session_info.session_type if session_info else None,
            },
            claim_stats={
                "total": len(claims),
                "supported": sum(1 for c in claims if c.status == EvidenceStatus.SUPPORTED),
                "unclear": sum(1 for c in claims if c.status == EvidenceStatus.UNCLEAR),
                "contradicted": sum(1 for c in claims if c.status == EvidenceStatus.CONTRADICTED),
            }
        )
        
        logger.info(f"Race brief generated: {brief.claim_stats}")
        return brief

    def _build_timeline(
        self,
        document_text: str,
        claims: List[Claim],
        session_id: Optional[str] = None,
    ) -> List[RaceEvent]:
        """Build timeline from claims and race control.
        
        Args:
            document_text: Document text
            claims: Extracted claims
            session_id: OpenF1 session ID
            
        Returns:
            List of RaceEvent objects
        """
        events = []
        
        # Add events from claims
        for claim in claims:
            if claim.time_scope and claim.claim_type == ClaimType.INCIDENT:
                event = RaceEvent(
                    lap=claim.time_scope.lap_start,
                    event=claim.claim_text,
                    source="pdf",
                    affected_drivers=claim.entities.drivers,
                )
                events.append(event)
        
        # Add race control messages if available
        if session_id:
            try:
                messages = self.openf1_client.get_race_control_messages(session_id)
                for msg in messages[:5]:  # Top 5 messages
                    event = RaceEvent(
                        lap=msg.get("lap"),
                        time=msg.get("time"),
                        event=msg.get("message", ""),
                        source="openf1",
                    )
                    events.append(event)
            except:
                pass
        
        # Sort by lap number
        events.sort(key=lambda x: x.lap or 0)
        
        return events
