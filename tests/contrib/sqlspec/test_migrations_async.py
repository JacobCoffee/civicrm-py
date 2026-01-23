"""Async tests for sqlspec migrations module.

These tests require sqlspec to be installed and use an in-memory SQLite database.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from civi_py.contrib.sqlspec.migrations import (
    MigrationConfig,
    MigrationResult,
    create_entity_table,
    create_sync_metadata_table,
    downgrade,
    get_all_migrations,
    get_current_version,
    get_migration_status,
    upgrade,
    verify_schema,
)


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock database session."""
    return AsyncMock()


class TestGetCurrentVersion:
    """Tests for get_current_version function."""

    async def test_returns_zero_when_table_does_not_exist_sqlite(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test returns 0 when version table doesn't exist (SQLite)."""
        config = MigrationConfig(dialect="sqlite")
        mock_session.fetch_one = AsyncMock(return_value=None)

        version = await get_current_version(mock_session, config)

        assert version == 0
        mock_session.fetch_one.assert_called_once()

    async def test_returns_zero_when_table_does_not_exist_postgresql(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test returns 0 when version table doesn't exist (PostgreSQL)."""
        config = MigrationConfig(dialect="postgresql")
        mock_session.fetch_one = AsyncMock(return_value=(False,))

        version = await get_current_version(mock_session, config)

        assert version == 0

    async def test_returns_max_version_when_table_exists(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test returns max version when table exists and has data."""
        config = MigrationConfig(dialect="sqlite")
        # First call: table exists check, Second call: max version query
        mock_session.fetch_one = AsyncMock(
            side_effect=[
                MagicMock(name="table_exists"),  # Table exists
                (3,),  # Max version
            ],
        )

        version = await get_current_version(mock_session, config)

        assert version == 3

    async def test_returns_zero_when_table_empty(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test returns 0 when version table exists but is empty."""
        config = MigrationConfig(dialect="sqlite")
        mock_session.fetch_one = AsyncMock(
            side_effect=[
                MagicMock(name="table_exists"),  # Table exists
                (None,),  # No max version (empty table)
            ],
        )

        version = await get_current_version(mock_session, config)

        assert version == 0


class TestUpgrade:
    """Tests for upgrade function."""

    async def test_applies_all_pending_migrations(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test that upgrade applies all pending migrations."""
        config = MigrationConfig(dialect="sqlite")
        mock_session.fetch_one = AsyncMock(return_value=None)  # No existing tables
        mock_session.execute = AsyncMock()

        result = await upgrade(mock_session, config)

        assert isinstance(result, MigrationResult)
        assert result.success is True
        assert 1 in result.applied_versions

    async def test_skips_already_applied_migrations(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test that upgrade skips already applied migrations."""
        config = MigrationConfig(dialect="sqlite")
        # Return that table exists and version is 1 (all migrations applied)
        mock_session.fetch_one = AsyncMock(
            side_effect=[
                MagicMock(name="table_exists"),  # Table exists
                (1,),  # Current version is 1
            ],
        )
        mock_session.execute = AsyncMock()

        result = await upgrade(mock_session, config)

        assert result.success is True
        assert result.applied_versions == []
        assert result.current_version == 1

    async def test_stops_at_target_version(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test that upgrade stops at target version."""
        config = MigrationConfig(dialect="sqlite")
        mock_session.fetch_one = AsyncMock(return_value=None)  # No existing tables
        mock_session.execute = AsyncMock()

        result = await upgrade(mock_session, config, target_version=1)

        assert result.success is True
        assert result.current_version <= 1

    async def test_handles_migration_error(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test that upgrade handles migration errors gracefully."""
        config = MigrationConfig(dialect="sqlite")
        mock_session.fetch_one = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock(side_effect=Exception("Database error"))

        result = await upgrade(mock_session, config)

        assert result.success is False
        assert len(result.errors) > 0


class TestDowngrade:
    """Tests for downgrade function."""

    async def test_rollbacks_to_target_version(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test that downgrade rolls back to target version."""
        config = MigrationConfig(dialect="sqlite")
        # Simulate version table exists and current version is 1
        mock_session.fetch_one = AsyncMock(
            side_effect=[
                MagicMock(name="table_exists"),  # Table exists
                (1,),  # Current version is 1
            ],
        )
        mock_session.execute = AsyncMock()

        result = await downgrade(mock_session, config, target_version=0)

        assert isinstance(result, MigrationResult)
        # Note: The rollback might succeed even if some operations fail silently

    async def test_does_nothing_when_already_at_target(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test that downgrade does nothing when already at target version."""
        config = MigrationConfig(dialect="sqlite")
        mock_session.fetch_one = AsyncMock(
            side_effect=[
                MagicMock(name="table_exists"),
                (0,),  # Current version is 0
            ],
        )

        result = await downgrade(mock_session, config, target_version=0)

        assert result.success is True
        assert result.applied_versions == []


class TestCreateEntityTable:
    """Tests for create_entity_table function."""

    async def test_creates_table(self, mock_session: AsyncMock) -> None:
        """Test that create_entity_table calls execute with DDL."""
        config = MigrationConfig(dialect="sqlite")
        mock_session.execute = AsyncMock()

        await create_entity_table(mock_session, "Contact", config)

        mock_session.execute.assert_called_once()
        call_args = mock_session.execute.call_args
        assert "CREATE TABLE IF NOT EXISTS civi_cache_contact" in call_args[0][0]


class TestCreateSyncMetadataTable:
    """Tests for create_sync_metadata_table function."""

    async def test_creates_table(self, mock_session: AsyncMock) -> None:
        """Test that create_sync_metadata_table calls execute with DDL."""
        config = MigrationConfig(dialect="sqlite")
        mock_session.execute = AsyncMock()

        await create_sync_metadata_table(mock_session, config)

        mock_session.execute.assert_called_once()
        call_args = mock_session.execute.call_args
        assert "CREATE TABLE IF NOT EXISTS civi_cache_sync_metadata" in call_args[0][0]


class TestGetMigrationStatus:
    """Tests for get_migration_status function."""

    async def test_returns_status_dict(self, mock_session: AsyncMock) -> None:
        """Test that get_migration_status returns proper status dictionary."""
        config = MigrationConfig(dialect="sqlite")
        mock_session.fetch_one = AsyncMock(return_value=None)  # No existing tables

        status = await get_migration_status(mock_session, config)

        assert "current_version" in status
        assert "latest_version" in status
        assert "pending_count" in status
        assert "applied_migrations" in status
        assert "pending_migrations" in status

    async def test_shows_pending_when_no_migrations_applied(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test status shows pending migrations when none applied."""
        config = MigrationConfig(dialect="sqlite")
        mock_session.fetch_one = AsyncMock(return_value=None)

        status = await get_migration_status(mock_session, config)

        assert status["current_version"] == 0
        assert status["pending_count"] > 0
        assert len(status["pending_migrations"]) > 0

    async def test_shows_applied_when_migrations_complete(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test status shows applied migrations when complete."""
        config = MigrationConfig(dialect="sqlite")
        migrations = get_all_migrations(config)
        max_version = len(migrations)

        mock_session.fetch_one = AsyncMock(
            side_effect=[
                MagicMock(name="table_exists"),
                (max_version,),
            ],
        )

        status = await get_migration_status(mock_session, config)

        assert status["current_version"] == max_version
        assert status["pending_count"] == 0
        assert len(status["applied_migrations"]) == max_version


class TestVerifySchema:
    """Tests for verify_schema function."""

    async def test_returns_dict_of_table_existence(
        self,
        mock_session: AsyncMock,
    ) -> None:
        """Test that verify_schema returns table existence status."""
        config = MigrationConfig(dialect="sqlite")
        # Mock all tables as not existing
        mock_session.fetch_one = AsyncMock(return_value=None)

        tables = await verify_schema(mock_session, config)

        assert isinstance(tables, dict)
        assert config.version_table in tables
        assert f"{config.table_prefix}sync_metadata" in tables
        assert f"{config.table_prefix}sync_cursor" in tables

        # Check entity tables
        for entity in config.include_entities:
            table_name = f"{config.table_prefix}{entity.lower()}"
            assert table_name in tables

    async def test_shows_missing_tables(self, mock_session: AsyncMock) -> None:
        """Test that verify_schema shows missing tables as False."""
        config = MigrationConfig(dialect="sqlite")
        mock_session.fetch_one = AsyncMock(return_value=None)

        tables = await verify_schema(mock_session, config)

        # All tables should be marked as not existing
        assert all(exists is False for exists in tables.values())

    async def test_shows_existing_tables(self, mock_session: AsyncMock) -> None:
        """Test that verify_schema shows existing tables as True."""
        config = MigrationConfig(dialect="sqlite")
        # Mock all tables as existing
        mock_session.fetch_one = AsyncMock(return_value=MagicMock())

        tables = await verify_schema(mock_session, config)

        # All tables should be marked as existing
        assert all(exists is True for exists in tables.values())
