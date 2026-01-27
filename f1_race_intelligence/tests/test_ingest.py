"""Tests for PDF ingestion and chunking."""

import tempfile
from pathlib import Path
import pytest

from rag.ingest import (
    extract_text_from_pdf,
    clean_text,
    semantic_chunk,
    ingest_pdf,
    IngestConfig,
    create_sample_pdf_text,
)
from rag.schemas import Chunk


class TestTextCleaning:
    """Test text cleaning functionality."""

    def test_clean_text_removes_extra_whitespace(self):
        """Test that extra whitespace is normalized."""
        text = "Hello    world  \n\n  test"
        cleaned = clean_text(text)
        assert "    " not in cleaned
        assert "\n\n\n" not in cleaned

    def test_clean_text_preserves_content(self):
        """Test that important content is preserved."""
        text = "Driver Max Verstappen won the race."
        cleaned = clean_text(text)
        assert "Max Verstappen" in cleaned
        assert "race" in cleaned

    def test_clean_text_removes_page_markers(self):
        """Test that page markers are processed."""
        text = "Content\nPage 1 of 5\nMore content"
        cleaned = clean_text(text)
        assert "Page 1 of 5" not in cleaned
        assert "Content" in cleaned


class TestSemanticChunking:
    """Test semantic chunking."""

    def test_chunk_respects_size_limit(self):
        """Test that chunks respect the size limit."""
        text = "sentence. " * 100  # Long text
        chunks = semantic_chunk(text, chunk_size=200, chunk_overlap=50)
        
        for chunk in chunks:
            # Allow some flexibility for sentence boundaries
            assert len(chunk) <= 300

    def test_chunk_preserves_content(self):
        """Test that all content is preserved."""
        text = "Hello world. This is test. More content here."
        chunks = semantic_chunk(text, chunk_size=20, chunk_overlap=5)
        
        combined = " ".join(chunks)
        assert "Hello" in combined
        assert "world" in combined

    def test_chunk_overlap(self):
        """Test that overlaps are created."""
        text = "A. B. C. D. E. F. G."
        chunks = semantic_chunk(text, chunk_size=10, chunk_overlap=5)
        
        assert len(chunks) > 1
        # Check for overlap
        first_chunk = chunks[0]
        if len(chunks) > 1:
            second_chunk = chunks[1]
            # Some content should be repeated
            overlap = set(first_chunk.split()) & set(second_chunk.split())
            assert len(overlap) > 0


class TestIngestion:
    """Test PDF ingestion."""

    def test_ingest_creates_chunks(self):
        """Test that ingestion creates chunks."""
        # Create a test text
        text = create_sample_pdf_text()
        
        # For this test, we'll just test chunking since we don't have a real PDF
        config = IngestConfig(chunk_size=512, chunk_overlap=128)
        from rag.ingest import semantic_chunk, clean_text
        
        cleaned = clean_text(text)
        chunks = semantic_chunk(cleaned, chunk_size=config.chunk_size, chunk_overlap=config.chunk_overlap)
        
        assert len(chunks) > 0

    def test_chunk_has_required_fields(self):
        """Test that chunks have all required fields."""
        text = "Test content."
        chunks = semantic_chunk(text)
        
        for chunk in chunks:
            assert isinstance(chunk, str)
            assert len(chunk) > 0


class TestSampleDocument:
    """Test sample document generation."""

    def test_sample_document_contains_race_info(self):
        """Test that sample document has race information."""
        doc = create_sample_pdf_text()
        
        assert "Monaco" in doc or "GRAND PRIX" in doc
        assert "Driver" in doc or "driver" in doc
        assert "pit" in doc.lower() or "tire" in doc.lower() or "tyre" in doc.lower()

    def test_sample_document_is_substantial(self):
        """Test that sample document is not empty."""
        doc = create_sample_pdf_text()
        assert len(doc) > 500
