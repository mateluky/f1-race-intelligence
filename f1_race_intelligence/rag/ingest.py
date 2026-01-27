"""PDF ingestion, parsing, cleaning, and chunking."""

import logging
import re
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

from rag.schemas import Chunk, DocumentMetadata

logger = logging.getLogger(__name__)


class IngestConfig(BaseModel):
    """Configuration for PDF ingestion."""
    chunk_size: int = 512
    chunk_overlap: int = 128
    min_chunk_length: int = 50
    max_chunk_length: int = 2000


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Extracted text content
        
    Raises:
        FileNotFoundError: If PDF doesn't exist
        ValueError: If PDF cannot be parsed
    """
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    if PdfReader is None:
        raise ImportError("pypdf not installed. Install with: pip install pypdf")
    
    try:
        pdf = PdfReader(pdf_path)
        text = ""
        for page_num, page in enumerate(pdf.pages):
            page_text = page.extract_text()
            if page_text:
                # Add page marker for tracking
                text += f"\n[PAGE {page_num + 1}]\n{page_text}\n"
        
        if not text.strip():
            raise ValueError("No text could be extracted from PDF")
        
        logger.info(f"Extracted {len(text)} characters from {len(pdf.pages)} pages")
        return text
    except Exception as e:
        logger.error(f"Error parsing PDF {pdf_path}: {e}")
        raise


def clean_text(text: str) -> str:
    """Clean extracted text.
    
    Args:
        text: Raw text from PDF
        
    Returns:
        Cleaned text
    """
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove common header/footer patterns
    text = re.sub(r'Page \d+ of \d+', '', text)
    text = re.sub(r'www\.\S+', '', text)
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '', text)
    
    # Keep page markers but clean them
    text = re.sub(r'\[PAGE (\d+)\]', r'[PAGE_\1]', text)
    
    # Remove control characters
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\t')
    
    # Normalize whitespace
    text = '\n'.join(line.strip() for line in text.split('\n'))
    text = '\n\n'.join(para.strip() for para in text.split('\n\n') if para.strip())
    
    return text


def semantic_chunk(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 128,
) -> List[str]:
    """Split text into semantic chunks.
    
    Attempts to respect sentence boundaries for better semantic coherence.
    
    Args:
        text: Text to chunk
        chunk_size: Target chunk size in characters
        chunk_overlap: Overlap between chunks in characters
        
    Returns:
        List of text chunks
    """
    # Split on sentences first
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        # Add sentence to current chunk if it fits
        if len(current_chunk) + len(sentence) <= chunk_size:
            current_chunk += " " + sentence if current_chunk else sentence
        else:
            # Current chunk is full
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            
            # Handle very long sentences by splitting on newlines
            if len(sentence) > chunk_size:
                parts = sentence.split('\n')
                for part in parts:
                    if len(part) > chunk_size:
                        # Force split on spaces
                        words = part.split()
                        temp_chunk = ""
                        for word in words:
                            if len(temp_chunk) + len(word) <= chunk_size:
                                temp_chunk += " " + word if temp_chunk else word
                            else:
                                if temp_chunk:
                                    chunks.append(temp_chunk.strip())
                                temp_chunk = word
                        if temp_chunk:
                            chunks.append(temp_chunk.strip())
                    else:
                        chunks.append(part.strip())
            else:
                current_chunk = sentence
    
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    # Add overlap by merging adjacent chunks partially
    if chunk_overlap > 0:
        overlapped_chunks = []
        for i, chunk in enumerate(chunks):
            if i > 0:
                # Add overlap from previous chunk
                prev_chunk = chunks[i - 1]
                overlap_text = prev_chunk[-chunk_overlap:] if len(prev_chunk) > chunk_overlap else prev_chunk
                chunk = overlap_text + " " + chunk
            overlapped_chunks.append(chunk)
        chunks = overlapped_chunks
    
    return [c.strip() for c in chunks if len(c.strip()) > 50]


def ingest_pdf(
    pdf_path: str,
    config: Optional[IngestConfig] = None,
) -> tuple[str, List[Chunk], DocumentMetadata]:
    """Ingest and process a PDF file.
    
    Args:
        pdf_path: Path to PDF file
        config: Ingestion configuration
        
    Returns:
        Tuple of (document_id, chunks, metadata)
    """
    if config is None:
        config = IngestConfig()
    
    logger.info(f"Starting PDF ingestion: {pdf_path}")
    
    # Extract text
    raw_text = extract_text_from_pdf(pdf_path)
    
    # Clean text
    clean_text_content = clean_text(raw_text)
    
    # Chunk text
    text_chunks = semantic_chunk(
        clean_text_content,
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
    )
    
    # Create document and chunks
    doc_id = str(uuid.uuid4())
    chunks = []
    
    for idx, chunk_text in enumerate(text_chunks):
        chunk = Chunk(
            id=f"{doc_id}_chunk_{idx}",
            document_id=doc_id,
            content=chunk_text,
            chunk_index=idx,
            metadata={
                "original_length": len(raw_text),
                "chunk_count": len(text_chunks),
            }
        )
        chunks.append(chunk)
    
    # Create metadata
    metadata = DocumentMetadata(
        id=doc_id,
        filename=Path(pdf_path).name,
        chunk_count=len(chunks),
        size_bytes=len(raw_text),
    )
    
    logger.info(f"Successfully ingested PDF: {len(chunks)} chunks, {len(clean_text_content)} chars")
    
    return doc_id, chunks, metadata


def batch_ingest_pdfs(
    pdf_paths: List[str],
    config: Optional[IngestConfig] = None,
) -> List[tuple[str, List[Chunk], DocumentMetadata]]:
    """Ingest multiple PDF files.
    
    Args:
        pdf_paths: List of PDF file paths
        config: Ingestion configuration
        
    Returns:
        List of (document_id, chunks, metadata) tuples
    """
    results = []
    for pdf_path in pdf_paths:
        try:
            result = ingest_pdf(pdf_path, config)
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to ingest {pdf_path}: {e}")
    
    return results


# For testing/example: create a sample F1 document
SAMPLE_F1_DOCUMENT = """
FORMULA 1 RACE REPORT - MONACO GRAND PRIX 2023

SESSION: RACE (Main Event)
DATE: May 28, 2023
LOCATION: Circuit de Monaco, Monte-Carlo, Monaco
DRIVERS: Multiple competitors from 10 teams

EXECUTIVE SUMMARY
The Monaco Grand Prix was a competitive race with strategic pit stop decisions playing a crucial role. 
Driver Max Verstappen demonstrated strong pace throughout most of the race, maintaining consistent 
lap times particularly in Sector 2 where he showed significant advantage over competitors.

RACE ANALYSIS
Lap 1-15: Initial phase saw Verstappen and Hamilton battling for position. Verstappen's superior pace 
in the first corner sequence gave him an early advantage. Tire temperatures built up gradually as drivers 
pushed for position.

Lap 16-35: Pit stop window opened. Strategic calls were made by different teams. Red Bull pitted 
Verstappen on lap 22 with soft tires, gaining track position. Mercedes followed with Hamilton on lap 24 
with hard compound tires.

Lap 36-58: Post-pit stop phase showed clear tire degradation patterns. Verstappen maintained consistent 
pace while Hamilton struggled with tire management in the latter stages. The weather remained dry 
throughout, with track temperature reaching optimal levels.

KEY INCIDENTS
- Lap 18: Minor contact between drivers at Portier corner (Turn 6), minor damage but no safety car
- Lap 45: Another driver spun at the hairpin but recovered without damage

TIRE STRATEGY ANALYSIS
- Soft tires: Used in first stint by most drivers, showing high degradation after 18-20 laps
- Hard tires: Better in second stint, lasted until race end with manageable deg
- Medium tires: Not used due to strategic considerations

PIT STOP DATA
- Fastest pit stop: 2.3 seconds
- Average pit stop: 2.8 seconds
- Total pit stops: 45 (some drivers two stops, others one stop)

DRIVER PERFORMANCES
- Verstappen: Dominant pace, especially strong in Sectors 2 and 3
- Hamilton: Competitive but struggled with tire deg in final laps
- Leclerc: Home race considerations, pace variable across stint

WEATHER CONDITIONS
- Temperature: 22°C ambient, track temp ~28°C
- Wind: Light to moderate from northwest
- Visibility: Excellent throughout the race

RACE CONCLUSION
Verstappen won with dominant pace and strategic execution. The race was decided by pit stop timing 
and tire management rather than pure driver skill, though all drivers performed at high levels. 
Monaco's unique characteristics (limited overtaking, tight corners) meant first lap position and 
pit stop strategy were paramount.
"""

def create_sample_pdf_text() -> str:
    """Create sample F1 document text for testing."""
    return SAMPLE_F1_DOCUMENT
