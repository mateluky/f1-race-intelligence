"""Application service facade for RAG pipeline - bridges Streamlit UI to RAG internals."""

import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from rag.ingest import extract_text_from_pdf, semantic_chunk, clean_text, IngestConfig, Chunk
from rag.embed import get_embedder
from rag.store import get_vector_store
from rag.retrieve import Retriever
from rag.llm import get_llm
from rag.agent import RaceAgent
from rag.timeline import TimelineBuilder
from openf1.api import get_openf1_client
from rag.schemas import RaceBrief, RaceTimeline

logger = logging.getLogger(__name__)


def make_json_serializable(obj: Any) -> Any:
    """Recursively convert objects to JSON-serializable types.
    
    Args:
        obj: Object to convert
        
    Returns:
        JSON-serializable version of obj
    """
    if obj is None:
        return None
    elif isinstance(obj, (str, int, float, bool)):
        return obj
    elif isinstance(obj, (list, tuple)):
        return [make_json_serializable(item) for item in obj]
    elif isinstance(obj, dict):
        return {str(k): make_json_serializable(v) for k, v in obj.items()}
    elif hasattr(obj, "model_dump"):  # Pydantic model
        return make_json_serializable(obj.model_dump(mode="python"))
    elif hasattr(obj, "__dict__"):
        return make_json_serializable(obj.__dict__)
    else:
        return str(obj)


class AppService:
    """Facade service for Streamlit UI - orchestrates RAG pipeline."""

    def __init__(self, use_mock: bool = True):
        """Initialize app service.
        
        Args:
            use_mock: If True, use mock embedder/LLM for demo mode.
                      If False, try Ollama LLM (requires Ollama running), with fallback to mock.
        """
        self.use_mock = use_mock
        self.embedder = get_embedder(mode="mock" if use_mock else "sentence_transformer")
        self.vector_store = get_vector_store(mode="memory")
        self.retriever = Retriever(self.embedder, self.vector_store, top_k=5)
        
        # Get LLM with fallback: try Ollama, fall back to MockLLM if unavailable
        llm_mode = "mock" if use_mock else "ollama"
        self.llm, self.using_ollama_fallback = get_llm(mode=llm_mode, fallback_on_error=True)
        
        self.openf1_client = get_openf1_client(mode="mock" if use_mock else "real")
        self.agent = RaceAgent(self.llm, self.retriever, self.openf1_client)
        
        # Timeline builder for race timeline reconstruction
        self.timeline_builder = TimelineBuilder(self.retriever, self.llm)
        
        # Cache ingested documents: doc_id -> (text, chunks, embeddings)
        self.ingested_docs: Dict[str, Dict[str, Any]] = {}
        
        fallback_msg = " (FALLBACK: Using MockLLM)" if self.using_ollama_fallback else ""
        logger.info(f"AppService initialized (mock_mode={use_mock}){fallback_msg}")

    def ingest_pdf(self, pdf_path: str, doc_id: str) -> Dict[str, Any]:
        """Ingest a PDF file and store in vector DB.
        
        Args:
            pdf_path: Path to PDF file
            doc_id: Document identifier
            
        Returns:
            Dict with ingestion stats
        """
        try:
            # Extract text
            text = extract_text_from_pdf(pdf_path)
            logger.info(f"Extracted {len(text)} chars from {pdf_path}")
            
            # Clean text
            cleaned_text = clean_text(text)
            
            # Chunk
            config = IngestConfig()
            chunks = semantic_chunk(
                cleaned_text,
                chunk_size=config.chunk_size,
                chunk_overlap=config.chunk_overlap,
            )
            
            # Create chunk objects
            chunk_objects = []
            for idx, chunk_text in enumerate(chunks):
                chunk_obj = Chunk(
                    id=f"{doc_id}_chunk_{idx}",
                    document_id=doc_id,
                    content=chunk_text,
                    chunk_index=idx,
                )
                chunk_objects.append(chunk_obj)
            
            # Embed
            embeddings = self.embedder.embed_texts([c.content for c in chunk_objects])
            
            # Store in vector DB
            self.vector_store.add_chunks(chunk_objects, embeddings)
            
            # Cache
            self.ingested_docs[doc_id] = {
                "text": cleaned_text,
                "chunks": [c.model_dump(mode="python") for c in chunk_objects],
                "num_chunks": len(chunk_objects),
            }
            
            logger.info(f"Ingested {len(chunk_objects)} chunks for {doc_id}")
            
            return {
                "success": True,
                "doc_id": doc_id,
                "num_chunks": len(chunk_objects),
                "text_length": len(cleaned_text),
                "message": f"Successfully ingested {len(chunk_objects)} chunks",
            }
        
        except FileNotFoundError as e:
            logger.error(f"PDF not found: {e}")
            return {"success": False, "error": f"File not found: {str(e)}"}
        except ImportError as e:
            logger.error(f"Dependency missing: {e}")
            return {"success": False, "error": f"Missing dependency: {str(e)}"}
        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
            return {"success": False, "error": f"Ingestion failed: {str(e)}"}

    def build_brief(
        self,
        doc_id: str,
        year: Optional[int] = None,
        gp_name: Optional[str] = None,
        session_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build race intelligence brief.
        
        Args:
            doc_id: Document ID (must be ingested first)
            year: Optional race year
            gp_name: Optional GP name
            session_type: Optional session type
            
        Returns:
            Dict with brief data
        """
        try:
            if doc_id not in self.ingested_docs:
                return {
                    "success": False,
                    "error": f"Document {doc_id} not ingested. Please ingest PDF first.",
                }
            
            doc_data = self.ingested_docs[doc_id]
            text = doc_data["text"]
            
            # Build brief using agent
            brief: RaceBrief = self.agent.build_race_brief(text, doc_id)
            
            # Convert to JSON-serializable format
            brief_dict = make_json_serializable(brief.model_dump(mode="python"))
            
            logger.info(f"Built brief for {doc_id}")
            
            return {
                "success": True,
                "doc_id": doc_id,
                "brief": brief_dict,
                "message": "Brief generated successfully",
            }
        
        except Exception as e:
            logger.error(f"Brief generation failed: {e}")
            return {"success": False, "error": f"Brief generation failed: {str(e)}"}

    def query(self, question: str, doc_id: str) -> Dict[str, Any]:
        """Query about a document using RAG.
        
        Args:
            question: Question to ask
            doc_id: Document ID to query against
            
        Returns:
            Dict with answer and sources
        """
        try:
            if doc_id not in self.ingested_docs:
                return {
                    "success": False,
                    "error": f"Document {doc_id} not ingested. Please ingest PDF first.",
                }
            
            # Retrieve relevant chunks
            result = self.retriever.retrieve(question, document_id=doc_id, top_k=3)
            
            # Build sources
            sources = [
                {
                    "content": chunk.content[:200],
                    "score": float(score),
                    "chunk_id": chunk.id,
                }
                for chunk, score in zip(result.chunks, result.scores)
            ]
            
            # Generate answer using LLM
            prompt = f"Based on the following context, answer this question: {question}\n\nContext:\n"
            if result.chunks:
                prompt += "\n".join([c.content for c in result.chunks[:3]])
            
            answer = self.llm.generate(prompt)
            
            logger.info(f"Answered query for {doc_id}")
            
            return {
                "success": True,
                "answer": answer,
                "sources": sources,
                "num_sources": len(sources),
            }
        
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return {"success": False, "error": f"Query failed: {str(e)}"}

    def get_ingested_docs(self) -> List[str]:
        """Get list of ingested document IDs."""
        return list(self.ingested_docs.keys())

    def generate_race_story(self, doc_id: str, brief_dict: Dict[str, Any], audience: str = "fan") -> str:
        """Generate audience-specific race story/narrative.
        
        Args:
            doc_id: Document ID
            brief_dict: Brief data (output from build_brief)
            audience: One of "fan", "analyst", "newbie"
            
        Returns:
            Markdown narrative
        """
        try:
            summary = brief_dict.get("executive_summary", "")
            claims = brief_dict.get("extracted_claims", [])[:5]
            timeline = brief_dict.get("timeline", [])
            
            if audience == "fan":
                # Narrative, story-like, highlights
                prompt = f"""Write a compelling race story for a casual F1 fan (2-3 paragraphs):
Summary: {summary}
Key events: {json.dumps([c.get('claim_text') for c in claims], indent=2)}
Use vivid language, avoid jargon, focus on drama and excitement."""
            
            elif audience == "analyst":
                # Technical, evidence-heavy
                prompt = f"""Write a technical analysis for an F1 analyst (3-4 paragraphs):
Summary: {summary}
Claims with confidence: {json.dumps([{'text': c.get('claim_text'), 'confidence': c.get('confidence')} for c in claims], indent=2)}
Focus on evidence, data, and methodology. Include confidence levels."""
            
            else:  # newbie
                # Simple, glossary-friendly
                prompt = f"""Write a beginner-friendly race explanation (2-3 paragraphs):
Summary: {summary}
Key points: {json.dumps([c.get('claim_text')[:50] for c in claims], indent=2)}
Use simple language, short sentences, explain F1 terms. Assume no prior knowledge."""
            
            story = self.llm.generate(prompt)
            logger.info(f"Generated {audience} race story for {doc_id}")
            
            return story
        
        except Exception as e:
            logger.warning(f"Race story generation failed: {e}")
            return brief_dict.get("executive_summary", "Race story generation failed")

    def action_items(self, doc_id: str, brief_dict: Dict[str, Any]) -> List[Dict[str, str]]:
        """Extract action items and recommendations.
        
        Args:
            doc_id: Document ID
            brief_dict: Brief data
            
        Returns:
            List of action items with issue, cause, and recommended action
        """
        try:
            claims = brief_dict.get("extracted_claims", [])
            unclear_claims = [c for c in claims if c.get("status") == "unclear"]
            
            if not unclear_claims:
                # Use top claims by confidence
                unclear_claims = sorted(claims, key=lambda x: x.get("confidence", 0), reverse=True)[:3]
            
            prompt = f"""Based on these uncertain/low-confidence claims, suggest 2-3 action items:
{json.dumps([c.get('claim_text') for c in unclear_claims], indent=2)}

For each action item, provide JSON:
- issue: what needs investigation
- likely_cause: why it's unclear
- recommended_action: what to do next
"""
            
            response_json = self.llm.extract_json(prompt)
            items = response_json.get("action_items", [])
            
            logger.info(f"Generated {len(items)} action items for {doc_id}")
            return items
        
        except Exception as e:
            logger.warning(f"Action items generation failed: {e}")
            return []

    def auto_questions(self, doc_id: str, brief_dict: Dict[str, Any]) -> List[Dict[str, str]]:
        """Generate auto-suggested follow-up questions.
        
        Args:
            doc_id: Document ID
            brief_dict: Brief data
            
        Returns:
            List of questions with suggested evidence type
        """
        try:
            summary = brief_dict.get("executive_summary", "")
            claims = brief_dict.get("extracted_claims", [])[:5]
            
            prompt = f"""Based on this race brief, suggest 3-5 natural follow-up questions:
Summary: {summary}
Top claims: {json.dumps([c.get('claim_text') for c in claims], indent=2)}

For each question, return JSON:
- question: natural follow-up
- suggested_evidence: "pdf" or "openf1" or "both"
- why_relevant: why this question matters
"""
            
            response_json = self.llm.extract_json(prompt)
            questions = response_json.get("questions", [])
            
            logger.info(f"Generated {len(questions)} auto-questions for {doc_id}")
            return questions
        
        except Exception as e:
            logger.warning(f"Auto-questions generation failed: {e}")
            return brief_dict.get("follow_up_questions", [])

    def claim_confidence_breakdown(self, doc_id: str, brief_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate detailed confidence breakdown for each claim.
        
        Args:
            doc_id: Document ID
            brief_dict: Brief data
            
        Returns:
            List of claims with detailed confidence analysis
        """
        try:
            claims = brief_dict.get("extracted_claims", [])
            
            breakdown = []
            for claim in claims:
                evidence = claim.get("evidence", [])
                pdf_evidence = [e for e in evidence if "pdf" in e.get("source", "").lower()]
                openf1_evidence = [e for e in evidence if "openf1" in e.get("source", "").lower()]
                
                # Simple scoring
                pdf_score = len(pdf_evidence) * 0.5  # max 1.0 with 2+ sources
                openf1_score = len(openf1_evidence) * 0.5
                final_confidence = min((pdf_score + openf1_score) / 2.0, 1.0)
                
                # Determine level
                conf_value = claim.get("confidence", 0.5)
                if conf_value >= 0.75:
                    conf_level = "High"
                elif conf_value >= 0.5:
                    conf_level = "Medium"
                else:
                    conf_level = "Low"
                
                breakdown.append({
                    "claim_id": claim.get("id", "unknown"),
                    "claim_text": claim.get("claim_text", ""),
                    "pdf_support_score": round(pdf_score, 2),
                    "openf1_support_score": round(openf1_score, 2),
                    "final_confidence": round(final_confidence, 2),
                    "confidence_level": conf_level,
                    "pdf_evidence_count": len(pdf_evidence),
                    "openf1_evidence_count": len(openf1_evidence),
                    "rationale": claim.get("rationale", ""),
                })
            
            logger.info(f"Generated confidence breakdown for {len(breakdown)} claims")
            return breakdown
        
        except Exception as e:
            logger.warning(f"Confidence breakdown failed: {e}")
            return []
    def build_timeline(
        self,
        doc_id: str,
        year: Optional[int] = None,
        gp_name: Optional[str] = None,
        session_type: str = "RACE",
    ) -> Dict[str, Any]:
        """Build race timeline from PDF + OpenF1 data.
        
        Combines events extracted from PDF (via LLM + RAG citations) with
        structured OpenF1 data (race control, pit stops, stints).
        
        Args:
            doc_id: Document ID
            year: F1 season year (optional)
            gp_name: Grand Prix name (optional)
            session_type: Session type (RACE, QUALI, FP1, FP2, FP3)
            
        Returns:
            Dict with success status and timeline data
        """
        try:
            # Build session metadata
            session_metadata = {
                "year": year,
                "gp_name": gp_name,
                "session_type": session_type,
            }
            
            # Build race timeline
            race_timeline = self.timeline_builder.build_race_timeline(
                doc_id=doc_id,
                openf1_client=self.openf1_client,
                retriever=self.retriever,
                session_metadata=session_metadata,
            )
            
            # Convert to JSON-serializable dict
            timeline_dict = make_json_serializable(race_timeline.model_dump(mode="python"))
            
            return {
                "success": True,
                "timeline": timeline_dict,
                "event_count": len(race_timeline.timeline_items),
                "message": f"Built timeline with {len(race_timeline.timeline_items)} events",
            }
        
        except Exception as e:
            logger.error(f"Failed to build timeline: {e}")
            return {
                "success": False,
                "error": str(e),
                "timeline": None,
            }