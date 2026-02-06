"""OpenF1 API client with caching and graceful degradation."""

import logging
import json
import time
import re
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

    def get_drivers(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get driver information for a session."""
        return []

    def get_weather(
        self,
        session_id: str,
    ) -> List[Dict[str, Any]]:
        """Get weather data for a session."""
        return []

    def get_position(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get position changes throughout a session."""
        return []

    def get_intervals(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get interval/gap data between drivers."""
        return []

    def get_overtakes(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get overtake data."""
        return []

    def get_team_radio(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get team radio communications."""
        return []

    def get_session_result(
        self,
        session_id: str,
    ) -> List[Dict[str, Any]]:
        """Get final session results/standings."""
        return []

    def get_starting_grid(
        self,
        session_id: str,
    ) -> List[Dict[str, Any]]:
        """Get starting grid positions."""
        return []


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

    def get_drivers(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return mock driver data."""
        drivers = [
            {"driver_number": 1, "name_acronym": "VER", "full_name": "Max Verstappen", "team_name": "Red Bull Racing"},
            {"driver_number": 11, "name_acronym": "PER", "full_name": "Sergio Perez", "team_name": "Red Bull Racing"},
            {"driver_number": 44, "name_acronym": "HAM", "full_name": "Lewis Hamilton", "team_name": "Mercedes"},
            {"driver_number": 63, "name_acronym": "RUS", "full_name": "George Russell", "team_name": "Mercedes"},
        ]
        if driver_number:
            return [d for d in drivers if d["driver_number"] == driver_number]
        return drivers

    def get_weather(
        self,
        session_id: str,
    ) -> List[Dict[str, Any]]:
        """Return mock weather data."""
        return [
            {
                "session_id": session_id,
                "air_temperature": 25.5,
                "track_temperature": 42.0,
                "humidity": 45,
                "rainfall": 0,
                "wind_speed": 3.2,
                "wind_direction": 180,
            }
        ]

    def get_position(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return mock position data."""
        return [
            {"session_id": session_id, "driver_number": 1, "position": 1},
            {"session_id": session_id, "driver_number": 11, "position": 2},
            {"session_id": session_id, "driver_number": 44, "position": 3},
        ]

    def get_intervals(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return mock interval data."""
        return [
            {"session_id": session_id, "driver_number": 1, "gap_to_leader": None, "interval": None},
            {"session_id": session_id, "driver_number": 11, "gap_to_leader": 2.5, "interval": 2.5},
            {"session_id": session_id, "driver_number": 44, "gap_to_leader": 8.3, "interval": 5.8},
        ]

    def get_overtakes(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return mock overtake data."""
        return [
            {"session_id": session_id, "overtaking_driver_number": 44, "overtaken_driver_number": 11, "position": 2},
        ]

    def get_team_radio(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return mock team radio data."""
        return [
            {"session_id": session_id, "driver_number": 1, "recording_url": "https://example.com/radio1.mp3"},
        ]

    def get_session_result(
        self,
        session_id: str,
    ) -> List[Dict[str, Any]]:
        """Return mock session result data."""
        return [
            {"session_id": session_id, "driver_number": 1, "position": 1, "dnf": False, "gap_to_leader": 0},
            {"session_id": session_id, "driver_number": 11, "position": 2, "dnf": False, "gap_to_leader": 5.2},
        ]

    def get_starting_grid(
        self,
        session_id: str,
    ) -> List[Dict[str, Any]]:
        """Return mock starting grid data."""
        return [
            {"session_id": session_id, "driver_number": 1, "position": 1, "lap_duration": 76.5},
            {"session_id": session_id, "driver_number": 11, "position": 2, "lap_duration": 76.8},
        ]


class OpenF1Client(OpenF1ClientInterface):
    """Real OpenF1 API client with caching."""

    def __init__(
        self,
        base_url: str = "https://api.openf1.org/v1",
        cache_timeout_hours: int = 24,
        retry_max_attempts: int = 3,
        retry_backoff_factor: float = 1.5,
    ):
        """Initialize OpenF1 client.
        
        Args:
            base_url: Base URL for OpenF1 API (default: https://api.openf1.org/v1)
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
        """Search for sessions by year and optional filters.
        
        Uses multi-query fallback strategy:
        1. Try exact GP name match against location/country_name
        2. Try GP name without "Grand Prix"
        3. Try country-based tokens
        4. Return all RACE sessions for year if no filters
        
        Args:
            year: F1 season year (e.g., 2024)
            gp_name: Grand Prix name (e.g., "Australian Grand Prix", "Monaco")
            session_type: Session type (RACE, QUALI, FP1, FP2, FP3) - API uses "Race", "Qualifying", etc.
            
        Returns:
            List of session objects matching criteria
        """
        try:
            # Query all sessions for the year
            params = {"year": year}
            all_sessions = self._request("sessions", params)
            
            if not all_sessions:
                logger.warning(f"No sessions found for year {year}")
                return []
            
            # Convert to list if needed
            sessions = all_sessions if isinstance(all_sessions, list) else [all_sessions]
            
            logger.debug(f"Total sessions for {year}: {len(sessions)}")
            
            # Normalize session_type if provided (API uses "Race", "Qualifying", "Practice", etc.)
            if session_type:
                session_type_normalized = session_type.lower()
                if session_type_normalized in ["race", "qualifying", "sprint", "practice"]:
                    # Capitalize first letter to match API format: "Race", "Qualifying", etc.
                    session_type_normalized = session_type_normalized.capitalize()
                # Also handle "FP1", "FP2", "FP3" -> might not exist in all years
                logger.debug(f"Normalized session_type: {session_type} -> {session_type_normalized}")
            
            # Filter by gp_name if provided (case-insensitive, with fallback queries)
            if gp_name and gp_name.lower() != "unknown":
                gp_lower = gp_name.lower()
                
                # Build list of query tokens to try (in priority order)
                query_tokens = []
                
                # Token 1: Full GP name (e.g., "Australian Grand Prix" or "Bahrain")
                query_tokens.append(gp_lower)
                
                # Token 2: GP name without "Grand Prix" (e.g., "Australian" from "Australian Grand Prix")
                without_gp = gp_lower.replace(" grand prix", "").replace("grand prix", "").strip()
                if without_gp and without_gp != gp_lower:
                    query_tokens.append(without_gp)
                
                # Token 3: Country name variations
                # Extract country from "X Grand Prix" -> "X"
                import re
                gp_match = re.search(r'^(\w+(?:\s+\w+)?)', gp_lower)
                if gp_match:
                    country_token = gp_match.group(1).strip()
                    if country_token and country_token != gp_lower:
                        query_tokens.append(country_token)
                
                # Try each query token in order
                filtered_sessions = None
                matched_query = None
                
                for query_token in query_tokens:
                    candidate_sessions = [
                        s for s in sessions
                        if query_token in s.get("location", "").lower()
                        or query_token in s.get("country_name", "").lower()
                        or query_token in s.get("circuit_short_name", "").lower()
                    ]
                    
                    if candidate_sessions:
                        filtered_sessions = candidate_sessions
                        matched_query = query_token
                        logger.debug(f"GP name match: '{gp_name}' matched token '{query_token}' ({len(candidate_sessions)} sessions)")
                        break
                
                if filtered_sessions:
                    sessions = filtered_sessions
                else:
                    # Log what we got instead
                    available = list(set([s.get("location", "N/A") for s in sessions[:10]]))
                    logger.warning(f"No sessions found for GP '{gp_name}'. Available locations: {available}")
            
            # Filter by session_type if provided (API format: "Race", "Qualifying", "Practice", etc.)
            if session_type:
                session_type_normalized = session_type.lower().capitalize()
                sessions = [
                    s for s in sessions
                    if s.get("session_type", "").lower() == session_type_normalized.lower()
                ]
                logger.debug(f"Filtered to {len(sessions)} sessions with type {session_type_normalized}")
            
            logger.info(f"Found {len(sessions)} sessions for {year} {gp_name or 'all'} {session_type or 'all'}")
            return sessions
        
        except Exception as e:
            logger.error(f"Error searching sessions: {e}")
            return []

    def get_race_control_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Get race control messages.
        
        Args:
            session_id: Session key (from OpenF1 API - called "session_key" in responses)
        """
        try:
            # OpenF1 API uses "session_key" parameter
            params = {"session_key": session_id}
            data = self._request("race_control", params)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and data:
                return [data]
            else:
                logger.debug(f"No race control messages for session {session_id}")
                return []
        except Exception as e:
            logger.warning(f"Error getting race control messages for {session_id}: {e}")
            return []

    def get_laps(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get lap times."""
        try:
            # Use session_id parameter (not session_key)
            params = {"session_id": session_id}
            if driver_number:
                params["driver_number"] = driver_number
            
            data = self._request("laps", params)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and data:
                return [data]
            else:
                logger.debug(f"No laps found for session {session_id}")
                return []
        except Exception as e:
            logger.warning(f"Error getting laps for {session_id}: {e}")
            return []

    def get_stints(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get stint data."""
        try:
            # OpenF1 API uses "session_key" parameter
            params = {"session_key": session_id}
            if driver_number:
                params["driver_number"] = driver_number
            
            data = self._request("stints", params)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and data:
                return [data]
            else:
                logger.debug(f"No stints for session {session_id}")
                return []
        except Exception as e:
            logger.warning(f"Error getting stints for {session_id}: {e}")
            return []

    def get_pit_stops(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get pit stop data."""
        try:
            # OpenF1 API uses "session_key" parameter
            params = {"session_key": session_id}
            if driver_number:
                params["driver_number"] = driver_number
            
            data = self._request("pit", params)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and data:
                return [data]
            else:
                logger.debug(f"No pit stops for session {session_id}")
                return []
        except Exception as e:
            logger.warning(f"Error getting pit stops for {session_id}: {e}")
            return []

    def get_drivers(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get driver information for a session.
        
        Args:
            session_id: Session key
            driver_number: Optional driver number filter
            
        Returns:
            List of driver dicts with name, team, etc.
        """
        try:
            params = {"session_key": session_id}
            if driver_number:
                params["driver_number"] = driver_number
            
            data = self._request("drivers", params)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and data:
                return [data]
            else:
                logger.debug(f"No drivers for session {session_id}")
                return []
        except Exception as e:
            logger.warning(f"Error getting drivers for {session_id}: {e}")
            return []

    def get_weather(
        self,
        session_id: str,
    ) -> List[Dict[str, Any]]:
        """Get weather data for a session.
        
        Args:
            session_id: Session key
            
        Returns:
            List of weather readings (air_temp, track_temp, humidity, rainfall, wind, etc.)
        """
        try:
            params = {"session_key": session_id}
            
            data = self._request("weather", params)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and data:
                return [data]
            else:
                logger.debug(f"No weather data for session {session_id}")
                return []
        except Exception as e:
            logger.warning(f"Error getting weather for {session_id}: {e}")
            return []

    def get_position(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get position changes throughout a session.
        
        Args:
            session_id: Session key
            driver_number: Optional driver number filter
            
        Returns:
            List of position records (driver, position, timestamp)
        """
        try:
            params = {"session_key": session_id}
            if driver_number:
                params["driver_number"] = driver_number
            
            data = self._request("position", params)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and data:
                return [data]
            else:
                logger.debug(f"No position data for session {session_id}")
                return []
        except Exception as e:
            logger.warning(f"Error getting position for {session_id}: {e}")
            return []

    def get_intervals(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get interval/gap data between drivers (race only).
        
        Args:
            session_id: Session key
            driver_number: Optional driver number filter
            
        Returns:
            List of interval records (gap_to_leader, interval to car ahead)
        """
        try:
            params = {"session_key": session_id}
            if driver_number:
                params["driver_number"] = driver_number
            
            data = self._request("intervals", params)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and data:
                return [data]
            else:
                logger.debug(f"No intervals for session {session_id}")
                return []
        except Exception as e:
            logger.warning(f"Error getting intervals for {session_id}: {e}")
            return []

    def get_overtakes(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get overtake data (race only).
        
        Args:
            session_id: Session key
            driver_number: Optional driver number filter (overtaking driver)
            
        Returns:
            List of overtake records (overtaking_driver, overtaken_driver, position, timestamp)
        """
        try:
            params = {"session_key": session_id}
            if driver_number:
                params["overtaking_driver_number"] = driver_number
            
            data = self._request("overtakes", params)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and data:
                return [data]
            else:
                logger.debug(f"No overtakes for session {session_id}")
                return []
        except Exception as e:
            logger.warning(f"Error getting overtakes for {session_id}: {e}")
            return []

    def get_team_radio(
        self,
        session_id: str,
        driver_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get team radio communications.
        
        Args:
            session_id: Session key
            driver_number: Optional driver number filter
            
        Returns:
            List of radio records (driver, timestamp, recording_url)
        """
        try:
            params = {"session_key": session_id}
            if driver_number:
                params["driver_number"] = driver_number
            
            data = self._request("team_radio", params)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and data:
                return [data]
            else:
                logger.debug(f"No team radio for session {session_id}")
                return []
        except Exception as e:
            logger.warning(f"Error getting team radio for {session_id}: {e}")
            return []

    def get_session_result(
        self,
        session_id: str,
    ) -> List[Dict[str, Any]]:
        """Get final session results/standings.
        
        Args:
            session_id: Session key
            
        Returns:
            List of result records (position, driver, duration, gap, dnf/dns/dsq status)
        """
        try:
            params = {"session_key": session_id}
            
            data = self._request("session_result", params)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and data:
                return [data]
            else:
                logger.debug(f"No session results for session {session_id}")
                return []
        except Exception as e:
            logger.warning(f"Error getting session results for {session_id}: {e}")
            return []

    def get_starting_grid(
        self,
        session_id: str,
    ) -> List[Dict[str, Any]]:
        """Get starting grid positions.
        
        Args:
            session_id: Session key
            
        Returns:
            List of grid positions (position, driver, qualifying lap time)
        """
        try:
            params = {"session_key": session_id}
            
            data = self._request("starting_grid", params)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and data:
                return [data]
            else:
                logger.debug(f"No starting grid for session {session_id}")
                return []
        except Exception as e:
            logger.warning(f"Error getting starting grid for {session_id}: {e}")
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
