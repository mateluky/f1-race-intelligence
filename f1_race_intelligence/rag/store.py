"""Vector store interface and implementations."""

import json
import logging
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from rag.schemas import Chunk
from rag.embed import EmbedderInterface

logger = logging.getLogger(__name__)


class VectorStoreInterface(ABC):
    """Abstract interface for vector storage and retrieval."""

    @abstractmethod
    def add_chunks(self, chunks: List[Chunk], embeddings: List[List[float]]) -> None:
        """Add chunks with their embeddings to the store.
        
        Args:
            chunks: List of Chunk objects
            embeddings: List of embedding vectors (same length as chunks)
        """
        pass

    @abstractmethod
    def search(
        self,
        query_embedding: List[float],
        k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[Chunk, float]]:
        """Search for similar chunks.
        
        Args:
            query_embedding: Query embedding vector
            k: Number of results to return
            metadata_filter: Optional filter on chunk metadata
            
        Returns:
            List of (Chunk, similarity_score) tuples
        """
        pass

    @abstractmethod
    def get_chunk(self, chunk_id: str) -> Optional[Chunk]:
        """Get a specific chunk by ID.
        
        Args:
            chunk_id: Chunk ID
            
        Returns:
            Chunk object or None if not found
        """
        pass

    @abstractmethod
    def delete_document(self, document_id: str) -> None:
        """Delete all chunks for a document.
        
        Args:
            document_id: Document ID
        """
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all chunks from the store."""
        pass


class InMemoryVectorStore(VectorStoreInterface):
    """Simple in-memory vector store for testing."""

    def __init__(self):
        """Initialize in-memory store."""
        self.chunks: Dict[str, Chunk] = {}
        self.embeddings: Dict[str, List[float]] = {}
        logger.info("Initialized InMemoryVectorStore")

    def add_chunks(self, chunks: List[Chunk], embeddings: List[List[float]]) -> None:
        """Add chunks to the store."""
        if len(chunks) != len(embeddings):
            raise ValueError(f"Chunks and embeddings length mismatch: {len(chunks)} vs {len(embeddings)}")
        
        for chunk, embedding in zip(chunks, embeddings):
            self.chunks[chunk.id] = chunk
            self.embeddings[chunk.id] = embedding
        
        logger.info(f"Added {len(chunks)} chunks to store")

    def search(
        self,
        query_embedding: List[float],
        k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[Chunk, float]]:
        """Search using cosine similarity."""
        import numpy as np
        
        query_vec = np.array(query_embedding)
        results = []
        
        for chunk_id, chunk in self.chunks.items():
            # Apply metadata filter if provided
            if metadata_filter:
                if chunk.metadata.get("document_id") != metadata_filter.get("document_id"):
                    continue
            
            embedding_vec = np.array(self.embeddings[chunk_id])
            
            # Cosine similarity
            norm_query = np.linalg.norm(query_vec)
            norm_emb = np.linalg.norm(embedding_vec)
            if norm_query > 0 and norm_emb > 0:
                similarity = np.dot(query_vec, embedding_vec) / (norm_query * norm_emb)
            else:
                similarity = 0.0
            
            results.append((chunk, float(similarity)))
        
        # Sort by similarity descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:k]

    def get_chunk(self, chunk_id: str) -> Optional[Chunk]:
        """Get a specific chunk."""
        return self.chunks.get(chunk_id)

    def delete_document(self, document_id: str) -> None:
        """Delete all chunks for a document."""
        chunk_ids_to_delete = [
            cid for cid, chunk in self.chunks.items()
            if chunk.document_id == document_id
        ]
        for chunk_id in chunk_ids_to_delete:
            del self.chunks[chunk_id]
            del self.embeddings[chunk_id]
        
        logger.info(f"Deleted {len(chunk_ids_to_delete)} chunks for document {document_id}")

    def clear(self) -> None:
        """Clear all chunks."""
        self.chunks.clear()
        self.embeddings.clear()
        logger.info("Cleared all chunks from store")


class ChromaVectorStore(VectorStoreInterface):
    """Vector store using Chroma."""

    def __init__(self, db_path: str = "./chroma_db"):
        """Initialize Chroma vector store.
        
        Args:
            db_path: Path to Chroma database directory
        """
        try:
            import chromadb
            from chromadb.config import Settings
            
            # Create persistent Chroma client
            settings = Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=db_path,
                anonymized_telemetry=False,
            )
            self.client = chromadb.Client(settings)
            self.collection = self.client.get_or_create_collection(
                name="f1_race_intelligence",
                metadata={"description": "F1 race documents and chunks"}
            )
            
            # Store chunks in memory for retrieval
            self.chunks: Dict[str, Chunk] = {}
            
            logger.info(f"Initialized ChromaVectorStore at {db_path}")
        except ImportError:
            logger.error("chromadb not installed. Install with: pip install chromadb")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize ChromaVectorStore: {e}")
            raise

    def add_chunks(self, chunks: List[Chunk], embeddings: List[List[float]]) -> None:
        """Add chunks to Chroma."""
        if len(chunks) != len(embeddings):
            raise ValueError(f"Length mismatch: {len(chunks)} chunks vs {len(embeddings)} embeddings")
        
        # Add to local store
        for chunk in chunks:
            self.chunks[chunk.id] = chunk
        
        # Add to Chroma
        try:
            self.collection.add(
                ids=[chunk.id for chunk in chunks],
                embeddings=embeddings,
                documents=[chunk.content for chunk in chunks],
                metadatas=[
                    {
                        "document_id": chunk.document_id,
                        "chunk_index": chunk.chunk_index,
                        **chunk.metadata,
                    }
                    for chunk in chunks
                ]
            )
            logger.info(f"Added {len(chunks)} chunks to Chroma")
        except Exception as e:
            logger.error(f"Error adding chunks to Chroma: {e}")
            raise

    def search(
        self,
        query_embedding: List[float],
        k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[Chunk, float]]:
        """Search using Chroma."""
        try:
            where_filter = None
            if metadata_filter and "document_id" in metadata_filter:
                where_filter = {"document_id": {"$eq": metadata_filter["document_id"]}}
            
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                where=where_filter,
                include=["distances", "documents", "metadatas"]
            )
            
            # Convert distances to similarity scores (Chroma returns distances)
            chunks_with_scores = []
            if results and results["ids"] and len(results["ids"]) > 0:
                for i, chunk_id in enumerate(results["ids"][0]):
                    chunk = self.chunks.get(chunk_id)
                    if chunk:
                        # Convert distance to similarity (assume L2 distance)
                        distance = results["distances"][0][i]
                        similarity = 1 / (1 + distance)  # Convert distance to similarity
                        chunks_with_scores.append((chunk, similarity))
            
            return chunks_with_scores
        except Exception as e:
            logger.error(f"Error searching Chroma: {e}")
            raise

    def get_chunk(self, chunk_id: str) -> Optional[Chunk]:
        """Get a specific chunk."""
        return self.chunks.get(chunk_id)

    def delete_document(self, document_id: str) -> None:
        """Delete all chunks for a document."""
        try:
            # Get all chunk IDs for this document
            chunk_ids_to_delete = [
                cid for cid, chunk in self.chunks.items()
                if chunk.document_id == document_id
            ]
            
            # Delete from Chroma
            if chunk_ids_to_delete:
                self.collection.delete(ids=chunk_ids_to_delete)
            
            # Delete from local store
            for chunk_id in chunk_ids_to_delete:
                del self.chunks[chunk_id]
            
            logger.info(f"Deleted {len(chunk_ids_to_delete)} chunks for document {document_id}")
        except Exception as e:
            logger.error(f"Error deleting document from Chroma: {e}")
            raise

    def clear(self) -> None:
        """Clear all chunks."""
        try:
            # Delete the entire collection and recreate it
            self.client.delete_collection("f1_race_intelligence")
            self.collection = self.client.get_or_create_collection(
                name="f1_race_intelligence",
                metadata={"description": "F1 race documents and chunks"}
            )
            self.chunks.clear()
            logger.info("Cleared all chunks from Chroma")
        except Exception as e:
            logger.error(f"Error clearing Chroma: {e}")
            raise


def get_vector_store(mode: str = "memory", db_path: str = "./chroma_db") -> VectorStoreInterface:
    """Factory function to get appropriate vector store.
    
    Args:
        mode: "memory" or "chroma"
        db_path: Path for persistent storage (for Chroma)
        
    Returns:
        VectorStoreInterface instance
    """
    if mode == "memory":
        return InMemoryVectorStore()
    elif mode == "chroma":
        return ChromaVectorStore(db_path=db_path)
    else:
        logger.warning(f"Unknown vector store mode '{mode}', defaulting to memory")
        return InMemoryVectorStore()
