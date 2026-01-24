"""Tests for sqlspec migrations module."""

from __future__ import annotations

from civicrm_py.contrib.sqlspec.migrations import (
    DatabaseDialect,
    Migration,
    MigrationConfig,
    MigrationResult,
    _camel_to_snake,
    _get_json_type,
    _get_placeholder,
    _get_serial_type,
    _get_timestamp_type,
    _is_postgresql,
    generate_entity_table_ddl,
    generate_sync_metadata_table_ddl,
    generate_table_ddl,
    generate_version_table_ddl,
    get_all_migrations,
)


class TestMigrationConfig:
    """Tests for MigrationConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = MigrationConfig()

        assert config.table_prefix == "civi_cache_"
        assert config.version_table == "civi_migrations"
        assert config.dialect == "sqlite"
        assert "Contact" in config.include_entities
        assert "Activity" in config.include_entities
        assert "Contribution" in config.include_entities
        assert "Event" in config.include_entities
        assert "Membership" in config.include_entities

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = MigrationConfig(
            table_prefix="app_cache_",
            include_entities=["Contact", "Custom"],
            version_table="app_migrations",
            dialect="postgresql",
        )

        assert config.table_prefix == "app_cache_"
        assert config.include_entities == ["Contact", "Custom"]
        assert config.version_table == "app_migrations"
        assert config.dialect == "postgresql"


class TestMigration:
    """Tests for Migration dataclass."""

    def test_migration_creation(self) -> None:
        """Test Migration dataclass creation."""
        migration = Migration(
            version=1,
            description="Initial migration",
            upgrade_sql=["CREATE TABLE test (id INT)"],
            downgrade_sql=["DROP TABLE test"],
        )

        assert migration.version == 1
        assert migration.description == "Initial migration"
        assert len(migration.upgrade_sql) == 1
        assert len(migration.downgrade_sql) == 1


class TestMigrationResult:
    """Tests for MigrationResult dataclass."""

    def test_default_values(self) -> None:
        """Test default result values."""
        result = MigrationResult()

        assert result.success is True
        assert result.applied_versions == []
        assert result.current_version == 0
        assert result.errors == []

    def test_custom_values(self) -> None:
        """Test custom result values."""
        result = MigrationResult(
            success=False,
            applied_versions=[1, 2],
            current_version=2,
            errors=["Error 1"],
        )

        assert result.success is False
        assert result.applied_versions == [1, 2]
        assert result.current_version == 2
        assert result.errors == ["Error 1"]


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_camel_to_snake(self) -> None:
        """Test CamelCase to snake_case conversion."""
        assert _camel_to_snake("Contact") == "contact"
        assert _camel_to_snake("ContactType") == "contact_type"
        assert _camel_to_snake("APIResponse") == "a_p_i_response"
        assert _camel_to_snake("SomeLongEntityName") == "some_long_entity_name"

    def test_is_postgresql(self) -> None:
        """Test PostgreSQL detection."""
        assert _is_postgresql(DatabaseDialect.POSTGRESQL) is True
        assert _is_postgresql("postgresql") is True
        assert _is_postgresql(DatabaseDialect.SQLITE) is False
        assert _is_postgresql("sqlite") is False

    def test_get_placeholder_sqlite(self) -> None:
        """Test placeholder for SQLite."""
        assert _get_placeholder("sqlite") == "?"
        assert _get_placeholder("sqlite", 1) == "?"
        assert _get_placeholder("sqlite", 5) == "?"
        assert _get_placeholder(DatabaseDialect.SQLITE) == "?"

    def test_get_placeholder_postgresql(self) -> None:
        """Test placeholder for PostgreSQL."""
        assert _get_placeholder("postgresql") == "$1"
        assert _get_placeholder("postgresql", 1) == "$1"
        assert _get_placeholder("postgresql", 3) == "$3"
        assert _get_placeholder(DatabaseDialect.POSTGRESQL) == "$1"

    def test_get_timestamp_type(self) -> None:
        """Test timestamp type for different dialects."""
        assert _get_timestamp_type("sqlite") == "TEXT"
        assert _get_timestamp_type("postgresql") == "TIMESTAMP WITH TIME ZONE"
        assert _get_timestamp_type(DatabaseDialect.SQLITE) == "TEXT"
        assert _get_timestamp_type(DatabaseDialect.POSTGRESQL) == "TIMESTAMP WITH TIME ZONE"

    def test_get_json_type(self) -> None:
        """Test JSON type for different dialects."""
        assert _get_json_type("sqlite") == "TEXT"
        assert _get_json_type("postgresql") == "JSONB"
        assert _get_json_type(DatabaseDialect.SQLITE) == "TEXT"
        assert _get_json_type(DatabaseDialect.POSTGRESQL) == "JSONB"

    def test_get_serial_type(self) -> None:
        """Test serial type for different dialects."""
        assert _get_serial_type("sqlite") == "INTEGER"
        assert _get_serial_type("postgresql") == "SERIAL"
        assert _get_serial_type(DatabaseDialect.SQLITE) == "INTEGER"
        assert _get_serial_type(DatabaseDialect.POSTGRESQL) == "SERIAL"


class TestDDLGeneration:
    """Tests for DDL generation functions."""

    def test_generate_version_table_ddl_sqlite(self) -> None:
        """Test version table DDL for SQLite."""
        config = MigrationConfig(dialect="sqlite")
        ddl = generate_version_table_ddl(config)

        assert "CREATE TABLE IF NOT EXISTS civi_migrations" in ddl
        assert "id INTEGER PRIMARY KEY" in ddl
        assert "version INTEGER NOT NULL UNIQUE" in ddl
        assert "description TEXT NOT NULL" in ddl
        assert "applied_at TEXT NOT NULL" in ddl
        assert "checksum TEXT" in ddl

    def test_generate_version_table_ddl_postgresql(self) -> None:
        """Test version table DDL for PostgreSQL."""
        config = MigrationConfig(dialect="postgresql")
        ddl = generate_version_table_ddl(config)

        assert "CREATE TABLE IF NOT EXISTS civi_migrations" in ddl
        assert "TIMESTAMP WITH TIME ZONE" in ddl

    def test_generate_entity_table_ddl_sqlite(self) -> None:
        """Test entity table DDL for SQLite."""
        config = MigrationConfig(dialect="sqlite")
        ddl = generate_entity_table_ddl("Contact", config)

        assert "CREATE TABLE IF NOT EXISTS civi_cache_contact" in ddl
        assert "id INTEGER PRIMARY KEY" in ddl
        assert "data TEXT NOT NULL" in ddl
        assert "created_at TEXT NOT NULL" in ddl
        assert "updated_at TEXT NOT NULL" in ddl
        assert "sync_status TEXT NOT NULL DEFAULT 'synced'" in ddl
        assert "last_synced_at TEXT" in ddl
        assert "last_modified_locally TEXT" in ddl

    def test_generate_entity_table_ddl_postgresql(self) -> None:
        """Test entity table DDL for PostgreSQL."""
        config = MigrationConfig(dialect="postgresql")
        ddl = generate_entity_table_ddl("Activity", config)

        assert "CREATE TABLE IF NOT EXISTS civi_cache_activity" in ddl
        assert "JSONB NOT NULL" in ddl
        assert "TIMESTAMP WITH TIME ZONE" in ddl

    def test_generate_entity_table_ddl_custom_prefix(self) -> None:
        """Test entity table DDL with custom prefix."""
        config = MigrationConfig(table_prefix="app_", dialect="sqlite")
        ddl = generate_entity_table_ddl("Contact", config)

        assert "CREATE TABLE IF NOT EXISTS app_contact" in ddl

    def test_generate_sync_metadata_table_ddl_sqlite(self) -> None:
        """Test sync metadata table DDL for SQLite."""
        config = MigrationConfig(dialect="sqlite")
        ddl = generate_sync_metadata_table_ddl(config)

        assert "CREATE TABLE IF NOT EXISTS civi_cache_sync_metadata" in ddl
        assert "entity_id INTEGER NOT NULL" in ddl
        assert "entity_type TEXT NOT NULL" in ddl
        assert "PRIMARY KEY (entity_id, entity_type)" in ddl
        assert "sync_status TEXT NOT NULL DEFAULT 'synced'" in ddl

    def test_generate_sync_metadata_table_ddl_postgresql(self) -> None:
        """Test sync metadata table DDL for PostgreSQL."""
        config = MigrationConfig(dialect="postgresql")
        ddl = generate_sync_metadata_table_ddl(config)

        assert "CREATE TABLE IF NOT EXISTS civi_cache_sync_metadata" in ddl
        assert "TIMESTAMP WITH TIME ZONE" in ddl

    def test_generate_table_ddl_alias(self) -> None:
        """Test that generate_table_ddl is an alias for generate_entity_table_ddl."""
        config = MigrationConfig(dialect="sqlite")
        ddl1 = generate_entity_table_ddl("Contact", config)
        ddl2 = generate_table_ddl("Contact", config)

        assert ddl1 == ddl2


class TestGetAllMigrations:
    """Tests for get_all_migrations function."""

    def test_returns_list_of_migrations(self) -> None:
        """Test that get_all_migrations returns a list of Migration objects."""
        config = MigrationConfig()
        migrations = get_all_migrations(config)

        assert isinstance(migrations, list)
        assert len(migrations) >= 1
        assert all(isinstance(m, Migration) for m in migrations)

    def test_first_migration_is_version_1(self) -> None:
        """Test that the first migration is version 1."""
        config = MigrationConfig()
        migrations = get_all_migrations(config)

        assert migrations[0].version == 1

    def test_initial_migration_creates_expected_tables(self) -> None:
        """Test that initial migration creates all expected tables."""
        config = MigrationConfig()
        migrations = get_all_migrations(config)
        initial = migrations[0]

        # Check upgrade SQL creates version table
        upgrade_sql_str = " ".join(initial.upgrade_sql)
        assert "civi_migrations" in upgrade_sql_str

        # Check for entity tables
        for entity in config.include_entities:
            table_name = f"civi_cache_{_camel_to_snake(entity)}"
            assert table_name in upgrade_sql_str

        # Check for sync metadata table
        assert "civi_cache_sync_metadata" in upgrade_sql_str

        # Check for sync cursor table
        assert "civi_cache_sync_cursor" in upgrade_sql_str

    def test_initial_migration_has_matching_downgrade(self) -> None:
        """Test that initial migration has proper downgrade SQL."""
        config = MigrationConfig()
        migrations = get_all_migrations(config)
        initial = migrations[0]

        downgrade_sql_str = " ".join(initial.downgrade_sql)

        # Check that downgrade drops version table
        assert "DROP TABLE IF EXISTS civi_migrations" in downgrade_sql_str

        # Check for entity table drops
        for entity in config.include_entities:
            table_name = f"civi_cache_{_camel_to_snake(entity)}"
            assert f"DROP TABLE IF EXISTS {table_name}" in downgrade_sql_str


class TestDatabaseDialect:
    """Tests for DatabaseDialect enum."""

    def test_dialect_values(self) -> None:
        """Test dialect enum values."""
        assert DatabaseDialect.SQLITE.value == "sqlite"
        assert DatabaseDialect.POSTGRESQL.value == "postgresql"

    def test_dialect_is_string_enum(self) -> None:
        """Test that dialect can be compared as string."""
        assert DatabaseDialect.SQLITE == "sqlite"
        assert DatabaseDialect.POSTGRESQL == "postgresql"
