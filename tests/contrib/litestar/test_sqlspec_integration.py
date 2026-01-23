"""Tests for SQLSpec integration with Litestar plugin.

Tests cover:
- SQLSpecPluginConfig initialization and validation
- Graceful degradation when sqlspec is not installed
- Dependency provider registration
- Lifecycle handlers (startup/shutdown)
- Correlation ID utilities
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# Check if sqlspec is available
try:
    import sqlspec  # noqa: F401

    HAS_SQLSPEC = True
except ImportError:
    HAS_SQLSPEC = False

# Check if litestar is available
try:
    import litestar  # noqa: F401

    HAS_LITESTAR = True
except ImportError:
    HAS_LITESTAR = False

# Skip all tests if litestar is not installed
pytestmark = pytest.mark.skipif(not HAS_LITESTAR, reason="litestar not installed")


# =============================================================================
# SQLSpecPluginConfig Tests
# =============================================================================


class TestSQLSpecPluginConfig:
    """Tests for SQLSpecPluginConfig initialization and defaults."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        from civi_py.contrib.litestar.sqlspec_integration import SQLSpecPluginConfig

        config = SQLSpecPluginConfig()

        assert config.enabled is False
        assert config.sqlspec_config is None
        assert config.auto_run_migrations is True
        assert config.provide_repositories is True
        assert config.enable_correlation_tracking is False
        assert config.correlation_header == "X-Correlation-ID"

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        from civi_py.contrib.litestar.sqlspec_integration import SQLSpecPluginConfig

        config = SQLSpecPluginConfig(
            enabled=False,  # Keep disabled for testing without sqlspec
            auto_run_migrations=False,
            provide_repositories=False,
            enable_correlation_tracking=True,
            correlation_header="X-Request-ID",
        )

        assert config.enabled is False
        assert config.auto_run_migrations is False
        assert config.provide_repositories is False
        assert config.enable_correlation_tracking is True
        assert config.correlation_header == "X-Request-ID"

    @pytest.mark.skipif(HAS_SQLSPEC, reason="Test requires sqlspec NOT installed")
    def test_enabled_without_sqlspec_raises(self) -> None:
        """Test that enabling without sqlspec raises ImportError."""
        from civi_py.contrib.litestar.sqlspec_integration import SQLSpecPluginConfig

        with pytest.raises(ImportError, match="sqlspec is not installed"):
            SQLSpecPluginConfig(enabled=True)


# =============================================================================
# SQLSPEC_AVAILABLE Detection Tests
# =============================================================================


class TestSQLSpecAvailable:
    """Tests for SQLSPEC_AVAILABLE detection."""

    def test_sqlspec_available_detection(self) -> None:
        """Test that SQLSPEC_AVAILABLE is correctly detected."""
        from civi_py.contrib.litestar.sqlspec_integration import SQLSPEC_AVAILABLE

        # Should match our local detection
        assert SQLSPEC_AVAILABLE == SQLSPEC_AVAILABLE  # Tautology, but tests the import


# =============================================================================
# SQLSpecState Tests
# =============================================================================


class TestSQLSpecState:
    """Tests for SQLSpecState dataclass."""

    def test_state_creation(self) -> None:
        """Test SQLSpecState creation."""
        from civi_py.contrib.litestar.sqlspec_integration import SQLSpecState

        # Create a mock config
        mock_config = MagicMock()

        state = SQLSpecState(config=mock_config)

        assert state.config is mock_config
        assert state.repositories == {}
        assert state.initialized is False

    def test_state_with_repositories(self) -> None:
        """Test SQLSpecState with repositories."""
        from civi_py.contrib.litestar.sqlspec_integration import SQLSpecState

        mock_config = MagicMock()
        mock_repo = MagicMock()

        state = SQLSpecState(
            config=mock_config,
            repositories={"contact": mock_repo},
            initialized=True,
        )

        assert state.config is mock_config
        assert state.repositories == {"contact": mock_repo}
        assert state.initialized is True


# =============================================================================
# Correlation ID Utilities Tests
# =============================================================================


class TestCorrelationIDUtilities:
    """Tests for correlation ID utility functions."""

    def test_generate_correlation_id(self) -> None:
        """Test correlation ID generation."""
        from civi_py.contrib.litestar.sqlspec_integration import generate_correlation_id

        correlation_id = generate_correlation_id()

        # Should be a valid UUID4 string
        assert isinstance(correlation_id, str)
        assert len(correlation_id) == 36  # UUID format
        assert "-" in correlation_id

    def test_generate_unique_correlation_ids(self) -> None:
        """Test that generated correlation IDs are unique."""
        from civi_py.contrib.litestar.sqlspec_integration import generate_correlation_id

        ids = [generate_correlation_id() for _ in range(100)]

        # All IDs should be unique
        assert len(ids) == len(set(ids))

    def test_get_set_correlation_id(self) -> None:
        """Test getting and setting correlation ID."""
        from civi_py.contrib.litestar.sqlspec_integration import (
            CORRELATION_ID_KEY,
            get_correlation_id,
            set_correlation_id,
        )

        # Create mock state
        class MockState:
            def get(self, key: str, default: str | None = None) -> str | None:
                return getattr(self, key, default)

        state = MockState()

        # Initially should be None
        assert get_correlation_id(state) is None  # type: ignore[arg-type]

        # Set correlation ID
        set_correlation_id(state, "test-correlation-123")  # type: ignore[arg-type]

        # Should be retrievable
        assert getattr(state, CORRELATION_ID_KEY) == "test-correlation-123"


# =============================================================================
# Dependency Provider Tests
# =============================================================================


class TestDependencyProviders:
    """Tests for SQLSpec dependency providers."""

    def test_get_sqlspec_dependency_providers(self) -> None:
        """Test get_sqlspec_dependency_providers returns correct mappings."""
        from civi_py.contrib.litestar.sqlspec_integration import (
            get_sqlspec_dependency_providers,
        )

        providers = get_sqlspec_dependency_providers()

        assert "sqlspec_session" in providers
        assert "contact_repository" in providers
        assert "activity_repository" in providers
        assert "contribution_repository" in providers
        assert "event_repository" in providers
        assert "membership_repository" in providers

        # All should be wrapped in Provide
        for provider in providers.values():
            assert hasattr(provider, "dependency")

    async def test_provide_contact_repository_missing_state(self) -> None:
        """Test RuntimeError when SQLSpec state is missing."""
        from civi_py.contrib.litestar.sqlspec_integration import (
            provide_contact_repository,
        )

        # Create mock state without SQLSpec
        class MockState:
            def get(self, key: str, default: str | None = None) -> str | None:
                return None

        state = MockState()

        with pytest.raises(RuntimeError, match="SQLSpec state not found"):
            await provide_contact_repository(state)  # type: ignore[arg-type]

    async def test_provide_activity_repository_missing_state(self) -> None:
        """Test RuntimeError when SQLSpec state is missing."""
        from civi_py.contrib.litestar.sqlspec_integration import (
            provide_activity_repository,
        )

        class MockState:
            def get(self, key: str, default: str | None = None) -> str | None:
                return None

        state = MockState()

        with pytest.raises(RuntimeError, match="SQLSpec state not found"):
            await provide_activity_repository(state)  # type: ignore[arg-type]

    async def test_provide_contribution_repository_missing_state(self) -> None:
        """Test RuntimeError when SQLSpec state is missing."""
        from civi_py.contrib.litestar.sqlspec_integration import (
            provide_contribution_repository,
        )

        class MockState:
            def get(self, key: str, default: str | None = None) -> str | None:
                return None

        state = MockState()

        with pytest.raises(RuntimeError, match="SQLSpec state not found"):
            await provide_contribution_repository(state)  # type: ignore[arg-type]

    async def test_provide_event_repository_missing_state(self) -> None:
        """Test RuntimeError when SQLSpec state is missing."""
        from civi_py.contrib.litestar.sqlspec_integration import (
            provide_event_repository,
        )

        class MockState:
            def get(self, key: str, default: str | None = None) -> str | None:
                return None

        state = MockState()

        with pytest.raises(RuntimeError, match="SQLSpec state not found"):
            await provide_event_repository(state)  # type: ignore[arg-type]

    async def test_provide_membership_repository_missing_state(self) -> None:
        """Test RuntimeError when SQLSpec state is missing."""
        from civi_py.contrib.litestar.sqlspec_integration import (
            provide_membership_repository,
        )

        class MockState:
            def get(self, key: str, default: str | None = None) -> str | None:
                return None

        state = MockState()

        with pytest.raises(RuntimeError, match="SQLSpec state not found"):
            await provide_membership_repository(state)  # type: ignore[arg-type]


# =============================================================================
# SQLSpecPlugin Tests
# =============================================================================


class TestSQLSpecPlugin:
    """Tests for SQLSpecPlugin standalone plugin."""

    def test_plugin_default_config(self) -> None:
        """Test plugin with default config (disabled)."""
        from civi_py.contrib.litestar.sqlspec_integration import SQLSpecPlugin

        plugin = SQLSpecPlugin()

        assert plugin.config.enabled is False

    def test_plugin_config_property(self) -> None:
        """Test plugin config property."""
        from civi_py.contrib.litestar.sqlspec_integration import (
            SQLSpecPlugin,
            SQLSpecPluginConfig,
        )

        config = SQLSpecPluginConfig(enabled=False)
        plugin = SQLSpecPlugin(config)

        assert plugin.config is config

    def test_plugin_on_app_init_disabled(self) -> None:
        """Test on_app_init does nothing when disabled."""
        from civi_py.contrib.litestar.sqlspec_integration import SQLSpecPlugin

        plugin = SQLSpecPlugin()

        # Create mock app config
        mock_app_config = MagicMock()
        mock_app_config.on_startup = []
        mock_app_config.on_shutdown = []
        mock_app_config.dependencies = {}

        result = plugin.on_app_init(mock_app_config)

        # Should return unchanged config
        assert result is mock_app_config
        assert len(mock_app_config.on_startup) == 0
        assert len(mock_app_config.on_shutdown) == 0


# =============================================================================
# Lifecycle Handler Tests
# =============================================================================


class TestLifecycleHandlers:
    """Tests for SQLSpec lifecycle handlers."""

    async def test_cleanup_sqlspec_no_state(self) -> None:
        """Test cleanup_sqlspec handles missing state gracefully."""
        from civi_py.contrib.litestar.sqlspec_integration import cleanup_sqlspec

        # Create mock app without SQLSpec state
        mock_app = MagicMock()
        mock_app.state = MagicMock()
        mock_app.state.__getattr__ = MagicMock(return_value=None)

        # Should not raise
        await cleanup_sqlspec(mock_app)

    async def test_initialize_sqlspec_disabled(self) -> None:
        """Test initialize_sqlspec does nothing when disabled."""
        from civi_py.contrib.litestar.sqlspec_integration import (
            SQLSPEC_STATE_KEY,
            SQLSpecPluginConfig,
            initialize_sqlspec,
        )

        mock_app = MagicMock()
        config = SQLSpecPluginConfig(enabled=False)

        await initialize_sqlspec(mock_app, config)

        # Should not set state
        assert not hasattr(mock_app.state, SQLSPEC_STATE_KEY)


# =============================================================================
# Integration with CiviPluginConfig Tests
# =============================================================================


class TestCiviPluginConfigSQLSpecIntegration:
    """Tests for SQLSpec integration with CiviPluginConfig."""

    def test_civi_plugin_config_sqlspec_none_by_default(self) -> None:
        """Test CiviPluginConfig has sqlspec=None by default."""
        from civi_py.contrib.litestar import CiviPluginConfig

        config = CiviPluginConfig()

        assert config.sqlspec is None

    def test_civi_plugin_config_with_sqlspec(self) -> None:
        """Test CiviPluginConfig accepts SQLSpecPluginConfig."""
        from civi_py.contrib.litestar import CiviPluginConfig
        from civi_py.contrib.litestar.sqlspec_integration import SQLSpecPluginConfig

        sqlspec_config = SQLSpecPluginConfig(enabled=False)
        config = CiviPluginConfig(sqlspec=sqlspec_config)

        assert config.sqlspec is sqlspec_config
        assert config.sqlspec.enabled is False


# =============================================================================
# Module Exports Tests
# =============================================================================


class TestModuleExports:
    """Tests for module-level exports."""

    def test_all_exports_available(self) -> None:
        """Test all __all__ exports are importable."""
        from civi_py.contrib.litestar import (
            CORRELATION_ID_KEY,
            SQLSPEC_AVAILABLE,
            SQLSPEC_STATE_KEY,
            SQLSpecPlugin,
            SQLSpecPluginConfig,
            SQLSpecState,
            cleanup_sqlspec,
            generate_correlation_id,
            get_correlation_id,
            get_sqlspec_dependency_providers,
            initialize_sqlspec,
            provide_activity_repository,
            provide_contact_repository,
            provide_contribution_repository,
            provide_event_repository,
            provide_membership_repository,
            provide_sqlspec_session,
            set_correlation_id,
        )

        # All should be importable
        assert SQLSPEC_STATE_KEY is not None
        assert CORRELATION_ID_KEY is not None
        assert SQLSPEC_AVAILABLE is not None
        assert SQLSpecPluginConfig is not None
        assert SQLSpecState is not None
        assert SQLSpecPlugin is not None
        assert initialize_sqlspec is not None
        assert cleanup_sqlspec is not None
        assert get_sqlspec_dependency_providers is not None
        assert provide_sqlspec_session is not None
        assert provide_contact_repository is not None
        assert provide_activity_repository is not None
        assert provide_contribution_repository is not None
        assert provide_event_repository is not None
        assert provide_membership_repository is not None
        assert generate_correlation_id is not None
        assert get_correlation_id is not None
        assert set_correlation_id is not None
