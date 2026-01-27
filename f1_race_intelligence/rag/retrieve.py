"""Retrieval logic for the RAG pipeline."""

import logging
from typing import List, Optional, Dict, Any

from rag.schemas import RetrievalResult, Chunk
from rag.embed import EmbedderInterface
from rag.store import VectorStoreInterface

logger = logging.getLogger(__name__)


class Retriever:
    """Retrieves relevant chunks from the vector store."""

    def __init__(
        self,
        embedder: EmbedderInterface,
        vector_store: VectorStoreInterface,
        top_k: int = 5,
    ):
        """Initialize retriever.
        
        Args:
            embedder: Embedder for converting text to vectors
            vector_store: Vector store for similarity search
            top_k: Number of top results to return
        """
        self.embedder = embedder
        self.vector_store = vector_store
        self.top_k = top_k
        logger.info(f"Initialized Retriever with top_k={top_k}")

    def retrieve(
        self,
        query: str,
        document_id: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> RetrievalResult:
        """Retrieve relevant chunks for a query.
        
        Args:
            query: Query text
            document_id: Optional document ID to filter results
            top_k: Optional override for number of results
            
        Returns:
            RetrievalResult with chunks and similarity scores
        """
        if top_k is None:
            top_k = self.top_k
        
        # Embed the query
        query_embedding = self.embedder.embed_text(query)
        
        # Search the vector store
        metadata_filter = None
        if document_id:
            metadata_filter = {"document_id": document_id}
        
        search_results = self.vector_store.search(
            query_embedding=query_embedding,
            k=top_k,
            metadata_filter=metadata_filter,
        )
        
        # Extract chunks and scores
        chunks = []
        scores = []
        for chunk, score in search_results:
            chunks.append(chunk)
            scores.append(score)
        
        logger.info(f"Retrieved {len(chunks)} chunks for query (top_k={top_k})")
        
        return RetrievalResult(
            chunks=chunks,
            scores=scores,
            query=query,
        )

    def retrieve_for_claim_evidence(
        self,
        claim_text: str,
        document_id: str,
        entity_keywords: Optional[List[str]] = None,
        top_k: Optional[int] = None,
    ) -> List[Chunk]:
        """Retrieve chunks most relevant to supporting/refuting a claim.
        
        This performs an expanded search to find evidence chunks.
        
        Args:
            claim_text: The claim to find evidence for
            document_id: Document ID to search within
            entity_keywords: Optional keywords (drivers, teams) to boost relevance
            top_k: Optional override for number of results
            
        Returns:
            List of relevant chunks
        """
        if top_k is None:
            top_k = self.top_k * 2  # Get more for evidence mapping
        
        # Build enhanced query
        queries = [claim_text]
        
        # Add entity-specific queries if provided
        if entity_keywords:
            for keyword in entity_keywords[:3]:  # Limit to 3 keywords
                queries.append(f"{claim_text} {keyword}")
        
        # Retrieve for each query and combine results
        all_chunks = {}
        all_scores = {}
        
        for query in queries:
            result = self.retrieve(query, document_id=document_id, top_k=top_k)
            for chunk, score in zip(result.chunks, result.scores):
                if chunk.id not in all_chunks:
                    all_chunks[chunk.id] = chunk
                    all_scores[chunk.id] = score
                else:
                    # Average scores if chunk appears in multiple results
                    all_scores[chunk.id] = (all_scores[chunk.id] + score) / 2
        
        # Sort by combined score and return top chunks
        sorted_chunks = sorted(
            all_chunks.items(),
            key=lambda x: all_scores[x[0]],
            reverse=True
        )
        
        return [chunk for chunk_id, chunk in sorted_chunks[:top_k]]

    def get_context_window(
        self,
        chunk_id: str,
        context_size: int = 2,
    ) -> List[Chunk]:
        """Get a chunk with surrounding context.
        
        Args:
            chunk_id: ID of the target chunk
            context_size: Number of chunks before/after to include
            
        Returns:
            List of chunks with target in the middle
        """
        target_chunk = self.vector_store.get_chunk(chunk_id)
        if not target_chunk:
            return []
        
        # This is a simple implementation; could be enhanced
        # to properly fetch neighboring chunks
        return [target_chunk]

    def batch_retrieve(
        self,
        queries: List[str],
        document_id: Optional[str] = None,
    ) -> List[RetrievalResult]:
        """Retrieve results for multiple queries.
        
        Args:
            queries: List of queries
            document_id: Optional document ID filter
            
        Returns:
            List of RetrievalResult objects
        """
        results = []
        for query in queries:
            result = self.retrieve(query, document_id=document_id)
            results.append(result)
        
        return results


class RAGContext:
    """Manages context for RAG generation."""

    def __init__(self, retriever: Retriever):
        """Initialize RAG context.
        
        Args:
            retriever: Retriever instance
        """
        self.retriever = retriever
        self.context_chunks: List[Chunk] = []
        self.context_scores: List[float] = []

    def add_retrieved_chunks(self, result: RetrievalResult) -> None:
        """Add retrieved chunks to context.
        
        Args:
            result: RetrievalResult from retriever
        """
        self.context_chunks.extend(result.chunks)
        self.context_scores.extend(result.scores)

    def get_context_text(self, max_length: Optional[int] = None) -> str:
        """Get formatted context text.
        
        Args:
            max_length: Optional max length in characters
            
        Returns:
            Formatted context text with chunk boundaries marked
        """
        context_parts = []
        total_length = 0
        
        for chunk, score in zip(self.context_chunks, self.context_scores):
            chunk_text = f"[Score: {score:.3f}] {chunk.content}"
            context_parts.append(chunk_text)
            total_length += len(chunk_text)
            
            if max_length and total_length > max_length:
                break
        
        return "\n\n---\n\n".join(context_parts)

    def clear(self) -> None:
        """Clear context."""
        self.context_chunks.clear()
        self.context_scores.clear()
