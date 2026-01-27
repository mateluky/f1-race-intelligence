"""MCP Server exposing F1 race intelligence tools via FastAPI."""

import logging
import os
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import tempfile

from rag.ingest import ingest_pdf, IngestConfig
from rag.embed import get_embedder
from rag.store import get_vector_store
from rag.retrieve import Retriever
from rag.llm import get_llm
from rag.agent import RaceAgent
from openf1.api import get_openf1_client

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="F1 Race Intelligence MCP Server",
    description="Agentic RAG system with MCP for Formula 1 race analysis",
    version="0.1.0"
)

# Configuration
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")
LLM_MODE = os.getenv("LLM_MODE", "mock")
OPENF1_MODE = os.getenv("OPENF1_MODE", "mock")

# Initialize components
embedder = get_embedder(mode="sentence-transformers")
vector_store = get_vector_store(mode="chroma", db_path=CHROMA_DB_PATH)
retriever = Retriever(embedder, vector_store, top_k=5)

llm = get_llm(mode=LLM_MODE)
openf1_client = get_openf1_client(mode=OPENF1_MODE)

agent = RaceAgent(llm, retriever, openf1_client)

# In-memory document registry
documents_registry = {}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "F1 Race Intelligence MCP Server",
        "mode": {
            "llm": LLM_MODE,
            "openf1": OPENF1_MODE,
            "embedder": "sentence-transformers",
            "vector_store": "chroma",
        }
    }


@app.post("/pdf_ingest")
async def pdf_ingest(file: UploadFile = File(...)) -> JSONResponse:
    """Ingest a PDF document.
    
    Args:
        file: PDF file to ingest
        
    Returns:
        Document metadata and chunk information
    """
    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        
        # Ingest PDF
        doc_id, chunks, metadata = ingest_pdf(tmp_path)
        
        # Embed chunks
        chunk_texts = [chunk.content for chunk in chunks]
        embeddings = embedder.embed_texts(chunk_texts)
        
        # Add to vector store
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding
        vector_store.add_chunks(chunks, embeddings)
        
        # Store in registry
        documents_registry[doc_id] = {
            "metadata": metadata,
            "chunks": chunks,
            "raw_text": "\n\n".join([c.content for c in chunks]),
        }
        
        # Clean up temp file
        os.unlink(tmp_path)
        
        logger.info(f"Ingested PDF: {doc_id}, {len(chunks)} chunks")
        
        return JSONResponse({
            "doc_id": doc_id,
            "filename": metadata.filename,
            "chunk_count": metadata.chunk_count,
            "size_bytes": metadata.size_bytes,
            "uploaded_at": metadata.uploaded_at.isoformat(),
        })
    
    except Exception as e:
        logger.error(f"Error ingesting PDF: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/rag_query")
async def rag_query(doc_id: str, query: str) -> JSONResponse:
    """Query a document using RAG.
    
    Args:
        doc_id: Document ID
        query: Query string
        
    Returns:
        Retrieved chunks and answer
    """
    try:
        if doc_id not in documents_registry:
            raise ValueError(f"Document not found: {doc_id}")
        
        # Retrieve relevant chunks
        result = retriever.retrieve(query, document_id=doc_id, top_k=5)
        
        # Format context
        context = "\n\n---\n\n".join([
            f"[Chunk {i}, Score: {score:.3f}]\n{chunk.content}"
            for i, (chunk, score) in enumerate(zip(result.chunks, result.scores))
        ])
        
        logger.info(f"RAG query on {doc_id}: retrieved {len(result.chunks)} chunks")
        
        return JSONResponse({
            "query": query,
            "doc_id": doc_id,
            "chunk_count": len(result.chunks),
            "chunks": [
                {
                    "id": chunk.id,
                    "content": chunk.content[:500] + "..." if len(chunk.content) > 500 else chunk.content,
                    "score": score,
                }
                for chunk, score in zip(result.chunks, result.scores)
            ],
            "context": context[:2000],
        })
    
    except Exception as e:
        logger.error(f"Error in RAG query: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/extract_claims")
async def extract_claims(doc_id: str) -> JSONResponse:
    """Extract claims from a document.
    
    Args:
        doc_id: Document ID
        
    Returns:
        JSON list of claims with entities and evidence types
    """
    try:
        if doc_id not in documents_registry:
            raise ValueError(f"Document not found: {doc_id}")
        
        raw_text = documents_registry[doc_id]["raw_text"]
        
        claims = agent.claim_extractor.extract_claims(raw_text, max_claims=10)
        
        logger.info(f"Extracted {len(claims)} claims from {doc_id}")
        
        return JSONResponse({
            "doc_id": doc_id,
            "claim_count": len(claims),
            "claims": [
                {
                    "id": claim.id,
                    "text": claim.claim_text,
                    "type": claim.claim_type.value,
                    "confidence": claim.confidence,
                    "entities": {
                        "drivers": claim.entities.drivers,
                        "teams": claim.entities.teams,
                    },
                    "rationale": claim.rationale,
                }
                for claim in claims
            ]
        })
    
    except Exception as e:
        logger.error(f"Error extracting claims: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/openf1_search_session")
async def openf1_search_session(
    year: int,
    gp_name: str,
    session_type: Optional[str] = "RACE",
) -> JSONResponse:
    """Search for an F1 session on OpenF1.
    
    Args:
        year: Race year
        gp_name: Grand Prix name
        session_type: Session type (RACE, QUALI, FP1, etc.)
        
    Returns:
        Session identifiers and metadata
    """
    try:
        sessions = openf1_client.search_sessions(
            year=year,
            gp_name=gp_name,
            session_type=session_type,
        )
        
        logger.info(f"Found {len(sessions)} sessions for {year} {gp_name}")
        
        return JSONResponse({
            "year": year,
            "gp_name": gp_name,
            "session_type": session_type,
            "session_count": len(sessions),
            "sessions": sessions[:5],  # Return top 5
        })
    
    except Exception as e:
        logger.error(f"Error searching sessions: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/openf1_get_race_control")
async def openf1_get_race_control(session_id: str) -> JSONResponse:
    """Get race control messages for a session.
    
    Args:
        session_id: OpenF1 session ID
        
    Returns:
        Race control messages
    """
    try:
        messages = openf1_client.get_race_control_messages(session_id)
        
        logger.info(f"Retrieved {len(messages)} race control messages")
        
        return JSONResponse({
            "session_id": session_id,
            "message_count": len(messages),
            "messages": messages[:20],  # Top 20
        })
    
    except Exception as e:
        logger.error(f"Error getting race control: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/openf1_get_laps")
async def openf1_get_laps(session_id: str, driver_number: Optional[int] = None) -> JSONResponse:
    """Get lap times for a session.
    
    Args:
        session_id: OpenF1 session ID
        driver_number: Optional driver number filter
        
    Returns:
        Lap data
    """
    try:
        laps = openf1_client.get_laps(session_id, driver_number=driver_number)
        
        logger.info(f"Retrieved {len(laps)} laps")
        
        return JSONResponse({
            "session_id": session_id,
            "driver_number": driver_number,
            "lap_count": len(laps),
            "laps": laps[:30],  # Top 30
        })
    
    except Exception as e:
        logger.error(f"Error getting laps: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/openf1_get_stints")
async def openf1_get_stints(session_id: str, driver_number: Optional[int] = None) -> JSONResponse:
    """Get stint/tire data for a session.
    
    Args:
        session_id: OpenF1 session ID
        driver_number: Optional driver number filter
        
    Returns:
        Stint data
    """
    try:
        stints = openf1_client.get_stints(session_id, driver_number=driver_number)
        
        logger.info(f"Retrieved {len(stints)} stints")
        
        return JSONResponse({
            "session_id": session_id,
            "driver_number": driver_number,
            "stint_count": len(stints),
            "stints": stints,
        })
    
    except Exception as e:
        logger.error(f"Error getting stints: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/build_race_brief")
async def build_race_brief(doc_id: str) -> JSONResponse:
    """Build complete race intelligence brief.
    
    This is the main "cool" endpoint that orchestrates the entire pipeline:
    - Extract entities and session info
    - Extract claims
    - Plan OpenF1 API calls
    - Retrieve and map evidence
    - Generate summary and follow-ups
    
    Args:
        doc_id: Document ID
        
    Returns:
        Complete RaceBrief JSON
    """
    try:
        if doc_id not in documents_registry:
            raise ValueError(f"Document not found: {doc_id}")
        
        raw_text = documents_registry[doc_id]["raw_text"]
        
        # Build brief using agent
        brief = agent.build_race_brief(raw_text, doc_id)
        
        logger.info(f"Generated race brief for {doc_id}: {brief.claim_stats}")
        
        return JSONResponse({
            "id": brief.id,
            "document_id": brief.document_id,
            "generated_at": brief.generated_at.isoformat(),
            "executive_summary": brief.executive_summary,
            "key_points": brief.key_points,
            "claim_count": len(brief.extracted_claims),
            "claims": [
                {
                    "id": claim.id,
                    "text": claim.claim_text,
                    "type": claim.claim_type.value,
                    "confidence": claim.confidence,
                    "status": claim.status.value,
                    "evidence_count": len(claim.evidence),
                }
                for claim in brief.extracted_claims
            ],
            "timeline_events": len(brief.timeline),
            "follow_up_questions": brief.follow_up_questions,
            "session_info": brief.session_info,
            "claim_stats": brief.claim_stats,
        })
    
    except Exception as e:
        logger.error(f"Error building race brief: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/documents")
async def list_documents() -> JSONResponse:
    """List all ingested documents."""
    return JSONResponse({
        "document_count": len(documents_registry),
        "documents": [
            {
                "doc_id": doc_id,
                "filename": data["metadata"].filename,
                "chunk_count": data["metadata"].chunk_count,
                "uploaded_at": data["metadata"].uploaded_at.isoformat(),
            }
            for doc_id, data in documents_registry.items()
        ]
    })


@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str) -> JSONResponse:
    """Delete a document and its chunks.
    
    Args:
        doc_id: Document ID
        
    Returns:
        Confirmation
    """
    try:
        if doc_id not in documents_registry:
            raise ValueError(f"Document not found: {doc_id}")
        
        # Delete from vector store
        vector_store.delete_document(doc_id)
        
        # Delete from registry
        del documents_registry[doc_id]
        
        logger.info(f"Deleted document {doc_id}")
        
        return JSONResponse({
            "status": "deleted",
            "doc_id": doc_id,
        })
    
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", 8000))
    
    logger.info(f"Starting server on {host}:{port}")
    logger.info(f"Modes: LLM={LLM_MODE}, OpenF1={OPENF1_MODE}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )
