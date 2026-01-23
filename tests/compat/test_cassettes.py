"""Tests for cassette management infrastructure.

These tests verify the VCR/cassette-style HTTP recording and replay system.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import httpx
import pytest

from tests.compat.cassettes import (
    Cassette,
    CassetteManager,
    CassetteMode,
    CassetteRecorder,
    CassetteStore,
    HTTPInteraction,
    HTTPRequest,
    HTTPResponse,
    get_cassette_manager,
)

if TYPE_CHECKING:
    import respx


class TestHTTPRequest:
    """Tests for HTTPRequest dataclass."""

    def test_signature_basic(self) -> None:
        """Test request signature generation."""
        request = HTTPRequest(
            method="POST",
            url="https://example.org/api/Contact/get",
        )
        signature = request.signature()
        assert len(signature) == 16
        assert signature.isalnum()

    def test_signature_with_body(self) -> None:
        """Test signature includes body content."""
        request1 = HTTPRequest(
            method="POST",
            url="https://example.org/api/Contact/get",
            body={"select": ["id"]},
        )
        request2 = HTTPRequest(
            method="POST",
            url="https://example.org/api/Contact/get",
            body={"select": ["id", "name"]},
        )

        assert request1.signature() != request2.signature()

    def test_signature_deterministic(self) -> None:
        """Test signature is deterministic for same request."""
        request1 = HTTPRequest(method="POST", url="https://example.org/api")
        request2 = HTTPRequest(method="POST", url="https://example.org/api")

        assert request1.signature() == request2.signature()

    def test_signature_dict_body_order_independent(self) -> None:
        """Test dict body order doesn't affect signature."""
        request1 = HTTPRequest(
            method="POST",
            url="https://example.org/api",
            body={"a": 1, "b": 2},
        )
        request2 = HTTPRequest(
            method="POST",
            url="https://example.org/api",
            body={"b": 2, "a": 1},
        )

        assert request1.signature() == request2.signature()


class TestCassette:
    """Tests for Cassette class."""

    def test_create_empty_cassette(self) -> None:
        """Test creating an empty cassette."""
        cassette = Cassette(name="test", version="5.74")

        assert cassette.name == "test"
        assert cassette.version == "5.74"
        assert cassette.interactions == []
        assert cassette.metadata == {}

    def test_add_interaction(self) -> None:
        """Test adding interactions to cassette."""
        cassette = Cassette(name="test", version="5.74")

        request = HTTPRequest(method="POST", url="https://example.org/api")
        response = HTTPResponse(status_code=200, body={"values": []})
        interaction = HTTPInteraction(request=request, response=response)

        cassette.add_interaction(interaction)

        assert len(cassette.interactions) == 1
        assert cassette.interactions[0] is interaction

    def test_find_interaction(self) -> None:
        """Test finding interactions by request."""
        cassette = Cassette(name="test", version="5.74")

        request = HTTPRequest(method="POST", url="https://example.org/api")
        response = HTTPResponse(status_code=200, body={"values": []})
        interaction = HTTPInteraction(request=request, response=response)
        cassette.add_interaction(interaction)

        # Find the interaction
        found = cassette.find_interaction(request)
        assert found is interaction

        # Not found for different request
        other_request = HTTPRequest(method="GET", url="https://example.org/other")
        assert cassette.find_interaction(other_request) is None

    def test_to_dict_and_from_dict(self) -> None:
        """Test cassette serialization round-trip."""
        cassette = Cassette(
            name="test",
            version="5.74",
            metadata={"recorded_at": "2024-01-20"},
        )

        request = HTTPRequest(
            method="POST",
            url="https://example.org/api",
            headers={"Content-Type": "application/json"},
            body={"select": ["id"]},
        )
        response = HTTPResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body={"values": [{"id": 1}]},
        )
        cassette.add_interaction(HTTPInteraction(request=request, response=response))

        # Serialize and deserialize
        data = cassette.to_dict()
        restored = Cassette.from_dict(data)

        assert restored.name == cassette.name
        assert restored.version == cassette.version
        assert restored.metadata == cassette.metadata
        assert len(restored.interactions) == 1

        restored_interaction = restored.interactions[0]
        assert restored_interaction.request.method == "POST"
        assert restored_interaction.request.url == "https://example.org/api"
        assert restored_interaction.response.status_code == 200
        assert restored_interaction.response.body == {"values": [{"id": 1}]}


class TestCassetteStore:
    """Tests for CassetteStore class."""

    @pytest.fixture
    def temp_cassette_dir(self) -> Path:
        """Create temporary cassette directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_cassette_path(self, temp_cassette_dir: Path) -> None:
        """Test cassette path generation."""
        store = CassetteStore(temp_cassette_dir, version="5.74")

        path = store.cassette_path("Contact_get")
        assert path == temp_cassette_dir / "v5.74" / "entities" / "Contact_get.json"

    def test_cassette_path_sanitizes_name(self, temp_cassette_dir: Path) -> None:
        """Test cassette path sanitizes special characters."""
        store = CassetteStore(temp_cassette_dir, version="5.74")

        path = store.cassette_path("Contact/get?id=1")
        assert "Contact_get_id_1" in path.name

    def test_exists_false_when_missing(self, temp_cassette_dir: Path) -> None:
        """Test exists returns False for missing cassette."""
        store = CassetteStore(temp_cassette_dir, version="5.74")
        assert store.exists("NonExistent") is False

    def test_save_and_load(self, temp_cassette_dir: Path) -> None:
        """Test saving and loading cassettes."""
        store = CassetteStore(temp_cassette_dir, version="5.74")

        # Create cassette
        cassette = Cassette(name="TestCassette", version="5.74")
        request = HTTPRequest(method="POST", url="https://example.org/api")
        response = HTTPResponse(status_code=200, body={"values": []})
        cassette.add_interaction(HTTPInteraction(request=request, response=response))

        # Save
        path = store.save(cassette)
        assert path.exists()
        assert store.exists("TestCassette")

        # Load
        loaded = store.load("TestCassette")
        assert loaded.name == "TestCassette"
        assert loaded.version == "5.74"
        assert len(loaded.interactions) == 1

    def test_load_missing_raises(self, temp_cassette_dir: Path) -> None:
        """Test loading missing cassette raises FileNotFoundError."""
        store = CassetteStore(temp_cassette_dir, version="5.74")

        with pytest.raises(FileNotFoundError, match="Cassette not found"):
            store.load("NonExistent")

    def test_list_cassettes(self, temp_cassette_dir: Path) -> None:
        """Test listing available cassettes."""
        store = CassetteStore(temp_cassette_dir, version="5.74")

        # Initially empty
        assert store.list_cassettes() == []

        # Create some cassettes
        for name in ["Contact_get", "Activity_get", "Event_get"]:
            cassette = Cassette(name=name, version="5.74")
            store.save(cassette)

        cassettes = store.list_cassettes()
        assert len(cassettes) == 3
        assert set(cassettes) == {"Contact_get", "Activity_get", "Event_get"}


class TestCassetteRecorder:
    """Tests for CassetteRecorder class."""

    @pytest.fixture
    def temp_cassette_dir(self) -> Path:
        """Create temporary cassette directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def recorder(self, temp_cassette_dir: Path) -> CassetteRecorder:
        """Create a CassetteRecorder instance."""
        store = CassetteStore(temp_cassette_dir, version="5.74")
        return CassetteRecorder(store)

    def test_start_recording(self, recorder: CassetteRecorder) -> None:
        """Test starting a recording session."""
        cassette = recorder.start_recording("test_cassette")

        assert cassette.name == "test_cassette"
        assert cassette.version == "5.74"
        assert "recorded_at" in cassette.metadata

    def test_record_interaction(self, recorder: CassetteRecorder) -> None:
        """Test recording an HTTP interaction."""
        recorder.start_recording("test_cassette")

        # Create mock request/response
        request = httpx.Request(
            method="POST",
            url="https://example.org/api/Contact/get",
            headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
            content=b'{"select": ["id"]}',
        )
        response = httpx.Response(
            status_code=200,
            headers={"Content-Type": "application/json"},
            content=b'{"values": [{"id": 1}]}',
        )

        recorder.record_interaction(request, response)

        # Verify recording
        cassette = recorder._current_cassette
        assert cassette is not None
        assert len(cassette.interactions) == 1

        interaction = cassette.interactions[0]
        assert interaction.request.method == "POST"
        assert interaction.request.url == "https://example.org/api/Contact/get"
        assert interaction.response.status_code == 200

    def test_record_interaction_redacts_sensitive_headers(self, recorder: CassetteRecorder) -> None:
        """Test that sensitive headers are redacted."""
        recorder.start_recording("test_cassette")

        request = httpx.Request(
            method="POST",
            url="https://example.org/api",
            headers={
                "Authorization": "Bearer secret-token",
                "X-Civi-Api-Key": "my-api-key",
                "Content-Type": "application/json",
            },
        )
        response = httpx.Response(status_code=200)

        recorder.record_interaction(request, response)

        cassette = recorder._current_cassette
        assert cassette is not None
        interaction = cassette.interactions[0]

        # Normalize headers to lowercase for comparison (httpx may normalize)
        headers_lower = {k.lower(): v for k, v in interaction.request.headers.items()}

        # Sensitive headers should be redacted
        assert headers_lower.get("authorization") == "[REDACTED]"
        # Content-Type should not be redacted
        assert headers_lower.get("content-type") == "application/json"

    def test_record_interaction_without_start_raises(self, recorder: CassetteRecorder) -> None:
        """Test recording without starting raises RuntimeError."""
        request = httpx.Request(method="POST", url="https://example.org/api")
        response = httpx.Response(status_code=200)

        with pytest.raises(RuntimeError, match="Recording not started"):
            recorder.record_interaction(request, response)

    def test_stop_recording_saves_cassette(self, recorder: CassetteRecorder) -> None:
        """Test stopping recording saves the cassette."""
        recorder.start_recording("test_cassette")

        request = httpx.Request(method="POST", url="https://example.org/api")
        response = httpx.Response(status_code=200, content=b'{"values": []}')
        recorder.record_interaction(request, response)

        cassette = recorder.stop_recording()

        assert cassette is not None
        assert cassette.name == "test_cassette"
        assert recorder._current_cassette is None

        # Verify saved to disk
        assert recorder.store.exists("test_cassette")


class TestCassetteManager:
    """Tests for CassetteManager class."""

    @pytest.fixture
    def temp_cassette_dir(self) -> Path:
        """Create temporary cassette directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_detect_mode_from_env(self, temp_cassette_dir: Path) -> None:
        """Test mode detection from environment."""
        with patch.dict(os.environ, {"CIVI_CASSETTE_MODE": "record"}, clear=False):
            manager = CassetteManager(temp_cassette_dir, civicrm_version="5.74")
            assert manager.mode == CassetteMode.RECORD

    def test_detect_mode_defaults_replay_in_ci(self, temp_cassette_dir: Path) -> None:
        """Test mode defaults to REPLAY in CI environment."""
        with patch.dict(os.environ, {"CI": "true", "CIVI_CASSETTE_MODE": ""}, clear=False):
            manager = CassetteManager(temp_cassette_dir, civicrm_version="5.74")
            assert manager.mode == CassetteMode.REPLAY

    def test_detect_mode_defaults_auto(self, temp_cassette_dir: Path) -> None:
        """Test mode defaults to AUTO outside CI."""
        with patch.dict(os.environ, {"CI": "", "CIVI_CASSETTE_MODE": ""}, clear=False):
            manager = CassetteManager(temp_cassette_dir, civicrm_version="5.74")
            assert manager.mode == CassetteMode.AUTO

    def test_load_or_create_replay_mode(self, temp_cassette_dir: Path) -> None:
        """Test load_or_create in REPLAY mode."""
        manager = CassetteManager(
            temp_cassette_dir,
            civicrm_version="5.74",
            mode=CassetteMode.REPLAY,
        )

        # Should fail when cassette doesn't exist
        with pytest.raises(FileNotFoundError):
            manager.load_or_create("NonExistent")

    def test_load_or_create_record_mode(self, temp_cassette_dir: Path) -> None:
        """Test load_or_create in RECORD mode."""
        manager = CassetteManager(
            temp_cassette_dir,
            civicrm_version="5.74",
            mode=CassetteMode.RECORD,
        )

        # Should create new cassette
        cassette = manager.load_or_create("NewCassette")
        assert cassette.name == "NewCassette"
        assert len(cassette.interactions) == 0

    def test_load_or_create_auto_mode_creates_when_missing(self, temp_cassette_dir: Path) -> None:
        """Test load_or_create in AUTO mode creates when missing."""
        manager = CassetteManager(
            temp_cassette_dir,
            civicrm_version="5.74",
            mode=CassetteMode.AUTO,
        )

        cassette = manager.load_or_create("NewCassette")
        assert cassette.name == "NewCassette"

    def test_load_or_create_auto_mode_loads_when_exists(self, temp_cassette_dir: Path) -> None:
        """Test load_or_create in AUTO mode loads existing cassette."""
        manager = CassetteManager(
            temp_cassette_dir,
            civicrm_version="5.74",
            mode=CassetteMode.AUTO,
        )

        # Pre-create cassette
        cassette = Cassette(name="ExistingCassette", version="5.74")
        request = HTTPRequest(method="POST", url="https://example.org/api")
        response = HTTPResponse(status_code=200, body={"values": []})
        cassette.add_interaction(HTTPInteraction(request=request, response=response))
        manager.store.save(cassette)

        # Should load existing
        loaded = manager.load_or_create("ExistingCassette")
        assert len(loaded.interactions) == 1

    def test_configure_mock(
        self,
        temp_cassette_dir: Path,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test configuring respx mock with cassette data."""
        manager = CassetteManager(
            temp_cassette_dir,
            civicrm_version="5.74",
            mode=CassetteMode.REPLAY,
        )

        # Create cassette with interaction
        cassette = Cassette(name="test", version="5.74")
        request = HTTPRequest(
            method="POST",
            url="https://example.org/civicrm/ajax/api4/Contact/get",
        )
        response = HTTPResponse(
            status_code=200,
            body={"values": [{"id": 1}], "count": 1},
        )
        cassette.add_interaction(HTTPInteraction(request=request, response=response))

        # Configure mock
        manager.configure_mock(respx_mock, cassette)

        # Verify mock is configured
        assert len(respx_mock.routes) > 0


class TestGetCassetteManager:
    """Tests for get_cassette_manager factory function."""

    def test_default_directory(self) -> None:
        """Test factory uses default directory."""
        manager = get_cassette_manager()
        assert "cassettes" in str(manager.cassette_dir)

    def test_custom_directory(self) -> None:
        """Test factory accepts custom directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = get_cassette_manager(cassette_dir=tmpdir)
            assert manager.cassette_dir == Path(tmpdir)

    def test_version_from_env(self) -> None:
        """Test factory reads version from environment."""
        with patch.dict(os.environ, {"CIVI_VERSION": "5.80"}, clear=False):
            manager = get_cassette_manager()
            assert manager.civicrm_version == "5.80"


class TestCassetteIntegration:
    """Integration tests for cassette system."""

    @pytest.fixture
    def temp_cassette_dir(self) -> Path:
        """Create temporary cassette directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.mark.compat
    async def test_record_and_replay_workflow(
        self,
        temp_cassette_dir: Path,
        respx_mock: respx.MockRouter,
    ) -> None:
        """Test complete record and replay workflow."""
        # Phase 1: Record
        record_manager = CassetteManager(
            temp_cassette_dir,
            civicrm_version="5.74",
            mode=CassetteMode.RECORD,
        )

        cassette = record_manager.recorder.start_recording("IntegrationTest")

        # Simulate recording an interaction
        request = httpx.Request(
            method="POST",
            url="https://example.org/civicrm/ajax/api4/Contact/get",
            content=b'{"params": {"select": ["id"]}}',
        )
        response = httpx.Response(
            status_code=200,
            content=b'{"values": [{"id": 42}], "count": 1}',
        )
        record_manager.recorder.record_interaction(request, response)
        record_manager.recorder.stop_recording()

        # Verify cassette was saved
        assert record_manager.store.exists("IntegrationTest")

        # Phase 2: Replay
        replay_manager = CassetteManager(
            temp_cassette_dir,
            civicrm_version="5.74",
            mode=CassetteMode.REPLAY,
        )

        loaded_cassette = replay_manager.load_or_create("IntegrationTest")
        assert len(loaded_cassette.interactions) == 1

        # Configure mock and verify
        replay_manager.configure_mock(respx_mock, loaded_cassette)
        assert len(respx_mock.routes) > 0

    @pytest.mark.compat
    def test_cassette_file_format(self, temp_cassette_dir: Path) -> None:
        """Test cassette JSON format is correct."""
        store = CassetteStore(temp_cassette_dir, version="5.74")

        cassette = Cassette(
            name="FormatTest",
            version="5.74",
            metadata={"description": "Format test"},
        )
        request = HTTPRequest(
            method="POST",
            url="https://example.org/api",
            headers={"Content-Type": "application/json"},
            body={"key": "value"},
        )
        response = HTTPResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body={"result": "success"},
        )
        cassette.add_interaction(HTTPInteraction(request=request, response=response))

        path = store.save(cassette)

        # Verify JSON structure
        with path.open() as f:
            data = json.load(f)

        assert data["name"] == "FormatTest"
        assert data["version"] == "5.74"
        assert "metadata" in data
        assert "interactions" in data
        assert len(data["interactions"]) == 1

        interaction = data["interactions"][0]
        assert "request" in interaction
        assert "response" in interaction
        assert "recorded_at" in interaction

    @pytest.mark.compat
    def test_version_isolation(self, temp_cassette_dir: Path) -> None:
        """Test cassettes are isolated by version."""
        store_574 = CassetteStore(temp_cassette_dir, version="5.74")
        store_575 = CassetteStore(temp_cassette_dir, version="5.75")

        # Create cassette in 5.74
        cassette_574 = Cassette(name="VersionTest", version="5.74")
        store_574.save(cassette_574)

        # 5.74 should have it, 5.75 should not
        assert store_574.exists("VersionTest")
        assert not store_575.exists("VersionTest")

        # Create different cassette in 5.75
        cassette_575 = Cassette(name="VersionTest", version="5.75")
        request = HTTPRequest(method="POST", url="https://example.org/api")
        response = HTTPResponse(status_code=200, body={"different": "response"})
        cassette_575.add_interaction(HTTPInteraction(request=request, response=response))
        store_575.save(cassette_575)

        # Both should exist now with different content
        assert store_574.exists("VersionTest")
        assert store_575.exists("VersionTest")

        loaded_574 = store_574.load("VersionTest")
        loaded_575 = store_575.load("VersionTest")

        assert len(loaded_574.interactions) == 0
        assert len(loaded_575.interactions) == 1
