"""Embedding generation and management."""

import logging
from abc import ABC, abstractmethod
from typing import List, Optional
import numpy as np

logger = logging.getLogger(__name__)


class EmbedderInterface(ABC):
    """Abstract interface for text embeddings."""

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Embed a single text string.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        pass

    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple text strings.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        pass

    @abstractmethod
    def get_embedding_dim(self) -> int:
        """Get the dimension of embeddings produced by this embedder.
        
        Returns:
            Embedding dimension
        """
        pass


class MockEmbedder(EmbedderInterface):
    """Mock embedder for testing and development."""

    def __init__(self, dim: int = 384):
        """Initialize mock embedder.
        
        Args:
            dim: Embedding dimension (default 384)
        """
        self.dim = dim
        logger.info(f"Initialized MockEmbedder with dimension {dim}")

    def embed_text(self, text: str) -> List[float]:
        """Create deterministic mock embedding from text hash."""
        # Use hash to create deterministic embeddings
        hash_val = hash(text)
        np.random.seed(abs(hash_val) % (2**31))
        return np.random.randn(self.dim).astype(float).tolist()

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Create mock embeddings for multiple texts."""
        return [self.embed_text(text) for text in texts]

    def get_embedding_dim(self) -> int:
        """Return embedding dimension."""
        return self.dim


class SentenceTransformerEmbedder(EmbedderInterface):
    """Embedder using sentence-transformers library."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        """Initialize SentenceTransformer embedder.
        
        Args:
            model_name: Name of the sentence-transformer model
        """
        try:
            from sentence_transformers import SentenceTransformer
            
            logger.info(f"Loading SentenceTransformer model: {model_name}")
            self.model = SentenceTransformer(model_name)
            self.dim = self.model.get_sentence_embedding_dimension()
            logger.info(f"Loaded model with dimension {self.dim}")
        except ImportError:
            logger.error("sentence-transformers not installed. Install with: pip install sentence-transformers")
            raise
        except Exception as e:
            logger.error(f"Failed to load embedder model: {e}")
            raise

    def embed_text(self, text: str) -> List[float]:
        """Embed a single text string."""
        embedding = self.model.encode(text, convert_to_tensor=False)
        return embedding.tolist()

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple text strings."""
        embeddings = self.model.encode(texts, convert_to_tensor=False)
        return [emb.tolist() for emb in embeddings]

    def get_embedding_dim(self) -> int:
        """Return embedding dimension."""
        return self.dim


class OpenAIEmbedder(EmbedderInterface):
    """Embedder using OpenAI API."""

    def __init__(self, api_key: Optional[str] = None, model: str = "text-embedding-3-small"):
        """Initialize OpenAI embedder.
        
        Args:
            api_key: OpenAI API key (loads from env if None)
            model: Model name (default: text-embedding-3-small)
        """
        try:
            import openai
            from openai import OpenAI
            
            if api_key:
                openai.api_key = api_key
            
            self.client = OpenAI()
            self.model = model
            
            # Determine embedding dimension based on model
            if "3-small" in model:
                self.dim = 1536
            elif "3-large" in model:
                self.dim = 3072
            elif "ada" in model:
                self.dim = 1536
            else:
                self.dim = 1536
            
            logger.info(f"Initialized OpenAI embedder with model {model} (dim={self.dim})")
        except ImportError:
            logger.error("openai package not installed. Install with: pip install openai")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI embedder: {e}")
            raise

    def embed_text(self, text: str) -> List[float]:
        """Embed a single text string using OpenAI API."""
        try:
            response = self.client.embeddings.create(
                input=text,
                model=self.model
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"OpenAI embedding error: {e}")
            raise

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple text strings using OpenAI API."""
        try:
            response = self.client.embeddings.create(
                input=texts,
                model=self.model
            )
            # Sort by index to maintain order
            sorted_data = sorted(response.data, key=lambda x: x.index)
            return [item.embedding for item in sorted_data]
        except Exception as e:
            logger.error(f"OpenAI batch embedding error: {e}")
            raise

    def get_embedding_dim(self) -> int:
        """Return embedding dimension."""
        return self.dim


def get_embedder(mode: str = "mock", **kwargs) -> EmbedderInterface:
    """Factory function to get appropriate embedder.
    
    Args:
        mode: "mock", "sentence-transformers", or "openai"
        **kwargs: Additional arguments for the embedder
        
    Returns:
        EmbedderInterface instance
    """
    if mode == "mock":
        return MockEmbedder(**kwargs)
    elif mode == "sentence-transformers":
        model_name = kwargs.get("model_name", "sentence-transformers/all-MiniLM-L6-v2")
        return SentenceTransformerEmbedder(model_name=model_name)
    elif mode == "openai":
        api_key = kwargs.get("api_key")
        model = kwargs.get("model", "text-embedding-3-small")
        return OpenAIEmbedder(api_key=api_key, model=model)
    else:
        logger.warning(f"Unknown embedder mode '{mode}', defaulting to mock")
        return MockEmbedder(**kwargs)
