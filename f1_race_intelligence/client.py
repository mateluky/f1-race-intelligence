"""Example MCP client demonstrating end-to-end F1 race intelligence workflow."""

import json
import logging
import argparse
import sys
from pathlib import Path
from typing import Optional
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class F1RaceIntelligenceClient:
    """Client for F1 Race Intelligence MCP Server."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """Initialize client.
        
        Args:
            base_url: Base URL of the MCP server
        """
        self.base_url = base_url
        self.session = requests.Session()
        logger.info(f"Initialized client for {base_url}")

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make a request to the server.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            **kwargs: Additional arguments for requests
            
        Returns:
            Response JSON
        """
        url = f"{self.base_url}/{endpoint}"
        
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise

    def health(self) -> dict:
        """Check server health."""
        return self._request("GET", "health")

    def ingest_pdf(self, pdf_path: str) -> str:
        """Ingest a PDF file.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Document ID
        """
        with open(pdf_path, "rb") as f:
            files = {"file": f}
            result = self._request("POST", "pdf_ingest", files=files)
        
        logger.info(f"Ingested PDF: {result['doc_id']}")
        return result["doc_id"]

    def rag_query(self, doc_id: str, query: str) -> dict:
        """Query a document using RAG.
        
        Args:
            doc_id: Document ID
            query: Query string
            
        Returns:
            Retrieved chunks and answer
        """
        return self._request("POST", "rag_query", params={"doc_id": doc_id, "query": query})

    def extract_claims(self, doc_id: str) -> dict:
        """Extract claims from a document.
        
        Args:
            doc_id: Document ID
            
        Returns:
            Claims with metadata
        """
        return self._request("POST", "extract_claims", params={"doc_id": doc_id})

    def search_session(self, year: int, gp_name: str, session_type: str = "RACE") -> dict:
        """Search for an F1 session.
        
        Args:
            year: Race year
            gp_name: Grand Prix name
            session_type: Session type
            
        Returns:
            Session information
        """
        return self._request(
            "POST",
            "openf1_search_session",
            params={"year": year, "gp_name": gp_name, "session_type": session_type},
        )

    def get_race_control(self, session_id: str) -> dict:
        """Get race control messages.
        
        Args:
            session_id: OpenF1 session ID
            
        Returns:
            Race control messages
        """
        return self._request("POST", "openf1_get_race_control", params={"session_id": session_id})

    def get_laps(self, session_id: str, driver_number: Optional[int] = None) -> dict:
        """Get lap times.
        
        Args:
            session_id: OpenF1 session ID
            driver_number: Optional driver number
            
        Returns:
            Lap data
        """
        params = {"session_id": session_id}
        if driver_number:
            params["driver_number"] = driver_number
        return self._request("POST", "openf1_get_laps", params=params)

    def get_stints(self, session_id: str, driver_number: Optional[int] = None) -> dict:
        """Get stint data.
        
        Args:
            session_id: OpenF1 session ID
            driver_number: Optional driver number
            
        Returns:
            Stint data
        """
        params = {"session_id": session_id}
        if driver_number:
            params["driver_number"] = driver_number
        return self._request("POST", "openf1_get_stints", params=params)

    def build_race_brief(self, doc_id: str) -> dict:
        """Build complete race intelligence brief.
        
        This is the main orchestration endpoint.
        
        Args:
            doc_id: Document ID
            
        Returns:
            Complete race brief
        """
        return self._request("POST", "build_race_brief", params={"doc_id": doc_id})

    def list_documents(self) -> dict:
        """List all ingested documents."""
        return self._request("GET", "documents")

    def delete_document(self, doc_id: str) -> dict:
        """Delete a document.
        
        Args:
            doc_id: Document ID
            
        Returns:
            Confirmation
        """
        return self._request("DELETE", f"documents/{doc_id}")


def print_brief_markdown(brief: dict) -> str:
    """Format brief as markdown.
    
    Args:
        brief: Brief JSON from server
        
    Returns:
        Markdown string
    """
    md = []
    
    md.append("# F1 Race Intelligence Brief\n")
    md.append(f"**Generated:** {brief.get('generated_at')}\n")
    md.append(f"**Document ID:** {brief.get('document_id')}\n\n")
    
    # Executive Summary
    md.append("## Executive Summary\n")
    md.append(brief.get('executive_summary', 'N/A') + "\n\n")
    
    # Claims
    md.append("## Key Claims\n\n")
    claims = brief.get('claims', [])
    for i, claim in enumerate(claims[:10], 1):
        md.append(f"{i}. **{claim['text']}**\n")
        md.append(f"   - Type: {claim['type']}\n")
        md.append(f"   - Confidence: {claim['confidence']:.2f}\n")
        md.append(f"   - Status: {claim['status']}\n")
        md.append(f"   - Evidence: {claim['evidence_count']} items\n\n")
    
    # Follow-ups
    md.append("## Follow-up Questions\n\n")
    for i, q in enumerate(brief.get('follow_up_questions', []), 1):
        md.append(f"{i}. {q}\n")
    
    md.append("\n## Statistics\n\n")
    stats = brief.get('claim_stats', {})
    md.append(f"- **Total Claims:** {stats.get('total', 0)}\n")
    md.append(f"- **Supported:** {stats.get('supported', 0)}\n")
    md.append(f"- **Unclear:** {stats.get('unclear', 0)}\n")
    md.append(f"- **Contradicted:** {stats.get('contradicted', 0)}\n")
    
    return "\n".join(md)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="F1 Race Intelligence Client - Analyze Formula 1 documents"
    )
    parser.add_argument(
        "--pdf",
        type=str,
        help="Path to PDF file to ingest and analyze",
    )
    parser.add_argument(
        "--server",
        type=str,
        default="http://localhost:8000",
        help="Server URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file for the brief (JSON and markdown)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: skip evidence retrieval",
    )
    parser.add_argument(
        "--doc-id",
        type=str,
        help="Use existing document ID instead of ingesting",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all ingested documents",
    )
    
    args = parser.parse_args()
    
    # Initialize client
    client = F1RaceIntelligenceClient(args.server)
    
    try:
        # Check health
        health = client.health()
        logger.info(f"Server health: {health['status']}")
        logger.info(f"Modes: LLM={health['mode']['llm']}, OpenF1={health['mode']['openf1']}")
        
    except Exception as e:
        logger.error(f"Cannot connect to server: {e}")
        sys.exit(1)
    
    # List documents
    if args.list:
        docs = client.list_documents()
        print(f"\nIngested Documents ({docs['document_count']}):\n")
        for doc in docs['documents']:
            print(f"  {doc['doc_id']}")
            print(f"    - File: {doc['filename']}")
            print(f"    - Chunks: {doc['chunk_count']}")
            print(f"    - Uploaded: {doc['uploaded_at']}\n")
        return
    
    # Get or ingest document
    if args.doc_id:
        doc_id = args.doc_id
        logger.info(f"Using document: {doc_id}")
    elif args.pdf:
        if not Path(args.pdf).exists():
            logger.error(f"PDF file not found: {args.pdf}")
            sys.exit(1)
        
        logger.info(f"Ingesting PDF: {args.pdf}")
        try:
            doc_id = client.ingest_pdf(args.pdf)
        except Exception as e:
            logger.error(f"Failed to ingest PDF: {e}")
            sys.exit(1)
    else:
        logger.error("Please provide --pdf, --doc-id, or --list")
        parser.print_help()
        sys.exit(1)
    
    # Build race brief
    logger.info("Building race intelligence brief...")
    try:
        brief = client.build_race_brief(doc_id)
    except Exception as e:
        logger.error(f"Failed to build brief: {e}")
        sys.exit(1)
    
    # Print brief
    brief_md = print_brief_markdown(brief)
    print("\n" + "=" * 80)
    print(brief_md)
    print("=" * 80 + "\n")
    
    # Save if requested
    if args.output:
        output_dir = Path(args.output).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save JSON
        json_path = Path(args.output).with_suffix(".json")
        with open(json_path, "w") as f:
            json.dump(brief, f, indent=2, default=str)
        logger.info(f"Saved brief JSON: {json_path}")
        
        # Save markdown
        md_path = Path(args.output).with_suffix(".md")
        with open(md_path, "w") as f:
            f.write(brief_md)
        logger.info(f"Saved brief markdown: {md_path}")
    
    logger.info("Done!")


if __name__ == "__main__":
    main()
