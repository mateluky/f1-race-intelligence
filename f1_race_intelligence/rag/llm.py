"""LLM interface and implementations.

Supports:
- MockLLM: For testing/offline development
- OllamaLLM: Free, local, open-source LLM via Ollama
"""

import json
import logging
import requests
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class LLMInterface(ABC):
    """Abstract base class for LLM interactions."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate text from a prompt."""
        pass

    @abstractmethod
    def extract_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        schema: Optional[BaseModel] = None,
    ) -> Dict[str, Any]:
        """Extract JSON from a prompt."""
        pass


class MockLLM(LLMInterface):
    """Mock LLM for testing and offline mode."""

    def __init__(self):
        """Initialize mock LLM."""
        logger.info("Initialized MockLLM (development/testing mode)")

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate mock response."""
        logger.debug(f"MockLLM.generate() called with prompt length {len(prompt)}")
        
        # Return deterministic mock responses based on prompt keywords
        if "claim" in prompt.lower() or "extract" in prompt.lower():
            return """Based on the document, key race insights include strategic tire management, 
            driver performance variations across different track sectors, and the impact of pit stop timing 
            on final race results. The weather conditions evolved during the race, affecting grip levels 
            and tire degradation patterns."""
        
        if "summary" in prompt.lower():
            return """The race was decided by strategic tire management and driver performance during 
            key phases. Early pit stops proved advantageous, and the team demonstrated superior pace 
            in the second half of the race. The final positions reflected both strategic acumen and 
            driver execution."""
        
        if "follow" in prompt.lower() or "question" in prompt.lower():
            return """1. How would an alternative strategy have affected the final outcome?
2. What was the impact of safety car windows on pit stop timing?
3. How did fuel management influence race pace?
4. What were the critical tire degradation rates?
5. How did track temperature changes affect tire compounds?"""
        
        return "This is a mock LLM response for testing purposes."

    def extract_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        schema: Optional[BaseModel] = None,
    ) -> Dict[str, Any]:
        """Extract mock JSON response."""
        logger.debug("MockLLM.extract_json() called")
        
        # Return mock JSON based on prompt content
        if "claim" in prompt.lower() or "extract" in prompt.lower():
            return {
                "claims": [
                    {
                        "claim_text": "Driver maintained consistent pace throughout the race",
                        "claim_type": "pace",
                        "drivers": ["driver_1"],
                        "teams": ["team_1"],
                        "lap_start": 1,
                        "lap_end": 58,
                        "confidence": 0.85,
                        "rationale": "Consistent lap times in telemetry data"
                    },
                    {
                        "claim_text": "Strategic pit stop timing provided advantage",
                        "claim_type": "strategy",
                        "drivers": ["driver_2"],
                        "teams": ["team_2"],
                        "lap_start": 20,
                        "lap_end": 30,
                        "confidence": 0.75,
                        "rationale": "Pit stop occurred during optimal window"
                    }
                ]
            }
        
        if "session" in prompt.lower() or "entity" in prompt.lower():
            return {
                "year": 2023,
                "gp_name": "Generic Grand Prix",
                "session_type": "RACE",
                "drivers": {"Driver One": 1, "Driver Two": 2},
                "teams": ["Team A", "Team B"]
            }
        
        if "followup" in prompt.lower() or "question" in prompt.lower():
            return {
                "questions": [
                    "How would alternative strategy have changed the outcome?",
                    "What was the impact of safety car timing?",
                    "How did fuel strategy influence the race?"
                ]
            }
        
        return {"status": "mock_response"}


class OllamaLLM(LLMInterface):
    """Local open-source LLM via Ollama.
    
    Free, no API key required, runs locally.
    Requires Ollama to be installed and running.
    
    Setup:
        1. Install Ollama from https://ollama.ai
        2. Run: ollama pull llama3
        3. Run: ollama serve (or it auto-starts)
        4. API will be available at http://localhost:11434
    """

    def __init__(self, model: str = "llama3", endpoint: str = "http://localhost:11434", timeout: int = 120):
        """Initialize Ollama LLM.
        
        Args:
            model: Ollama model name (default: "llama3", 8B variant)
            endpoint: Ollama API endpoint (default: localhost:11434)
            timeout: Request timeout in seconds (default: 120s for generation)
        """
        self.model = model
        self.endpoint = endpoint.rstrip("/")
        self.api_url = f"{self.endpoint}/api/generate"
        self.timeout = timeout
        self.available = False
        
        logger.info(f"Initialized OllamaLLM with model '{model}' at {self.endpoint} (timeout={timeout}s)")
        
        # Test connection (non-blocking)
        self._test_connection()

    def _test_connection(self) -> bool:
        """Test if Ollama is running and model is available. Non-blocking."""
        try:
            response = requests.post(
                self.api_url,
                json={"model": self.model, "prompt": "test", "stream": False},
                timeout=10,
            )
            if response.status_code == 200:
                self.available = True
                logger.info(f"✓ Ollama available at {self.endpoint}")
                return True
            else:
                logger.warning(
                    f"Ollama returned status {response.status_code}. "
                    f"Run: ollama pull {self.model}"
                )
                return False
        except requests.exceptions.ConnectionError:
            logger.warning(
                f"Ollama unreachable at {self.endpoint}. Run: ollama serve"
            )
            return False
        except requests.exceptions.Timeout:
            logger.warning("Ollama connection test timed out")
            return False
        except Exception as e:
            logger.warning(f"Ollama test failed: {e}")
            return False

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate text using Ollama API with graceful error handling."""
        try:
            # Combine system and user prompts
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"
            
            payload = {
                "model": self.model,
                "prompt": full_prompt,
                "stream": False,
                "temperature": temperature,
            }
            
            response = requests.post(self.api_url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            
            result = response.json()
            text = result.get("response", "").strip()
            
            if not text:
                logger.warning("Ollama returned empty response")
                raise RuntimeError("Empty response from Ollama")
            
            return text
        
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Ollama unreachable: {e}")
            raise RuntimeError(f"Ollama not running. Start with: ollama serve")
        except requests.exceptions.Timeout:
            logger.error(f"Ollama timeout after {self.timeout}s")
            raise RuntimeError(f"Ollama timeout (>{self.timeout}s). Try restarting: ollama serve")
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            raise

    def extract_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        schema: Optional[BaseModel] = None,
    ) -> Dict[str, Any]:
        """Extract JSON using Ollama API with robust parsing."""
        try:
            json_prompt = (
                prompt
                + "\n\nRespond with ONLY valid JSON, no markdown, no explanation."
            )
            
            response_text = self.generate(
                json_prompt,
                system_prompt=system_prompt,
                temperature=0.1,  # Lower temp for deterministic JSON
            )
            
            return self._extract_json_from_text(response_text)
        
        except requests.exceptions.Timeout:
            logger.error("JSON extraction timeout")
            raise RuntimeError("Ollama timeout during JSON extraction")
        except Exception as e:
            logger.error(f"JSON extraction error: {e}")
            raise

    def _extract_json_from_text(self, text: str) -> Dict[str, Any]:
        """Extract valid JSON from potentially malformed response."""
        text = text.strip()
        
        # Remove markdown code blocks
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        
        # Find first { and last } to extract JSON block
        if "{" in text and "}" in text:
            start = text.find("{")
            end = text.rfind("}") + 1
            text = text[start:end]
        
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed: {e}")
            logger.error(f"Text: {text[:300]}...")
            # Return empty structure instead of crashing
            return {"error": "json_parse_failed", "raw": text[:200]}


def get_llm(mode: str = "ollama", fallback_on_error: bool = True) -> Tuple[LLMInterface, bool]:
    """Factory function to get appropriate LLM instance with optional fallback.
    
    Args:
        mode: "mock" or "ollama" (default: "ollama")
        fallback_on_error: If True and Ollama unavailable, fall back to MockLLM (default: True)
    
    Returns:
        Tuple of (LLMInterface instance, using_fallback: bool)
        - using_fallback is True if Ollama was requested but fell back to MockLLM
    """
    if mode == "mock":
        return MockLLM(), False
    
    elif mode == "ollama":
        try:
            ollama = OllamaLLM(model="llama3")
            # Check if connection test succeeded
            if ollama.available:
                return ollama, False
            else:
                # Ollama unavailable
                if fallback_on_error:
                    logger.info("Ollama unavailable, falling back to MockLLM")
                    return MockLLM(), True
                else:
                    raise RuntimeError("Ollama unavailable and fallback disabled")
        except Exception as e:
            logger.warning(f"Failed to initialize Ollama: {e}")
            if fallback_on_error:
                logger.info("Falling back to MockLLM for testing")
                return MockLLM(), True
            else:
                raise
    
    else:
        logger.warning(f"Unknown LLM mode '{mode}', defaulting to ollama")
        ollama = OllamaLLM(model="llama3")
        if ollama.available:
            return ollama, False
        else:
            return MockLLM(), True
