"""OpenF1 API client with caching and graceful degradation."""

import logging
import json
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from pathlib import Path
import hashlib

try:
    import requests
except ImportError:
    requests = None

try:
    import requests_cache
except ImportError:
    requests_cache = None

logger = logging.getLogger(__name__)


class OpenF1ClientInterface(ABC):
    """Abstract interface for OpenF1 API client."""

    @abstractmethod
    def search_sessions(
        self,
        year: int,
        gp_name: Optional[str] = None,
        session_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search for F1 sessions."""
        pass

    @abstractmethod
    def get_race_control_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Get race control messages for a session."""
        pass

    @abstractmethod
    def get_laps(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get lap times/data."""
        pass

    @abstractmethod
    def get_stints(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get stint/tire data."""
        pass

    @abstractmethod
    def get_pit_stops(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get pit stop data."""
        pass


class MockOpenF1Client(OpenF1ClientInterface):
    """Mock OpenF1 client for testing and offline mode."""

    def __init__(self):
        """Initialize mock client."""
        logger.info("Initialized MockOpenF1Client")

    def search_sessions(
        self,
        year: int,
        gp_name: Optional[str] = None,
        session_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return mock session data."""
        return [
            {
                "session_id": f"mock_session_{year}_monaco",
                "year": year,
                "gp_name": "Monaco Grand Prix",
                "session_type": session_type or "RACE",
                "session_date": f"{year}-05-28",
                "location": "Monte-Carlo, Monaco",
            }
        ]

    def get_race_control_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Return mock race control messages."""
        return [
            {
                "session_id": session_id,
                "lap": 1,
                "message": "Session started",
                "time": "00:00:00",
            },
            {
                "session_id": session_id,
                "lap": 15,
                "message": "Yellow flag sector 1",
                "time": "00:30:45",
            },
            {
                "session_id": session_id,
                "lap": 22,
                "message": "DRS enabled",
                "time": "01:05:30",
            },
        ]

    def get_laps(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return mock lap times."""
        laps = []
        driver_num = driver_number or 1
        
        for lap in range(1, 59):
            laps.append({
                "session_id": session_id,
                "driver_number": driver_num,
                "lap_number": lap,
                "sector_1": 31.2 + (0.1 if lap < 20 else -0.05),
                "sector_2": 42.1 + (0.2 if lap < 20 else 0.0),
                "sector_3": 28.9 + (0.15 if lap < 20 else 0.05),
                "lap_time": 102.2 + (0.3 if lap < 20 else 0.0),
                "pit_loss": 0 if lap not in [22] else 25,
            })
        
        return laps

    def get_stints(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return mock stint data."""
        return [
            {
                "session_id": session_id,
                "driver_number": driver_number or 1,
                "stint_number": 1,
                "compound": "soft",
                "lap_start": 1,
                "lap_end": 22,
                "laps_on_compound": 22,
            },
            {
                "session_id": session_id,
                "driver_number": driver_number or 1,
                "stint_number": 2,
                "compound": "hard",
                "lap_start": 23,
                "lap_end": 58,
                "laps_on_compound": 36,
            },
        ]

    def get_pit_stops(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return mock pit stop data."""
        return [
            {
                "session_id": session_id,
                "driver_number": driver_number or 1,
                "lap": 22,
                "time_of_day": "01:02:30",
                "pit_duration": 2.3,
                "tyre_from": "soft",
                "tyre_to": "hard",
            }
        ]


class OpenF1Client(OpenF1ClientInterface):
    """Real OpenF1 API client with caching."""

    def __init__(
        self,
        base_url: str = "https://api.openf1.org",
        cache_timeout_hours: int = 24,
        retry_max_attempts: int = 3,
        retry_backoff_factor: float = 1.5,
    ):
        """Initialize OpenF1 client.
        
        Args:
            base_url: Base URL for OpenF1 API
            cache_timeout_hours: Cache timeout in hours
            retry_max_attempts: Max retry attempts for failed requests
            retry_backoff_factor: Backoff factor for retries
        """
        if requests is None:
            raise ImportError("requests not installed. Install with: pip install requests")
        
        self.base_url = base_url
        self.retry_max_attempts = retry_max_attempts
        self.retry_backoff_factor = retry_backoff_factor
        self.local_cache: Dict[str, tuple[Any, float]] = {}  # {key: (data, timestamp)}
        
        # Set up requests cache if available
        if requests_cache:
            self.session = requests_cache.CachedSession(
                f"f1_api_cache",
                backend="sqlite",
                expire_after=timedelta(hours=cache_timeout_hours),
            )
            logger.info(f"Initialized OpenF1Client with caching (timeout={cache_timeout_hours}h)")
        else:
            self.session = requests.Session()
            logger.warning("requests_cache not available; using in-memory cache only")

    def _request(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make a request to the OpenF1 API with retry logic.
        
        Args:
            endpoint: API endpoint (without base URL)
            params: Query parameters
            
        Returns:
            Response data as dict/list
            
        Raises:
            Exception: If all retries fail
        """
        cache_key = hashlib.md5(f"{endpoint}_{params}".encode()).hexdigest()
        
        # Check local cache first
        if cache_key in self.local_cache:
            data, timestamp = self.local_cache[cache_key]
            if time.time() - timestamp < 86400:  # 24 hour cache
                logger.debug(f"Cache hit for {endpoint}")
                return data
        
        url = f"{self.base_url}/{endpoint}"
        
        for attempt in range(self.retry_max_attempts):
            try:
                logger.debug(f"Request {attempt + 1}/{self.retry_max_attempts}: {endpoint}")
                response = self.session.get(url, params=params or {}, timeout=10)
                response.raise_for_status()
                
                data = response.json()
                # Cache the result
                self.local_cache[cache_key] = (data, time.time())
                return data
            
            except requests.exceptions.RequestException as e:
                if attempt < self.retry_max_attempts - 1:
                    wait_time = self.retry_backoff_factor ** attempt
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}): {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"All {self.retry_max_attempts} attempts failed for {endpoint}")
                    raise
            
            except Exception as e:
                logger.error(f"Unexpected error in request to {endpoint}: {e}")
                raise

    def search_sessions(
        self,
        year: int,
        gp_name: Optional[str] = None,
        session_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search for sessions."""
        try:
            params = {"year": year}
            if gp_name:
                params["gp_name"] = gp_name
            if session_type:
                params["session_type"] = session_type
            
            data = self._request("sessions", params)
            # API might return single object or list
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return [data]
            else:
                return []
        except Exception as e:
            logger.error(f"Error searching sessions: {e}")
            return []

    def get_race_control_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Get race control messages."""
        try:
            data = self._request("race_control", {"session_key": session_id})
            if isinstance(data, list):
                return data
            else:
                return [data] if data else []
        except Exception as e:
            logger.error(f"Error getting race control messages: {e}")
            return []

    def get_laps(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get lap times."""
        try:
            params = {"session_key": session_id}
            if driver_number:
                params["driver_number"] = driver_number
            
            data = self._request("laps", params)
            if isinstance(data, list):
                return data
            else:
                return [data] if data else []
        except Exception as e:
            logger.error(f"Error getting laps: {e}")
            return []

    def get_stints(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get stint data."""
        try:
            params = {"session_key": session_id}
            if driver_number:
                params["driver_number"] = driver_number
            
            data = self._request("stints", params)
            if isinstance(data, list):
                return data
            else:
                return [data] if data else []
        except Exception as e:
            logger.error(f"Error getting stints: {e}")
            return []

    def get_pit_stops(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get pit stop data."""
        try:
            params = {"session_key": session_id}
            if driver_number:
                params["driver_number"] = driver_number
            
            data = self._request("pit_stops", params)
            if isinstance(data, list):
                return data
            else:
                return [data] if data else []
        except Exception as e:
            logger.error(f"Error getting pit stops: {e}")
            return []


def get_openf1_client(mode: str = "mock", **kwargs) -> OpenF1ClientInterface:
    """Factory function to get OpenF1 client.
    
    Args:
        mode: "mock" or "real"
        **kwargs: Arguments for the client
        
    Returns:
        OpenF1ClientInterface instance
    """
    if mode == "mock":
        return MockOpenF1Client()
    elif mode == "real":
        return OpenF1Client(**kwargs)
    else:
        logger.warning(f"Unknown OpenF1 mode '{mode}', defaulting to mock")
        return MockOpenF1Client()
