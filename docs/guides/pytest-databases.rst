Database Testing
================

Real database testing infrastructure for civi-py contributors using pytest-databases.

This guide covers testing against actual PostgreSQL and SQLite databases for
contributors who want to verify their changes work with real database operations.


Purpose
-------

While unit tests mock database interactions, integration tests verify:

- SQL generation works correctly for each database dialect
- Connection pooling behaves as expected
- Migrations apply cleanly to real databases
- Repository operations function end-to-end
- Edge cases in data serialization

These tests require Docker for PostgreSQL but can run SQLite tests without it.


Installation
------------

Install with development dependencies:

.. code-block:: bash

   pip install -e ".[dev,sqlspec]"

For PostgreSQL tests, install Docker:

- **macOS**: `Docker Desktop <https://www.docker.com/products/docker-desktop/>`_
- **Linux**: ``apt install docker.io`` or equivalent
- **Windows**: Docker Desktop with WSL2

Verify Docker is running:

.. code-block:: bash

   docker --version
   docker ps


Running Database Tests
----------------------

SQLite Tests
^^^^^^^^^^^^

SQLite tests run without Docker:

.. code-block:: bash

   # Run all SQLite tests
   pytest tests/integration/test_sqlspec_sqlite.py -v

   # Run specific test
   pytest tests/integration/test_sqlspec_sqlite.py::test_contact_repository -v

PostgreSQL Tests
^^^^^^^^^^^^^^^^

PostgreSQL tests require Docker:

.. code-block:: bash

   # Run all PostgreSQL tests (starts container automatically)
   pytest tests/integration/test_sqlspec_postgres.py -v

   # Tests are skipped if Docker is unavailable
   pytest tests/integration/test_sqlspec_postgres.py -v
   # Output: SKIPPED (Docker not available)

All Database Tests
^^^^^^^^^^^^^^^^^^

Run the full integration suite:

.. code-block:: bash

   # Run all database integration tests
   pytest tests/integration/ -v -m "database"

   # Run with coverage
   pytest tests/integration/ -v --cov=civi_py.contrib.sqlspec


Available Fixtures
------------------

pytest-databases provides fixtures for database connections.

sqlite_connection
^^^^^^^^^^^^^^^^^

In-memory SQLite database for fast tests:

.. code-block:: python

   import pytest

   @pytest.mark.database
   async def test_sqlite_operations(sqlite_connection):
       """Test with in-memory SQLite."""
       async with sqlite_connection as conn:
           await conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
           await conn.execute("INSERT INTO test (id) VALUES (1)")
           result = await conn.fetch_one("SELECT * FROM test WHERE id = 1")
           assert result["id"] == 1

postgres_connection
^^^^^^^^^^^^^^^^^^^

Real PostgreSQL connection via Docker:

.. code-block:: python

   import pytest

   @pytest.mark.database
   @pytest.mark.requires_docker
   async def test_postgres_operations(postgres_connection):
       """Test with real PostgreSQL."""
       async with postgres_connection as conn:
           await conn.execute("CREATE TABLE test (id SERIAL PRIMARY KEY)")
           await conn.execute("INSERT INTO test DEFAULT VALUES")
           result = await conn.fetch_one("SELECT * FROM test WHERE id = 1")
           assert result["id"] == 1

sqlspec_config
^^^^^^^^^^^^^^

Pre-configured ``CiviSQLSpecConfig`` for each database:

.. code-block:: python

   @pytest.mark.database
   async def test_with_sqlspec_config(sqlspec_config):
       """Test with CiviSQLSpecConfig fixture."""
       from civi_py.contrib.sqlspec import ContactRepository

       repo = ContactRepository(sqlspec_config)
       async with repo.get_session() as session:
           count = await repo.count(session)
           assert count >= 0


Writing Database Tests
----------------------

Test Structure
^^^^^^^^^^^^^^

Organize database tests by functionality:

.. code-block:: text

   tests/integration/
   |-- conftest.py              # Shared fixtures
   |-- test_sqlspec_sqlite.py   # SQLite-specific tests
   |-- test_sqlspec_postgres.py # PostgreSQL-specific tests
   |-- test_migrations.py       # Migration tests for all DBs
   `-- test_repositories.py     # Repository tests for all DBs

Basic Test Pattern
^^^^^^^^^^^^^^^^^^

.. code-block:: python

   import pytest
   from civi_py.contrib.sqlspec import CiviSQLSpecConfig, ContactRepository


   @pytest.fixture
   def contact_repo(sqlspec_config):
       """Create ContactRepository with test config."""
       return ContactRepository(sqlspec_config)


   @pytest.mark.database
   class TestContactRepository:
       """Integration tests for ContactRepository."""

       async def test_create_and_retrieve(self, contact_repo):
           """Test creating and retrieving a contact."""
           from civi_py.entities import Contact

           async with contact_repo.get_session() as session:
               # Create contact
               contact = Contact(
                   first_name="Test",
                   last_name="User",
                   contact_type="Individual",
               )
               saved = await contact_repo.save(session, contact)
               assert saved.id is not None

               # Retrieve contact
               retrieved = await contact_repo.get(session, entity_id=saved.id)
               assert retrieved is not None
               assert retrieved.first_name == "Test"

       async def test_filter_contacts(self, contact_repo):
           """Test filtering contacts."""
           from civi_py.entities import Contact

           async with contact_repo.get_session() as session:
               # Create test data
               for i in range(5):
                   contact = Contact(
                       first_name=f"Test{i}",
                       last_name="Filter",
                       contact_type="Individual",
                       is_deleted=i % 2 == 0,
                   )
                   await contact_repo.save(session, contact)

               # Filter
               active = await contact_repo.filter(
                   session,
                   is_deleted=False,
               )
               assert len(active) == 2

       async def test_count_contacts(self, contact_repo):
           """Test counting contacts."""
           async with contact_repo.get_session() as session:
               total = await contact_repo.count(session)
               deleted = await contact_repo.count(session, is_deleted=True)
               active = await contact_repo.count(session, is_deleted=False)

               assert total == deleted + active

Testing Migrations
^^^^^^^^^^^^^^^^^^

.. code-block:: python

   import pytest
   from civi_py.contrib.sqlspec import (
       CiviSQLSpecConfig,
       MigrationConfig,
       upgrade,
       downgrade,
       get_migration_status,
       verify_schema,
   )


   @pytest.mark.database
   class TestMigrations:
       """Integration tests for database migrations."""

       async def test_upgrade_creates_tables(self, sqlspec_config, db_session):
           """Test that upgrade creates all expected tables."""
           migration_config = MigrationConfig()

           result = await upgrade(db_session, migration_config)

           assert result.success
           assert result.current_version >= 1

           # Verify tables exist
           tables = await verify_schema(db_session, migration_config)
           assert tables["civi_migrations"] is True
           assert tables["civi_cache_contact"] is True
           assert tables["civi_cache_sync_metadata"] is True

       async def test_downgrade_removes_tables(self, sqlspec_config, db_session):
           """Test that downgrade removes tables."""
           migration_config = MigrationConfig()

           # First upgrade
           await upgrade(db_session, migration_config)

           # Then downgrade to version 0
           result = await downgrade(db_session, migration_config, target_version=0)

           assert result.success

           # Verify tables are gone
           tables = await verify_schema(db_session, migration_config)
           assert all(not exists for exists in tables.values())

       async def test_migration_is_idempotent(self, sqlspec_config, db_session):
           """Test running upgrade multiple times is safe."""
           migration_config = MigrationConfig()

           # Run upgrade twice
           result1 = await upgrade(db_session, migration_config)
           result2 = await upgrade(db_session, migration_config)

           assert result1.success
           assert result2.success
           assert result1.current_version == result2.current_version

Testing Dialect Differences
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   import pytest


   @pytest.mark.database
   class TestDialectSpecifics:
       """Test database-specific behavior."""

       @pytest.mark.parametrize("adapter", ["aiosqlite", "asyncpg"])
       async def test_json_storage(self, adapter, get_config_for_adapter):
           """Test JSON field storage works for both dialects."""
           config = get_config_for_adapter(adapter)

           if adapter == "asyncpg" and not docker_available():
               pytest.skip("Docker required for PostgreSQL tests")

           repo = ContactRepository(config)
           async with repo.get_session() as session:
               # Test list field serialization
               contact = Contact(
                   first_name="Test",
                   last_name="JSON",
                   api_key=[{"type": "Work", "key": "abc123"}],
               )
               saved = await repo.save(session, contact)

               # Retrieve and verify JSON is intact
               retrieved = await repo.get(session, entity_id=saved.id)
               assert retrieved.api_key == [{"type": "Work", "key": "abc123"}]


Skipping Tests
--------------

Skip tests when requirements are not met.

Docker Not Available
^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   import pytest

   def docker_available():
       """Check if Docker is available."""
       import subprocess
       try:
           subprocess.run(["docker", "ps"], capture_output=True, check=True)
           return True
       except (subprocess.CalledProcessError, FileNotFoundError):
           return False


   @pytest.mark.skipif(not docker_available(), reason="Docker not available")
   async def test_postgres_specific():
       """Test that requires PostgreSQL."""
       ...

Using Markers
^^^^^^^^^^^^^

.. code-block:: python

   # conftest.py
   import pytest

   def pytest_configure(config):
       config.addinivalue_line(
           "markers", "requires_docker: test requires Docker"
       )
       config.addinivalue_line(
           "markers", "database: test uses real database"
       )

   def pytest_collection_modifyitems(config, items):
       if not docker_available():
           skip_docker = pytest.mark.skip(reason="Docker not available")
           for item in items:
               if "requires_docker" in item.keywords:
                   item.add_marker(skip_docker)

Usage:

.. code-block:: python

   @pytest.mark.requires_docker
   @pytest.mark.database
   async def test_postgres_connection(postgres_connection):
       """This test is skipped if Docker is unavailable."""
       ...


CI Configuration
----------------

Configure GitHub Actions for database tests:

.. code-block:: yaml

   # .github/workflows/test.yml
   name: Tests

   on: [push, pull_request]

   jobs:
     test:
       runs-on: ubuntu-latest

       services:
         postgres:
           image: postgres:15
           env:
             POSTGRES_USER: test
             POSTGRES_PASSWORD: test
             POSTGRES_DB: civi_test
           ports:
             - 5432:5432
           options: >-
             --health-cmd pg_isready
             --health-interval 10s
             --health-timeout 5s
             --health-retries 5

       steps:
         - uses: actions/checkout@v4

         - name: Set up Python
           uses: actions/setup-python@v5
           with:
             python-version: "3.12"

         - name: Install dependencies
           run: pip install -e ".[dev,sqlspec]"

         - name: Run unit tests
           run: pytest tests/ -v --ignore=tests/integration/

         - name: Run database tests
           env:
             CIVI_SQLSPEC_DSN: postgresql://test:test@localhost:5432/civi_test
           run: pytest tests/integration/ -v -m "database"


Troubleshooting
---------------

Docker Connection Errors
^^^^^^^^^^^^^^^^^^^^^^^^

**Error**: ``Cannot connect to Docker daemon``

Ensure Docker is running:

.. code-block:: bash

   # macOS/Windows
   # Open Docker Desktop application

   # Linux
   sudo systemctl start docker

   # Verify
   docker ps

**Error**: ``Port 5432 already in use``

Stop existing PostgreSQL or use a different port:

.. code-block:: bash

   # Find process using port
   lsof -i :5432

   # Or configure different port in tests
   export CIVI_TEST_POSTGRES_PORT=5433

Database Connection Timeouts
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Increase timeout in test configuration:

.. code-block:: python

   @pytest.fixture
   def sqlspec_config():
       return CiviSQLSpecConfig(
           adapter="asyncpg",
           dsn=os.environ.get("CIVI_SQLSPEC_DSN"),
           timeout=60.0,  # Increase timeout
       )

Test Isolation Issues
^^^^^^^^^^^^^^^^^^^^^

Ensure tests clean up after themselves:

.. code-block:: python

   @pytest.fixture
   async def clean_database(db_session):
       """Clean database before and after test."""
       # Clean before
       await db_session.execute("DELETE FROM civi_cache_contact")
       await db_session.execute("DELETE FROM civi_cache_sync_metadata")

       yield

       # Clean after
       await db_session.execute("DELETE FROM civi_cache_contact")
       await db_session.execute("DELETE FROM civi_cache_sync_metadata")

   @pytest.mark.database
   async def test_with_clean_db(clean_database, contact_repo):
       """Test runs with clean database state."""
       ...


See Also
--------

- :doc:`sqlspec` for sqlspec integration documentation
- `pytest-databases <https://github.com/litestar-org/pytest-databases>`_ project
- `pytest-docker <https://github.com/avast/pytest-docker>`_ for Docker-based testing
