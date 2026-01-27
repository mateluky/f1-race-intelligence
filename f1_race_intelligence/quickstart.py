"""Quick-start script demonstrating the F1 Race Intelligence System without API dependencies."""

import json
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Import all components
from rag.ingest import create_sample_pdf_text, semantic_chunk, clean_text, IngestConfig
from rag.embed import get_embedder
from rag.store import get_vector_store
from rag.retrieve import Retriever
from rag.llm import get_llm
from rag.agent import RaceAgent
from openf1.api import get_openf1_client


def main():
    """Run a complete demo without needing a server."""
    
    print("\n" + "="*80)
    print("F1 RACE INTELLIGENCE SYSTEM - QUICK START DEMO")
    print("="*80 + "\n")
    
    # Step 1: Initialize components
    print("[1] Initializing RAG components...\n")
    
    embedder = get_embedder(mode="mock")  # Mock embedder for demo
    vector_store = get_vector_store(mode="memory")  # In-memory store
    retriever = Retriever(embedder, vector_store, top_k=5)
    llm = get_llm(mode="mock")  # Mock LLM for demo
    openf1_client = get_openf1_client(mode="mock")  # Mock F1 client
    
    logger.info("Initialized all components")
    
    # Step 2: Create sample document
    print("[2] Loading sample F1 race document...\n")
    
    sample_text = create_sample_pdf_text()
    logger.info(f"Loaded sample document ({len(sample_text)} chars)")
    
    # Step 3: Ingest and chunk
    print("[3] Ingesting and chunking document...\n")
    
    config = IngestConfig(chunk_size=512, chunk_overlap=128)
    cleaned_text = clean_text(sample_text)
    chunks = semantic_chunk(cleaned_text, chunk_size=config.chunk_size, chunk_overlap=config.chunk_overlap)
    
    logger.info(f"Created {len(chunks)} chunks")
    
    # Create chunk objects and embed
    from rag.schemas import Chunk
    import uuid
    
    chunk_objects = []
    for idx, chunk_text in enumerate(chunks):
        chunk_obj = Chunk(
            id=f"demo_chunk_{idx}",
            document_id="demo_doc",
            content=chunk_text,
            chunk_index=idx,
        )
        chunk_objects.append(chunk_obj)
    
    # Embed chunks
    embeddings = embedder.embed_texts([c.content for c in chunk_objects])
    vector_store.add_chunks(chunk_objects, embeddings)
    
    logger.info("Chunks embedded and stored")
    
    # Step 4: Initialize agent
    print("[4] Initializing Race Agent...\n")
    
    agent = RaceAgent(llm, retriever, openf1_client)
    logger.info("Agent initialized")
    
    # Step 5: Test RAG retrieval
    print("[5] Testing semantic search...\n")
    
    test_queries = [
        "Pit stop strategy",
        "Driver pace comparison",
        "Tire compound strategy",
    ]
    
    for query in test_queries:
        result = retriever.retrieve(query, document_id="demo_doc", top_k=3)
        print(f"Query: '{query}'")
        print(f"  → Found {len(result.chunks)} relevant chunks")
        if result.chunks:
            print(f"     Top result (score={result.scores[0]:.3f}): {result.chunks[0].content[:80]}...\n")
    
    # Step 6: Extract entities and claims
    print("[6] Extracting entities and claims...\n")
    
    session_info = agent.entity_extractor.extract_session_info(sample_text)
    entities = agent.entity_extractor.extract_entities(sample_text)
    
    if session_info:
        print(f"Session: {session_info.year} {session_info.gp_name} ({session_info.session_type})")
    print(f"Teams found: {', '.join(entities.teams)}")
    print()
    
    claims = agent.claim_extractor.extract_claims(sample_text, max_claims=5)
    logger.info(f"Extracted {len(claims)} claims")
    
    print(f"Claims extracted: {len(claims)}")
    for i, claim in enumerate(claims[:3], 1):
        print(f"  {i}. {claim.claim_text}")
        print(f"     Type: {claim.claim_type.value} | Confidence: {claim.confidence:.2f}")
    print()
    
    # Step 7: Build race brief (main agent orchestration)
    print("[7] Building Race Intelligence Brief...\n")
    
    brief = agent.build_race_brief(sample_text, "demo_doc")
    
    logger.info(f"Generated brief: {brief.claim_stats}")
    
    # Step 8: Display results
    print("[8] Race Intelligence Brief\n")
    print("-" * 80)
    print(f"EXECUTIVE SUMMARY\n{brief.executive_summary}\n")
    
    print(f"KEY CLAIMS ({len(brief.extracted_claims)} total):\n")
    for i, claim in enumerate(brief.extracted_claims[:5], 1):
        status_icon = "✓" if claim.status.value == "supported" else "?" if claim.status.value == "unclear" else "✗"
        print(f"{i}. [{status_icon}] {claim.claim_text}")
        print(f"   Confidence: {claim.confidence:.2f} | Type: {claim.claim_type.value}")
    
    if brief.timeline:
        print(f"\nKEY TIMELINE EVENTS ({len(brief.timeline)} events):\n")
        for event in brief.timeline[:5]:
            print(f"- Lap {event.lap}: {event.event}")
    
    if brief.follow_up_questions:
        print(f"\nFOLLOW-UP QUESTIONS:\n")
        for i, q in enumerate(brief.follow_up_questions[:3], 1):
            print(f"{i}. {q}")
    
    print(f"\nCLAIM STATISTICS:")
    print(f"  Total: {brief.claim_stats.get('total', 0)}")
    print(f"  Supported: {brief.claim_stats.get('supported', 0)}")
    print(f"  Unclear: {brief.claim_stats.get('unclear', 0)}")
    print(f"  Contradicted: {brief.claim_stats.get('contradicted', 0)}")
    
    # Step 9: Save outputs
    print("\n[9] Saving outputs...\n")
    
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    
    # Save JSON brief
    brief_json = brief.model_dump(mode="python")
    json_path = output_dir / "race_brief.json"
    with open(json_path, "w") as f:
        json.dump(brief_json, f, indent=2, default=str)
    logger.info(f"Saved brief to {json_path}")
    
    # Save markdown report
    md_path = output_dir / "race_brief.md"
    with open(md_path, "w") as f:
        f.write(f"# F1 Race Intelligence Brief\n\n")
        f.write(f"**Generated:** {brief.generated_at.isoformat()}\n\n")
        
        f.write("## Executive Summary\n\n")
        f.write(f"{brief.executive_summary}\n\n")
        
        f.write("## Key Claims\n\n")
        for i, claim in enumerate(brief.extracted_claims[:10], 1):
            f.write(f"{i}. **{claim.claim_text}**\n")
            f.write(f"   - Type: {claim.claim_type.value}\n")
            f.write(f"   - Confidence: {claim.confidence:.2f}\n")
            f.write(f"   - Status: {claim.status.value}\n")
            f.write(f"   - Evidence: {len(claim.evidence)} items\n\n")
        
        if brief.follow_up_questions:
            f.write("## Follow-up Questions\n\n")
            for i, q in enumerate(brief.follow_up_questions, 1):
                f.write(f"{i}. {q}\n")
        
        f.write("\n## Statistics\n\n")
        f.write(f"- **Total Claims:** {brief.claim_stats.get('total', 0)}\n")
        f.write(f"- **Supported:** {brief.claim_stats.get('supported', 0)}\n")
        f.write(f"- **Unclear:** {brief.claim_stats.get('unclear', 0)}\n")
        f.write(f"- **Contradicted:** {brief.claim_stats.get('contradicted', 0)}\n")
    
    logger.info(f"Saved markdown to {md_path}")
    
    print("="*80)
    print(f"✓ Demo complete! Outputs saved to '{output_dir}/'")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
