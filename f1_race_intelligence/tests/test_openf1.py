"""Tests for OpenF1 API client."""

import pytest
from openf1.api import MockOpenF1Client, get_openf1_client


class TestMockOpenF1Client:
    """Test mock OpenF1 client."""

    def test_search_sessions_returns_list(self):
        """Test that search_sessions returns a list."""
        client = MockOpenF1Client()
        sessions = client.search_sessions(2023, "Monaco", "RACE")
        
        assert isinstance(sessions, list)
        assert len(sessions) > 0

    def test_search_sessions_contains_required_fields(self):
        """Test that sessions have required fields."""
        client = MockOpenF1Client()
        sessions = client.search_sessions(2023, "Monaco", "RACE")
        
        for session in sessions:
            assert "session_id" in session
            assert "year" in session
            assert "gp_name" in session
            assert "session_type" in session

    def test_get_race_control_messages(self):
        """Test getting race control messages."""
        client = MockOpenF1Client()
        messages = client.get_race_control_messages("test_session")
        
        assert isinstance(messages, list)
        assert len(messages) > 0
        
        for msg in messages:
            assert "session_id" in msg
            assert "message" in msg

    def test_get_laps(self):
        """Test getting lap data."""
        client = MockOpenF1Client()
        laps = client.get_laps("test_session", driver_number=1)
        
        assert isinstance(laps, list)
        assert len(laps) > 0
        
        for lap in laps:
            assert "lap_number" in lap
            assert "driver_number" in lap
            assert "sector_1" in lap

    def test_get_stints(self):
        """Test getting stint data."""
        client = MockOpenF1Client()
        stints = client.get_stints("test_session", driver_number=1)
        
        assert isinstance(stints, list)
        assert len(stints) > 0
        
        for stint in stints:
            assert "stint_number" in stint
            assert "compound" in stint
            assert "lap_start" in stint

    def test_get_pit_stops(self):
        """Test getting pit stop data."""
        client = MockOpenF1Client()
        pit_stops = client.get_pit_stops("test_session", driver_number=1)
        
        assert isinstance(pit_stops, list)
        assert len(pit_stops) > 0
        
        for pit_stop in pit_stops:
            assert "lap" in pit_stop
            assert "pit_duration" in pit_stop


class TestOpenF1ClientFactory:
    """Test OpenF1 client factory."""

    def test_factory_returns_mock(self):
        """Test that factory returns mock client."""
        client = get_openf1_client(mode="mock")
        assert isinstance(client, MockOpenF1Client)

    def test_mock_client_has_all_methods(self):
        """Test that mock client has all required methods."""
        client = get_openf1_client(mode="mock")
        
        assert hasattr(client, "search_sessions")
        assert hasattr(client, "get_race_control_messages")
        assert hasattr(client, "get_laps")
        assert hasattr(client, "get_stints")
        assert hasattr(client, "get_pit_stops")

    def test_factory_unknown_mode_returns_mock(self):
        """Test that unknown mode defaults to mock."""
        client = get_openf1_client(mode="unknown")
        assert isinstance(client, MockOpenF1Client)
