"""Application service facade for RAG pipeline - bridges Streamlit UI to RAG internals."""

import json
import logging
import re
import tempfile
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

# GP name normalization map: common variations -> canonical name
GP_NORMALIZATION_MAP = {
    "australia": "Australian Grand Prix",
    "aussie": "Australian Grand Prix",
    "bahrain": "Bahrain Grand Prix",
    "saudi": "Saudi Arabian Grand Prix",
    "monaco": "Monaco Grand Prix",
    "spain": "Spanish Grand Prix",
    "canada": "Canadian Grand Prix",
    "austria": "Austrian Grand Prix",
    "britain": "British Grand Prix",
    "british": "British Grand Prix",
    "hungary": "Hungarian Grand Prix",
    "netherlands": "Dutch Grand Prix",
    "belgium": "Belgian Grand Prix",
    "italy": "Italian Grand Prix",
    "singapore": "Singapore Grand Prix",
    "japan": "Japanese Grand Prix",
    "mexico": "Mexico City Grand Prix",
    "brazil": "Brazilian Grand Prix",
    "usa": "United States Grand Prix",
    "united states": "United States Grand Prix",
    "abu dhabi": "Abu Dhabi Grand Prix",
}


def make_json_serializable(obj: Any) -> Any:
    """Recursively convert objects to JSON-serializable types.
    
    Args:
        obj: Object to convert
        
    Returns:
        JSON-serializable version of obj
    """
    if obj is None:
        return None
    elif isinstance(obj, bool):  # Check bool before int (bool is subclass of int)
        return obj
    elif isinstance(obj, Enum):
        # Check Enum BEFORE str! String enums inherit from str so isinstance(obj, str) would match first
        # Convert Enum to its value, ensuring we get a pure string
        return str(obj.value) if isinstance(obj.value, str) else make_json_serializable(obj.value)
    elif isinstance(obj, (str, int, float)):
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



def normalize_gp_name(gp_text: str) -> Optional[str]:
    """Normalize GP name variations to canonical form.
    
    Handles:
    - Case variations
    - Sponsor prefixes (e.g., "Formula 1 Louis Vuitton Australian Grand Prix")
    - Common abbreviations (Australia -> Australian Grand Prix)
    - Partial names (Monaco -> Monaco Grand Prix)
    
    Args:
        gp_text: Raw GP name from document
        
    Returns:
        Canonical GP name or None if not recognized
    """
    if not gp_text:
        return None
    
    # Clean: remove extra whitespace, convert to lowercase
    cleaned = gp_text.lower().strip()
    
    # Remove sponsor prefixes (everything before "Grand Prix" in first match)
    sponsor_pattern = r"^.*?(?=Australian|Bahrain|Saudi|Monaco|Spanish|Canadian|Austrian|British|Hungarian|Dutch|Belgian|Italian|Singapore|Japanese|Mexico|Brazilian|United States|Abu Dhabi)"
    cleaned = re.sub(sponsor_pattern, "", cleaned).strip()
    
    # Direct lookup in normalization map
    for key, canonical in GP_NORMALIZATION_MAP.items():
        if key in cleaned or cleaned == key:
            return canonical
    
    # Try to extract GP name from "X Grand Prix" pattern
    gp_match = re.search(r"(\w+(?:\s+\w+)?)\s+Grand Prix", gp_text, re.IGNORECASE)
    if gp_match:
        gp_prefix = gp_match.group(1).lower().strip()
        # Check again against normalized map
        for key, canonical in GP_NORMALIZATION_MAP.items():
            if key in gp_prefix or gp_prefix in key:
                return canonical
        # If not in map, construct "X Grand Prix" assuming it's valid
        return f"{gp_match.group(1)} Grand Prix"
    
    return None


def extract_metadata_heuristic(filename: str, text_excerpt: str) -> Tuple[Optional[int], Optional[str], Optional[str], str]:
    """Extract metadata using filename and text heuristics (Stage 1).
    
    Fast, reliable extraction without LLM.
    
    Args:
        filename: PDF filename (e.g., "2025_Australian_Grand_Prix.pdf")
        text_excerpt: First 2000 chars of PDF text
        
    Returns:
        (year, gp_name, session_type, confidence_summary)
    """
    year = None
    gp_name = None
    session_type = None
    confidence_notes = []
    
    # Extract year from filename (e.g., "2025_Australian")
    filename_year_match = re.search(r'(\d{4})(?:_|\s)', filename, re.IGNORECASE)
    if filename_year_match:
        try:
            year = int(filename_year_match.group(1))
            if 2014 <= year <= datetime.now().year + 1:
                confidence_notes.append(f"Year {year} from filename")
            else:
                year = None
        except (ValueError, TypeError):
            pass
    
    # Extract GP name from filename patterns like "2025_Australian_Grand_Prix" or "Australian GP"
    # Pattern 1: YYYY_Word_Word_Grand_Prix
    filename_gp_match = re.search(r'_?(\w+(?:_\w+)?)(?:_Grand_Prix)?\.pdf', filename, re.IGNORECASE)
    if filename_gp_match:
        gp_candidate = filename_gp_match.group(1).replace('_', ' ')
        normalized = normalize_gp_name(gp_candidate)
        if normalized:
            gp_name = normalized
            confidence_notes.append(f"GP '{gp_name}' from filename")
    
    # Extract from text patterns
    # Pattern: "2025 Australian Grand Prix" or "Australian Grand Prix 2025"
    text_gp_year_match = re.search(r'(\d{4})\s+(\w+(?:\s+\w+)?)\s+Grand\s+Prix', text_excerpt, re.IGNORECASE)
    if text_gp_year_match:
        try:
            text_year = int(text_gp_year_match.group(1))
            if 2014 <= text_year <= datetime.now().year + 1:
                if not year:
                    year = text_year
                    confidence_notes.append(f"Year {text_year} from text")
        except (ValueError, TypeError):
            pass
        
        text_gp = text_gp_year_match.group(2)
        normalized = normalize_gp_name(text_gp)
        if normalized and not gp_name:
            gp_name = normalized
            confidence_notes.append(f"GP '{gp_name}' from text")
    
    # Detect session type from text
    if re.search(r'\brace\b|\bRACE\b', text_excerpt):
        session_type = "RACE"
        confidence_notes.append("Session type RACE from text")
    elif re.search(r'\bqualif|\bQUALIF', text_excerpt):
        session_type = "QUALIFYING"
        confidence_notes.append("Session type QUALIFYING from text")
    elif re.search(r'\bsprint\b|\bSPRINT\b', text_excerpt):
        session_type = "SPRINT"
        confidence_notes.append("Session type SPRINT from text")
    
    summary = " | ".join(confidence_notes) if confidence_notes else "No filename/text patterns matched"
    
    return year, gp_name, session_type, summary


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
        
        # Log OpenF1 client type for debugging
        openf1_client_type = type(self.openf1_client).__name__
        self.openf1_client_type = openf1_client_type
        
        fallback_msg = " (FALLBACK: Using MockLLM)" if self.using_ollama_fallback else ""
        logger.info(f"AppService initialized (mock_mode={use_mock}){fallback_msg}")
        logger.info(f"[OpenF1] Client type: {openf1_client_type}")

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
            
            # Cache - store filename for heuristic extraction
            self.ingested_docs[doc_id] = {
                "text": cleaned_text,
                "raw_text": text[:2000],  # First 2000 chars for heuristic
                "filename": Path(pdf_path).name,
                "chunks": [c.model_dump(mode="python") for c in chunk_objects],
                "num_chunks": len(chunk_objects),
            }
            
            logger.info(f"Ingested {len(chunk_objects)} chunks for {doc_id} from {Path(pdf_path).name}")
            
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

    def extract_race_metadata(self, doc_id: str) -> Dict[str, Any]:
        """Extract race metadata (year, GP name, session type) using 2-stage approach.
        
        Stage 1 (Heuristic): Fast extraction from filename and text patterns
        Stage 2 (LLM): Fallback to Ollama LLM if heuristic fails
        
        Uses the ingested PDF to automatically detect:
        - F1 season year
        - Grand Prix name
        - Session type (RACE, QUALIFYING, SPRINT, etc.)
        
        Args:
            doc_id: Document ID (must be ingested first)
            
        Returns:
            Dict with metadata, detection path, and reasoning
        """
        try:
            if doc_id not in self.ingested_docs:
                return {
                    "success": False,
                    "error": f"Document {doc_id} not ingested. Please ingest PDF first.",
                }
            
            doc_data = self.ingested_docs[doc_id]
            filename = doc_data.get("filename", "unknown.pdf")
            raw_text = doc_data.get("raw_text", "")
            chunks = doc_data.get("chunks", [])
            
            logger.info(f"=== METADATA EXTRACTION START for {doc_id} ===")
            logger.info(f"Filename: {filename}")
            logger.info(f"Raw text (first 400 chars): {raw_text[:400]}")
            
            # ===== STAGE 1: HEURISTIC EXTRACTION =====
            logger.info("--- Stage 1: Heuristic extraction ---")
            h_year, h_gp, h_session, h_summary = extract_metadata_heuristic(filename, raw_text)
            logger.info(f"Heuristic result: year={h_year}, gp={h_gp}, session={h_session}")
            logger.info(f"Heuristic summary: {h_summary}")
            
            # Check if heuristic result is high-confidence
            heuristic_confident = (h_year is not None and h_gp is not None and h_gp != "Unknown")
            
            if heuristic_confident:
                logger.info("✓ Heuristic extraction successful - using Stage 1 result")
                return {
                    "success": True,
                    "year": h_year,
                    "gp_name": h_gp,
                    "session_type": h_session or "RACE",
                    "message": f"Detected: {h_year} {h_gp} ({h_session or 'RACE'})",
                    "extraction_path": "heuristic_filename_text",
                    "reasoning": h_summary,
                }
            
            # ===== STAGE 2: LLM EXTRACTION =====
            logger.info("--- Stage 2: LLM extraction (heuristic not confident) ---")
            
            # Get first few chunks for LLM
            excerpt_parts = []
            for chunk in chunks[:10]:
                if isinstance(chunk, dict):
                    content = chunk.get("content", "")
                else:
                    content = getattr(chunk, "content", "")
                if content:
                    excerpt_parts.append(content)
            
            doc_excerpt = "\n".join(excerpt_parts)
            
            if not doc_excerpt.strip():
                logger.warning(f"No text content in chunks for {doc_id}, using heuristic fallback")
                # Fall back to heuristic even if not confident
                return {
                    "success": True,
                    "year": h_year or 2024,
                    "gp_name": h_gp or "Unknown",
                    "session_type": h_session or "RACE",
                    "message": f"Detected: {h_year or 2024} {h_gp or 'Unknown'} ({h_session or 'RACE'})",
                    "extraction_path": "heuristic_no_chunks",
                    "reasoning": "No text content in chunks; using heuristic result",
                }
            
            # Build LLM prompt
            extraction_prompt = f"""Extract race metadata from this F1 race document. Be precise and return ONLY valid JSON.

Document excerpt:
---
{doc_excerpt[:1500]}
---

Extract these three fields:
1. year: Integer year (2014-2025). Required.
2. gp_name: Full Grand Prix name (e.g., "Australian Grand Prix", "Monaco Grand Prix"). Required - never "Unknown".
3. session_type: One of RACE, QUALIFYING, SPRINT, FP1, FP2, FP3. Default to RACE.

Return ONLY this JSON format with no markdown or extra text:
{{"year": 2025, "gp_name": "Australian Grand Prix", "session_type": "RACE"}}"""
            
            logger.info(f"LLM prompt (first 300 chars): {extraction_prompt[:300]}")
            
            # Call LLM
            metadata_json = self.llm.extract_json(extraction_prompt)
            logger.info(f"Raw LLM response (first 200 chars): {str(metadata_json)[:200]}")
            
            # Extract and validate
            llm_year = metadata_json.get("year") if metadata_json else None
            llm_gp = metadata_json.get("gp_name") if metadata_json else None
            llm_session = metadata_json.get("session_type") if metadata_json else None
            
            logger.info(f"LLM parsed: year={llm_year}, gp={llm_gp}, session={llm_session}")
            
            # Validate LLM result and check against OpenF1 availability
            year = None
            if llm_year:
                try:
                    year = int(llm_year)
                    if year < 1950 or year > datetime.now().year + 1:
                        logger.warning(f"LLM year {year} out of valid range, falling back to heuristic")
                        year = None
                    else:
                        # Check if this year exists in OpenF1 database
                        try:
                            logger.info(f"Validating year {year} against OpenF1 database...")
                            test_sessions = self.openf1_client.search_sessions(year=year)
                            if not test_sessions:
                                logger.warning(f"Year {year} has no sessions in OpenF1. Trying fallback years...")
                                # Try previous years
                                for fallback_year in [year - 1, year - 2, 2024, 2023]:
                                    fb_sessions = self.openf1_client.search_sessions(year=fallback_year)
                                    if fb_sessions:
                                        logger.warning(f"Found data in year {fallback_year} instead of {year}")
                                        year = fallback_year
                                        break
                                else:
                                    logger.warning(f"Could not find any year with F1 data")
                                    year = None
                            else:
                                logger.info(f"Year {year} validated - found {len(test_sessions)} sessions")
                        except Exception as e:
                            logger.debug(f"Could not validate year against OpenF1: {e}. Continuing with year {year}")
                except (ValueError, TypeError):
                    logger.warning(f"LLM year '{llm_year}' not an integer, falling back to heuristic")
                    year = None
            
            gp_name = None
            if llm_gp:
                gp_name_str = str(llm_gp).strip()
                # Reject "Unknown" from LLM
                if gp_name_str.lower() == "unknown":
                    logger.warning(f"LLM returned 'Unknown' GP, falling back to heuristic")
                    gp_name = None
                else:
                    # Try to normalize it
                    normalized = normalize_gp_name(gp_name_str)
                    if normalized:
                        gp_name = normalized
                    elif len(gp_name_str) > 2:
                        # Accept if it looks reasonable (not "x" or "XY")
                        gp_name = gp_name_str
            
            session_type = None
            if llm_session:
                session_type_str = str(llm_session).upper().strip()
                valid_sessions = ["RACE", "QUALIFYING", "SPRINT", "FP1", "FP2", "FP3"]
                if session_type_str in valid_sessions:
                    session_type = session_type_str
            
            # Use LLM result if valid, otherwise fall back to heuristic
            llm_valid = (year is not None and gp_name is not None)
            
            if llm_valid:
                logger.info(f"✓ LLM extraction successful: {year} {gp_name}")
                return {
                    "success": True,
                    "year": year,
                    "gp_name": gp_name,
                    "session_type": session_type or "RACE",
                    "message": f"Detected: {year} {gp_name} ({session_type or 'RACE'})",
                    "extraction_path": "llm_extraction",
                    "reasoning": f"Extracted via Ollama LLM",
                }
            else:
                logger.warning(f"LLM result invalid, falling back to heuristic")
                
                # Use heuristic even if not fully confident
                final_year = h_year or 2024
                final_gp = h_gp or "Unknown"
                final_session = h_session or "RACE"
                
                error_reason = ""
                if h_year is None and llm_year is None:
                    error_reason += "Could not extract year from document or LLM. "
                if h_gp is None and llm_gp is None:
                    error_reason += "Could not extract GP name from document or LLM. "
                
                logger.warning(f"Metadata extraction partial. {error_reason.strip()}")
                
                return {
                    "success": True,  # Partial success - using defaults
                    "year": final_year,
                    "gp_name": final_gp,
                    "session_type": final_session,
                    "message": f"Detected: {final_year} {final_gp} ({final_session})",
                    "extraction_path": "heuristic_fallback_after_llm",
                    "reasoning": f"LLM failed; using heuristic fallback. {error_reason.strip()}",
                    "warning": "Low confidence detection - manual verification recommended",
                }
        
        except Exception as e:
            logger.error(f"Metadata extraction exception: {str(e)}")
            logger.debug(f"Full exception: {e}", exc_info=True)
            
            # Fallback to 2024 + Unknown
            logger.info(f"Using hardcoded fallback metadata due to exception")
            return {
                "success": False,
                "year": 2024,
                "gp_name": "Unknown",
                "session_type": "RACE",
                "message": "Detected: 2024 Unknown (RACE) [extraction failed]",
                "extraction_path": "exception_fallback",
                "reasoning": f"Exception during extraction: {str(e)}",
                "error": f"Metadata extraction failed: {str(e)}",
            }

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
        auto_extract_metadata: bool = True,
    ) -> Dict[str, Any]:
        """Build race timeline from PDF + OpenF1 data.
        
        Combines events extracted from PDF (via LLM + RAG citations) with
        structured OpenF1 data (race control, pit stops, stints).
        
        Args:
            doc_id: Document ID
            year: F1 season year (optional, auto-extracted if not provided)
            gp_name: Grand Prix name (optional, auto-extracted if not provided)
            session_type: Session type (RACE, QUALI, FP1, FP2, FP3)
            auto_extract_metadata: If True and year/gp_name not provided, extract from PDF
            
        Returns:
            Dict with success status and timeline data
        """
        try:
            # Auto-extract metadata if not provided
            if auto_extract_metadata and (not year or not gp_name):
                metadata_result = self.extract_race_metadata(doc_id)
                if not metadata_result.get("success"):
                    return {
                        "success": False,
                        "error": metadata_result.get("error", "Failed to extract metadata"),
                        "timeline": None,
                    }
                
                # Use extracted values, but allow provided values to override
                if not year:
                    year = metadata_result["year"]
                if not gp_name:
                    gp_name = metadata_result["gp_name"]
                # Note: session_type from metadata overrides default only if it was extracted
                if metadata_result.get("session_type") and session_type == "RACE":
                    session_type = metadata_result["session_type"]
            
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
                "metadata": session_metadata,
                "openf1_client_type": self.openf1_client_type,
                "debug_info": race_timeline.debug_info,  # Include debug info from timeline
            }
        
        except Exception as e:
            logger.error(f"Failed to build timeline: {e}")
            return {
                "success": False,
                "error": str(e),
                "timeline": None,
                "openf1_client_type": self.openf1_client_type if hasattr(self, 'openf1_client_type') else "unknown",
            }