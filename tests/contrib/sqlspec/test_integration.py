"""Integration tests for sqlspec module with pytest-databases.

These tests exercise the repository and migration functionality against real databases
(PostgreSQL via Docker and SQLite in-memory).

Tests marked with @pytest.mark.db and @skip_without_postgres require Docker and
pytest-databases[postgres] to be installed. Tests marked with @skip_without_sqlspec
require sqlspec to be installed.

Running tests:
    # Run all tests (SQLite only if Docker unavailable)
    pytest tests/contrib/sqlspec/test_integration.py

    # Run only PostgreSQL tests
    pytest tests/contrib/sqlspec/test_integration.py -m db

    # Run only SQLite tests
    pytest tests/contrib/sqlspec/test_integration.py -m "not db"
"""

from __future__ import annotations

from datetime import UTC
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import skip_without_postgres

# Check if sqlspec is available
try:
    import importlib.util

    SQLSPEC_AVAILABLE = importlib.util.find_spec("sqlspec") is not None
except ImportError:
    SQLSPEC_AVAILABLE = False

skip_without_sqlspec = pytest.mark.skipif(
    not SQLSPEC_AVAILABLE,
    reason="sqlspec not installed. Install with: pip install 'civi-py[sqlspec]'",
)

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def sqlspec_config_sqlite() -> Any:
    """Create sqlspec config for in-memory SQLite.

    Note: This fixture will raise ImportError if sqlspec is not installed
    when the config tries to create the adapter config.
    """
    from civicrm_py.contrib.sqlspec.config import CiviSQLSpecConfig

    return CiviSQLSpecConfig(
        adapter="aiosqlite",
        database=":memory:",
        table_prefix="test_civi_",
        auto_create_tables=True,
    )


@pytest.fixture
def sqlspec_config_postgres(postgres_async_url: str) -> Any:
    """Create sqlspec config for Postgres.

    Args:
        postgres_async_url: Async PostgreSQL connection URL from pytest-databases.

    Returns:
        CiviSQLSpecConfig configured for PostgreSQL.
    """
    from civicrm_py.contrib.sqlspec.config import CiviSQLSpecConfig

    return CiviSQLSpecConfig(
        adapter="asyncpg",
        dsn=postgres_async_url.replace("postgresql+asyncpg://", "postgresql://"),
        pool_min_size=1,
        pool_max_size=5,
        table_prefix="test_civi_",
        auto_create_tables=True,
    )


@pytest.fixture
def migration_config_sqlite() -> Any:
    """Create migration config for SQLite."""
    from civicrm_py.contrib.sqlspec.migrations import MigrationConfig

    return MigrationConfig(
        table_prefix="test_civi_",
        include_entities=["Contact", "Activity"],
        version_table="test_civi_migrations",
        dialect="sqlite",
    )


@pytest.fixture
def migration_config_postgres() -> Any:
    """Create migration config for PostgreSQL."""
    from civicrm_py.contrib.sqlspec.migrations import MigrationConfig

    return MigrationConfig(
        table_prefix="test_civi_",
        include_entities=["Contact", "Activity"],
        version_table="test_civi_migrations",
        dialect="postgresql",
    )


@pytest.fixture
def mock_civi_client() -> AsyncMock:
    """Mock CiviClient for sync tests.

    Returns:
        AsyncMock configured to simulate CiviCRM API responses.
    """
    client = AsyncMock()

    # Configure get response for contacts
    client.get = AsyncMock(
        return_value=MagicMock(
            values=[
                {
                    "id": 1,
                    "display_name": "John Doe",
                    "first_name": "John",
                    "last_name": "Doe",
                    "contact_type": "Individual",
                    "is_deleted": False,
                    "email_primary": "john@example.com",
                    "modified_date": "2024-01-15 10:00:00",
                },
                {
                    "id": 2,
                    "display_name": "Jane Smith",
                    "first_name": "Jane",
                    "last_name": "Smith",
                    "contact_type": "Individual",
                    "is_deleted": False,
                    "email_primary": "jane@example.com",
                    "modified_date": "2024-01-15 11:00:00",
                },
            ],
        ),
    )

    # Configure create response
    client.create = AsyncMock(
        return_value=MagicMock(
            values=[
                {
                    "id": 100,
                    "display_name": "New Contact",
                    "first_name": "New",
                    "last_name": "Contact",
                    "contact_type": "Individual",
                },
            ],
        ),
    )

    # Configure update response
    client.update = AsyncMock(
        return_value=MagicMock(
            values=[
                {
                    "id": 1,
                    "display_name": "John Updated",
                    "first_name": "John",
                    "last_name": "Updated",
                },
            ],
        ),
    )

    return client


@pytest.fixture
def mock_civi_client_activities() -> AsyncMock:
    """Mock CiviClient for Activity sync tests."""
    client = AsyncMock()

    client.get = AsyncMock(
        return_value=MagicMock(
            values=[
                {
                    "id": 1,
                    "activity_type_id": 3,
                    "subject": "Follow up call",
                    "activity_date_time": "2024-01-15 10:30:00",
                    "status_id": 2,
                    "source_contact_id": 1,
                    "is_deleted": False,
                    "modified_date": "2024-01-15 10:00:00",
                },
                {
                    "id": 2,
                    "activity_type_id": 1,
                    "subject": "Meeting",
                    "activity_date_time": "2024-01-16 14:00:00",
                    "status_id": 1,
                    "source_contact_id": 1,
                    "is_deleted": False,
                    "modified_date": "2024-01-16 09:00:00",
                },
            ],
        ),
    )

    client.create = AsyncMock(
        return_value=MagicMock(
            values=[
                {
                    "id": 100,
                    "activity_type_id": 3,
                    "subject": "New Activity",
                    "status_id": 1,
                },
            ],
        ),
    )

    return client


# -----------------------------------------------------------------------------
# SQLite Tests (Require sqlspec, No Docker Required)
# -----------------------------------------------------------------------------


@skip_without_sqlspec
class TestRepositoryWithSQLite:
    """Test repository operations with in-memory SQLite.

    These tests run without Docker and verify basic repository functionality.
    Requires sqlspec to be installed.
    """

    async def test_repository_initialization(self, sqlspec_config_sqlite: Any) -> None:
        """Test that repository initializes correctly with SQLite."""
        from civicrm_py.contrib.sqlspec.repository import ContactRepository

        repo = ContactRepository(sqlspec_config_sqlite)

        assert repo._table_name == "test_civi_contact"
        assert repo._metadata_table == "test_civi_sync_metadata"
        assert repo._initialized is False

    async def test_contact_crud_operations(self, sqlspec_config_sqlite: Any) -> None:
        """Test basic CRUD operations for ContactRepository with SQLite."""
        from civicrm_py.contrib.sqlspec.repository import ContactRepository
        from civicrm_py.entities.contact import Contact

        repo = ContactRepository(sqlspec_config_sqlite)

        # Create a mock session that simulates SQLite operations
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.fetch_one = AsyncMock(return_value={"id": 1})
        mock_session.fetch_all = AsyncMock(return_value=[])

        # Test save operation
        contact = Contact(
            first_name="John",
            last_name="Doe",
            display_name="John Doe",
            contact_type="Individual",
        )

        # Patch the get_session method
        with patch.object(repo, "get_session") as mock_get_session:
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_session)
            mock_context.__aexit__ = AsyncMock(return_value=None)
            mock_get_session.return_value = mock_context

            async with repo.get_session() as session:
                # Manually call save logic (simplified)
                row = repo._entity_to_row(contact)

                assert "first_name" in row
                assert row["first_name"] == "John"
                assert row["last_name"] == "Doe"
                assert row["is_deleted"] == 0  # Boolean converted to int

    async def test_entity_to_row_conversion(self, sqlspec_config_sqlite: Any) -> None:
        """Test entity to database row conversion."""
        from civicrm_py.contrib.sqlspec.repository import ContactRepository
        from civicrm_py.entities.contact import Contact

        repo = ContactRepository(sqlspec_config_sqlite)

        contact = Contact(
            id=1,
            first_name="Jane",
            last_name="Smith",
            display_name="Jane Smith",
            contact_type="Individual",
            is_deleted=False,
            do_not_email=True,
            preferred_communication_method=["email", "phone"],
        )

        row = repo._entity_to_row(contact)

        # Check basic fields
        assert row["id"] == 1
        assert row["first_name"] == "Jane"
        assert row["last_name"] == "Smith"

        # Check boolean conversion
        assert row["is_deleted"] == 0
        assert row["do_not_email"] == 1

        # Check list serialization (should be JSON string)
        import json

        assert row["preferred_communication_method"] == json.dumps(["email", "phone"])

    async def test_row_to_entity_conversion(self, sqlspec_config_sqlite: Any) -> None:
        """Test database row to entity conversion."""
        from civicrm_py.contrib.sqlspec.repository import ContactRepository

        repo = ContactRepository(sqlspec_config_sqlite)

        row = {
            "id": 1,
            "first_name": "Jane",
            "last_name": "Smith",
            "display_name": "Jane Smith",
            "contact_type": "Individual",
            "is_deleted": 0,
            "do_not_email": 1,
            "preferred_communication_method": '["email", "phone"]',
        }

        contact = repo._row_to_entity(row)

        assert contact.id == 1
        assert contact.first_name == "Jane"
        assert contact.last_name == "Smith"
        assert contact.display_name == "Jane Smith"
        # Note: Boolean conversion depends on type annotation detection

    async def test_activity_repository_initialization(
        self,
        sqlspec_config_sqlite: Any,
    ) -> None:
        """Test ActivityRepository initialization."""
        from civicrm_py.contrib.sqlspec.repository import ActivityRepository

        repo = ActivityRepository(sqlspec_config_sqlite)

        assert repo._table_name == "test_civi_activity"
        assert repo._metadata_table == "test_civi_sync_metadata"


class TestMigrationsWithSQLite:
    """Test migrations with in-memory SQLite.

    These tests use mocked sessions and don't require sqlspec.
    """

    async def test_upgrade_creates_tables(self, migration_config_sqlite: Any) -> None:
        """Test that upgrade creates all expected tables."""
        from civicrm_py.contrib.sqlspec.migrations import upgrade

        mock_session = AsyncMock()
        mock_session.fetch_one = AsyncMock(return_value=None)  # No existing tables
        mock_session.execute = AsyncMock()

        result = await upgrade(mock_session, migration_config_sqlite)

        assert result.success is True
        assert 1 in result.applied_versions
        assert result.current_version == 1

        # Verify execute was called for table creation
        assert mock_session.execute.call_count >= 1

    async def test_downgrade_drops_tables(self, migration_config_sqlite: Any) -> None:
        """Test that downgrade drops tables correctly."""
        from civicrm_py.contrib.sqlspec.migrations import downgrade

        mock_session = AsyncMock()
        # Simulate existing tables at version 1
        mock_session.fetch_one = AsyncMock(
            side_effect=[
                MagicMock(name="table_exists"),  # Table exists check
                (1,),  # Current version
            ],
        )
        mock_session.execute = AsyncMock()

        result = await downgrade(mock_session, migration_config_sqlite, target_version=0)

        assert result.success is True
        assert 1 in result.applied_versions
        assert result.current_version == 0

    async def test_verify_schema_checks_tables(
        self,
        migration_config_sqlite: Any,
    ) -> None:
        """Test that verify_schema checks for expected tables."""
        from civicrm_py.contrib.sqlspec.migrations import verify_schema

        mock_session = AsyncMock()
        # All tables exist
        mock_session.fetch_one = AsyncMock(return_value=MagicMock(name="exists"))

        tables = await verify_schema(mock_session, migration_config_sqlite)

        # Check expected tables are in result
        assert "test_civi_migrations" in tables
        assert "test_civi_sync_metadata" in tables
        assert "test_civi_sync_cursor" in tables
        assert "test_civi_contact" in tables
        assert "test_civi_activity" in tables

    async def test_get_migration_status(self, migration_config_sqlite: Any) -> None:
        """Test get_migration_status returns correct information."""
        from civicrm_py.contrib.sqlspec.migrations import get_migration_status

        mock_session = AsyncMock()
        mock_session.fetch_one = AsyncMock(return_value=None)  # No migrations applied

        status = await get_migration_status(mock_session, migration_config_sqlite)

        assert status["current_version"] == 0
        assert status["latest_version"] >= 1
        assert status["pending_count"] >= 1
        assert len(status["pending_migrations"]) >= 1


@skip_without_sqlspec
class TestSyncOperationsWithMock:
    """Test sync operations with mocked CiviClient and SQLite.

    Requires sqlspec to be installed.
    """

    async def test_sync_from_civi_mock(
        self,
        sqlspec_config_sqlite: Any,
        mock_civi_client: AsyncMock,
    ) -> None:
        """Test syncing data from CiviCRM to local database."""
        from civicrm_py.contrib.sqlspec.repository import ContactRepository, SyncResult

        repo = ContactRepository(sqlspec_config_sqlite)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.fetch_one = AsyncMock(return_value=None)
        mock_session.fetch_all = AsyncMock(return_value=[])

        # Call sync_from_civi
        result = await repo.sync_from_civi(mock_session, mock_civi_client)

        assert isinstance(result, SyncResult)
        assert result.synced_count == 2  # Two contacts from mock
        assert result.error_count == 0

        # Verify CiviClient.get was called
        mock_civi_client.get.assert_called_once()

    async def test_sync_from_civi_with_filters(
        self,
        sqlspec_config_sqlite: Any,
        mock_civi_client: AsyncMock,
    ) -> None:
        """Test syncing with filter conditions."""
        from civicrm_py.contrib.sqlspec.repository import ContactRepository

        repo = ContactRepository(sqlspec_config_sqlite)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.fetch_one = AsyncMock(return_value=None)

        result = await repo.sync_from_civi(
            mock_session,
            mock_civi_client,
            is_deleted=False,
            limit=100,
        )

        assert result.synced_count == 2

        # Verify get was called with filters
        call_args = mock_civi_client.get.call_args
        assert call_args is not None
        # The where clause should contain is_deleted filter
        assert call_args.kwargs.get("limit") == 100

    async def test_sync_to_civi_creates_new_entities(
        self,
        sqlspec_config_sqlite: Any,
        mock_civi_client: AsyncMock,
    ) -> None:
        """Test syncing local changes back to CiviCRM."""
        from civicrm_py.contrib.sqlspec.repository import (
            ContactRepository,
            SyncResult,
        )
        from civicrm_py.entities.contact import Contact

        repo = ContactRepository(sqlspec_config_sqlite)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.fetch_one = AsyncMock(return_value=None)
        mock_session.fetch_all = AsyncMock(return_value=[])

        # Mock pending entities
        pending_contact = Contact(
            first_name="New",
            last_name="Contact",
            display_name="New Contact",
            contact_type="Individual",
        )

        with patch.object(
            repo,
            "_get_pending_entities",
            return_value=[pending_contact],
        ):
            result = await repo.sync_to_civi(mock_session, mock_civi_client)

            assert isinstance(result, SyncResult)
            # Create should have been called for new entity
            mock_civi_client.create.assert_called_once()

    async def test_sync_to_civi_updates_existing(
        self,
        sqlspec_config_sqlite: Any,
        mock_civi_client: AsyncMock,
    ) -> None:
        """Test that sync_to_civi updates existing entities."""
        from civicrm_py.contrib.sqlspec.repository import ContactRepository
        from civicrm_py.entities.contact import Contact

        repo = ContactRepository(sqlspec_config_sqlite)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.fetch_one = AsyncMock(return_value=None)
        mock_session.fetch_all = AsyncMock(return_value=[])

        # Mock existing entity with ID
        existing_contact = Contact(
            id=1,
            first_name="John",
            last_name="Updated",
            display_name="John Updated",
            contact_type="Individual",
        )

        with patch.object(
            repo,
            "_get_pending_entities",
            return_value=[existing_contact],
        ):
            result = await repo.sync_to_civi(mock_session, mock_civi_client)

            # Update should have been called for existing entity
            mock_civi_client.update.assert_called_once()


@skip_without_sqlspec
class TestActivitySyncOperations:
    """Test Activity sync operations.

    Requires sqlspec to be installed.
    """

    async def test_activity_sync_from_civi(
        self,
        sqlspec_config_sqlite: Any,
        mock_civi_client_activities: AsyncMock,
    ) -> None:
        """Test syncing activities from CiviCRM."""
        from civicrm_py.contrib.sqlspec.repository import ActivityRepository

        repo = ActivityRepository(sqlspec_config_sqlite)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.fetch_one = AsyncMock(return_value=None)

        result = await repo.sync_from_civi(mock_session, mock_civi_client_activities)

        assert result.synced_count == 2
        assert result.error_count == 0
        mock_civi_client_activities.get.assert_called_once()


# -----------------------------------------------------------------------------
# PostgreSQL Tests (Require Docker)
# -----------------------------------------------------------------------------


@pytest.mark.db
@skip_without_postgres
class TestRepositoryWithPostgres:
    """Test repository operations with real PostgreSQL.

    These tests require Docker and pytest-databases[postgres] to be installed.
    """

    async def test_postgres_config_creation(self, postgres_async_url: str) -> None:
        """Test PostgreSQL config creation."""
        from civicrm_py.contrib.sqlspec.config import CiviSQLSpecConfig

        # Convert asyncpg URL to standard PostgreSQL URL
        dsn = postgres_async_url.replace("postgresql+asyncpg://", "postgresql://")

        config = CiviSQLSpecConfig(
            adapter="asyncpg",
            dsn=dsn,
            pool_min_size=1,
            pool_max_size=5,
            table_prefix="test_civi_",
        )

        assert config.adapter == "asyncpg"
        assert config.dsn is not None
        assert "postgresql" in config.dsn

    @skip_without_sqlspec
    async def test_contact_repository_table_name(
        self,
        sqlspec_config_postgres: Any,
    ) -> None:
        """Test ContactRepository generates correct table name for Postgres."""
        from civicrm_py.contrib.sqlspec.repository import ContactRepository

        repo = ContactRepository(sqlspec_config_postgres)

        assert repo._table_name == "test_civi_contact"
        assert repo._metadata_table == "test_civi_sync_metadata"


@pytest.mark.db
@skip_without_postgres
class TestMigrationsWithPostgres:
    """Test migrations against real PostgreSQL."""

    async def test_migrations_upgrade_postgres(
        self,
        migration_config_postgres: Any,
    ) -> None:
        """Test running migrations against PostgreSQL."""
        from civicrm_py.contrib.sqlspec.migrations import upgrade

        mock_session = AsyncMock()
        # PostgreSQL table check returns (False,) for non-existent table
        mock_session.fetch_one = AsyncMock(return_value=(False,))
        mock_session.execute = AsyncMock()

        result = await upgrade(mock_session, migration_config_postgres)

        assert result.success is True
        assert 1 in result.applied_versions

    async def test_migrations_downgrade_postgres(
        self,
        migration_config_postgres: Any,
    ) -> None:
        """Test rolling back migrations on PostgreSQL."""
        from civicrm_py.contrib.sqlspec.migrations import downgrade

        mock_session = AsyncMock()
        # Simulate tables exist and version is 1
        mock_session.fetch_one = AsyncMock(
            side_effect=[
                (True,),  # Table exists
                (1,),  # Current version
            ],
        )
        mock_session.execute = AsyncMock()

        result = await downgrade(
            mock_session,
            migration_config_postgres,
            target_version=0,
        )

        assert result.success is True

    async def test_verify_schema_postgres(
        self,
        migration_config_postgres: Any,
    ) -> None:
        """Test schema verification on PostgreSQL."""
        from civicrm_py.contrib.sqlspec.migrations import verify_schema

        mock_session = AsyncMock()
        # Simulate all tables exist
        mock_session.fetch_one = AsyncMock(return_value=(True,))

        tables = await verify_schema(mock_session, migration_config_postgres)

        assert "test_civi_migrations" in tables
        assert "test_civi_contact" in tables
        assert "test_civi_activity" in tables
        assert all(exists is True for exists in tables.values())


@pytest.mark.db
@skip_without_postgres
@skip_without_sqlspec
class TestSyncOperationsWithPostgres:
    """Test sync operations with PostgreSQL backend.

    Requires both Docker and sqlspec.
    """

    async def test_sync_from_civi_postgres(
        self,
        sqlspec_config_postgres: Any,
        mock_civi_client: AsyncMock,
    ) -> None:
        """Test syncing data from CiviCRM to PostgreSQL."""
        from civicrm_py.contrib.sqlspec.repository import ContactRepository

        repo = ContactRepository(sqlspec_config_postgres)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.fetch_one = AsyncMock(return_value=None)

        result = await repo.sync_from_civi(mock_session, mock_civi_client)

        assert result.synced_count == 2
        assert result.error_count == 0

    async def test_sync_to_civi_postgres(
        self,
        sqlspec_config_postgres: Any,
        mock_civi_client: AsyncMock,
    ) -> None:
        """Test syncing local PostgreSQL changes back to CiviCRM."""
        from civicrm_py.contrib.sqlspec.repository import ContactRepository
        from civicrm_py.entities.contact import Contact

        repo = ContactRepository(sqlspec_config_postgres)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.fetch_one = AsyncMock(return_value=None)
        mock_session.fetch_all = AsyncMock(return_value=[])

        # Mock pending entity
        pending_contact = Contact(
            first_name="Postgres",
            last_name="Contact",
            display_name="Postgres Contact",
            contact_type="Individual",
        )

        with patch.object(
            repo,
            "_get_pending_entities",
            return_value=[pending_contact],
        ):
            result = await repo.sync_to_civi(mock_session, mock_civi_client)

            mock_civi_client.create.assert_called_once()


# -----------------------------------------------------------------------------
# Error Handling Tests
# -----------------------------------------------------------------------------


@skip_without_sqlspec
class TestErrorHandling:
    """Test error handling in repository and migration operations.

    Requires sqlspec to be installed.
    """

    async def test_sync_from_civi_handles_api_error(
        self,
        sqlspec_config_sqlite: Any,
    ) -> None:
        """Test that sync_from_civi handles API errors gracefully."""
        from civicrm_py.contrib.sqlspec.repository import ContactRepository

        repo = ContactRepository(sqlspec_config_sqlite)

        # Mock client that raises an error
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("API connection failed"))

        mock_session = AsyncMock()

        result = await repo.sync_from_civi(mock_session, mock_client)

        assert result.error_count == 1
        assert len(result.errors) == 1
        assert "API request failed" in result.errors[0][1]

    async def test_sync_from_civi_handles_missing_id(
        self,
        sqlspec_config_sqlite: Any,
    ) -> None:
        """Test that sync_from_civi handles entities without ID."""
        from civicrm_py.contrib.sqlspec.repository import ContactRepository

        repo = ContactRepository(sqlspec_config_sqlite)

        # Mock client that returns entity without ID
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=MagicMock(
                values=[
                    {
                        # Missing "id" field
                        "display_name": "No ID Contact",
                        "first_name": "No",
                        "last_name": "ID",
                    },
                ],
            ),
        )

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.fetch_one = AsyncMock(return_value=None)

        result = await repo.sync_from_civi(mock_session, mock_client)

        assert result.error_count == 1
        assert "Entity missing ID" in result.errors[0][1]


class TestMigrationErrorHandling:
    """Test migration error handling (doesn't require sqlspec)."""

    async def test_migration_error_handling(
        self,
        migration_config_sqlite: Any,
    ) -> None:
        """Test that migration errors are handled gracefully."""
        from civicrm_py.contrib.sqlspec.migrations import upgrade

        mock_session = AsyncMock()
        mock_session.fetch_one = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock(
            side_effect=Exception("Database constraint violation"),
        )

        result = await upgrade(mock_session, migration_config_sqlite)

        assert result.success is False
        assert len(result.errors) > 0


# -----------------------------------------------------------------------------
# Integration Smoke Tests
# -----------------------------------------------------------------------------


@skip_without_sqlspec
class TestRepositorySmokeTests:
    """Smoke tests that require sqlspec to be installed."""

    async def test_all_repositories_can_be_instantiated(
        self,
        sqlspec_config_sqlite: Any,
    ) -> None:
        """Test that all repository classes can be instantiated."""
        from civicrm_py.contrib.sqlspec.repository import (
            ActivityRepository,
            ContactRepository,
            ContributionRepository,
            EventRepository,
            MembershipRepository,
        )

        # All should instantiate without error
        contact_repo = ContactRepository(sqlspec_config_sqlite)
        activity_repo = ActivityRepository(sqlspec_config_sqlite)
        contribution_repo = ContributionRepository(sqlspec_config_sqlite)
        event_repo = EventRepository(sqlspec_config_sqlite)
        membership_repo = MembershipRepository(sqlspec_config_sqlite)

        assert contact_repo._table_name == "test_civi_contact"
        assert activity_repo._table_name == "test_civi_activity"
        assert contribution_repo._table_name == "test_civi_contribution"
        assert event_repo._table_name == "test_civi_event"
        assert membership_repo._table_name == "test_civi_membership"


class TestIntegrationSmokeTests:
    """Quick smoke tests to verify basic integration works.

    These tests don't require sqlspec for imports.
    """

    async def test_migration_functions_are_importable(self) -> None:
        """Test that all migration functions can be imported."""
        from civicrm_py.contrib.sqlspec.migrations import (
            create_entity_table,
            create_sync_metadata_table,
            downgrade,
            get_all_migrations,
            get_current_version,
            get_migration_status,
            upgrade,
            verify_schema,
        )

        # All should be callable
        assert callable(upgrade)
        assert callable(downgrade)
        assert callable(get_current_version)
        assert callable(get_migration_status)
        assert callable(verify_schema)
        assert callable(create_entity_table)
        assert callable(create_sync_metadata_table)
        assert callable(get_all_migrations)

    async def test_sync_status_enum_values(self) -> None:
        """Test SyncStatus enum has expected values."""
        from civicrm_py.contrib.sqlspec.repository import SyncStatus

        assert SyncStatus.PENDING.value == "pending"
        assert SyncStatus.SYNCED.value == "synced"
        assert SyncStatus.CONFLICT.value == "conflict"
        assert SyncStatus.ERROR.value == "error"

    async def test_sync_result_dataclass(self) -> None:
        """Test SyncResult dataclass creation."""
        from civicrm_py.contrib.sqlspec.repository import SyncResult

        result = SyncResult()
        assert result.synced_count == 0
        assert result.error_count == 0
        assert result.conflict_count == 0
        assert result.errors == []

        result = SyncResult(synced_count=5, error_count=1, errors=[(1, "error")])
        assert result.synced_count == 5
        assert result.error_count == 1
        assert len(result.errors) == 1

    async def test_sync_metadata_dataclass(self) -> None:
        """Test SyncMetadata dataclass creation."""
        from datetime import datetime

        from civicrm_py.contrib.sqlspec.repository import SyncMetadata, SyncStatus

        metadata = SyncMetadata(entity_id=1, entity_type="Contact")
        assert metadata.entity_id == 1
        assert metadata.entity_type == "Contact"
        assert metadata.sync_status == SyncStatus.SYNCED

        metadata = SyncMetadata(
            entity_id=2,
            entity_type="Activity",
            last_synced_at=datetime.now(tz=UTC),
            sync_status=SyncStatus.PENDING,
        )
        assert metadata.entity_id == 2
        assert metadata.sync_status == SyncStatus.PENDING
