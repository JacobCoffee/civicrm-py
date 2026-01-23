SQLSpec Integration
===================

Local database caching for CiviCRM entities using sqlspec with support for PostgreSQL and SQLite.

The sqlspec integration provides a repository layer that caches CiviCRM data locally for:

- **Offline access**: Query cached data without CiviCRM connectivity
- **Performance**: Faster reads for frequently accessed data
- **Sync operations**: Bidirectional sync between local cache and CiviCRM

Installation
------------

Install with the sqlspec extra:

.. code-block:: bash

   pip install civi-py[sqlspec]

This installs sqlspec with both asyncpg (PostgreSQL) and aiosqlite (SQLite) adapters.


Configuration
-------------

Use ``CiviSQLSpecConfig`` to configure the database connection.

SQLite (Default)
^^^^^^^^^^^^^^^^

SQLite is the simplest option, requiring no external database server:

.. code-block:: python

   from civi_py.contrib.sqlspec import CiviSQLSpecConfig

   # In-memory database (data lost on restart)
   config = CiviSQLSpecConfig()

   # Persistent file-based database
   config = CiviSQLSpecConfig(
       adapter="aiosqlite",
       database="/path/to/civi_cache.db",
   )

PostgreSQL
^^^^^^^^^^

For production deployments with connection pooling:

.. code-block:: python

   from civi_py.contrib.sqlspec import CiviSQLSpecConfig

   config = CiviSQLSpecConfig(
       adapter="asyncpg",
       dsn="postgresql://user:password@localhost:5432/civi_cache",
       pool_min_size=5,
       pool_max_size=20,
       timeout=30.0,
   )

Configuration Options
^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Option
     - Default
     - Description
   * - ``adapter``
     - ``aiosqlite``
     - Database adapter: ``asyncpg`` or ``aiosqlite``
   * - ``dsn``
     - None
     - PostgreSQL connection string (required for asyncpg)
   * - ``database``
     - ``:memory:``
     - SQLite database path
   * - ``pool_min_size``
     - 1
     - Minimum pool connections (asyncpg only)
   * - ``pool_max_size``
     - 10
     - Maximum pool connections (asyncpg only)
   * - ``timeout``
     - 30.0
     - Connection timeout in seconds
   * - ``table_prefix``
     - ``civi_cache_``
     - Prefix for cache table names
   * - ``auto_create_tables``
     - True
     - Create tables automatically on startup


Repository Layer
----------------

Repositories provide local caching of CiviCRM entities with a familiar API.

Available Repositories
^^^^^^^^^^^^^^^^^^^^^^

- ``ContactRepository``: Cache Contact entities
- ``ActivityRepository``: Cache Activity entities
- ``ContributionRepository``: Cache Contribution entities
- ``EventRepository``: Cache Event entities
- ``MembershipRepository``: Cache Membership entities
- ``CiviRepository``: Base class for custom repositories

Basic Usage
^^^^^^^^^^^

.. code-block:: python

   import asyncio
   from civi_py import CiviClient
   from civi_py.contrib.sqlspec import CiviSQLSpecConfig, ContactRepository

   async def main():
       # Configure database
       config = CiviSQLSpecConfig(database="cache.db")

       # Create repository
       contact_repo = ContactRepository(config)

       async with CiviClient() as client:
           async with contact_repo.get_session() as session:
               # Sync contacts from CiviCRM to local cache
               result = await contact_repo.sync_from_civi(
                   session,
                   client,
                   is_deleted=False,
                   limit=1000,
               )
               print(f"Synced {result.synced_count} contacts")

               # Query local cache (no API call)
               contacts = await contact_repo.filter(
                   session,
                   contact_type="Individual",
                   limit=10,
               )
               for contact in contacts:
                   print(contact.display_name)

   asyncio.run(main())


Sync Operations
---------------

sync_from_civi
^^^^^^^^^^^^^^

Pull data from CiviCRM to the local database:

.. code-block:: python

   async with contact_repo.get_session() as session:
       # Sync with filters
       result = await contact_repo.sync_from_civi(
           session,
           client,
           is_deleted=False,  # Filter condition
           contact_type="Individual",  # Another filter
           limit=500,  # Max records to sync
       )

       print(f"Synced: {result.synced_count}")
       print(f"Errors: {result.error_count}")
       if result.errors:
           for entity_id, error in result.errors:
               print(f"  {entity_id}: {error}")

sync_to_civi
^^^^^^^^^^^^

Push local changes back to CiviCRM:

.. code-block:: python

   async with contact_repo.get_session() as session:
       # First, make local changes
       contact = await contact_repo.get(session, contact_id=123)
       if contact:
           # Modify locally
           contact.first_name = "Updated"
           await contact_repo.save(session, contact)

       # Sync changes to CiviCRM
       result = await contact_repo.sync_to_civi(
           session,
           client,
           only_pending=True,  # Only sync changed records
       )

       print(f"Pushed {result.synced_count} changes to CiviCRM")


Local Cache Operations
----------------------

Query local data without making API calls.

Filtering
^^^^^^^^^

.. code-block:: python

   async with contact_repo.get_session() as session:
       # Filter by field values
       individuals = await contact_repo.filter(
           session,
           contact_type="Individual",
           is_deleted=False,
       )

       # With pagination and ordering
       recent = await contact_repo.filter(
           session,
           is_deleted=False,
           limit=25,
           offset=0,
           order_by="-created_date",  # Descending
       )

Get by ID
^^^^^^^^^

.. code-block:: python

   async with contact_repo.get_session() as session:
       contact = await contact_repo.get(session, entity_id=42)
       if contact:
           print(contact.display_name)

Count
^^^^^

.. code-block:: python

   async with contact_repo.get_session() as session:
       total = await contact_repo.count(session)
       active = await contact_repo.count(session, is_deleted=False)
       print(f"Active contacts: {active}/{total}")

Save and Delete
^^^^^^^^^^^^^^^

.. code-block:: python

   from civi_py.entities import Contact

   async with contact_repo.get_session() as session:
       # Create new contact in local cache
       contact = Contact(
           first_name="New",
           last_name="Contact",
           contact_type="Individual",
       )
       contact = await contact_repo.save(session, contact)
       print(f"Saved with local ID: {contact.id}")

       # Delete from local cache
       deleted = await contact_repo.delete(session, entity_id=contact.id)


Sync Metadata
-------------

Track synchronization state for each entity.

.. code-block:: python

   from civi_py.contrib.sqlspec import SyncStatus

   async with contact_repo.get_session() as session:
       metadata = await contact_repo.get_sync_metadata(session, entity_id=42)

       if metadata:
           print(f"Status: {metadata.sync_status}")
           print(f"Last synced: {metadata.last_synced_at}")
           print(f"Last modified locally: {metadata.last_modified_locally}")

           if metadata.sync_status == SyncStatus.ERROR:
               print(f"Error: {metadata.error_message}")

Sync statuses:

- ``SYNCED``: Entity matches CiviCRM
- ``PENDING``: Local changes not yet synced
- ``CONFLICT``: Local and remote changes conflict
- ``ERROR``: Sync failed with an error


Migrations
----------

Manage cache table schemas with the migrations module.

Running Migrations
^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from civi_py.contrib.sqlspec import (
       CiviSQLSpecConfig,
       MigrationConfig,
       upgrade,
       get_migration_status,
   )
   from sqlspec import SQLSpec

   async def run_migrations():
       sqlspec_config = CiviSQLSpecConfig(database="cache.db")
       migration_config = MigrationConfig()

       spec = SQLSpec()
       spec.add_config(sqlspec_config.get_adapter_config())

       async with spec.get_session() as session:
           # Check current status
           status = await get_migration_status(session, migration_config)
           print(f"Current version: {status['current_version']}")
           print(f"Pending: {status['pending_count']}")

           # Apply pending migrations
           result = await upgrade(session, migration_config)
           if result.success:
               print(f"Applied: {result.applied_versions}")
           else:
               print(f"Errors: {result.errors}")

Rolling Back
^^^^^^^^^^^^

.. code-block:: python

   from civi_py.contrib.sqlspec import downgrade

   async with spec.get_session() as session:
       # Rollback to version 1
       result = await downgrade(session, migration_config, target_version=1)

       # Remove all migrations
       result = await downgrade(session, migration_config, target_version=0)


CLI Commands
------------

Manage the cache database from the command line.

Initialization
^^^^^^^^^^^^^^

.. code-block:: bash

   # Initialize SQLite database
   civi-py db init --database ./cache.db

   # Initialize PostgreSQL
   civi-py db init --adapter asyncpg --dsn postgresql://localhost/civi_cache

Upgrade
^^^^^^^

.. code-block:: bash

   # Apply all pending migrations
   civi-py db upgrade --database cache.db

   # Upgrade to specific version
   civi-py db upgrade --database cache.db --version 1

Status
^^^^^^

.. code-block:: bash

   # Check migration status
   civi-py db status --database cache.db

   # JSON output
   civi-py db status --database cache.db --json

Downgrade
^^^^^^^^^

.. code-block:: bash

   # Rollback to version 1
   civi-py db downgrade --database cache.db --version 1

   # Remove all tables (requires confirmation)
   civi-py db downgrade --database cache.db --version 0

   # Skip confirmation
   civi-py db downgrade --database cache.db --version 0 --yes


Litestar Integration
--------------------

Use sqlspec with the Litestar plugin for automatic repository injection.

Plugin Configuration
^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from litestar import Litestar
   from civi_py.contrib.litestar import CiviPlugin, CiviPluginConfig
   from civi_py.contrib.litestar.sqlspec_integration import SQLSpecPluginConfig
   from civi_py.contrib.sqlspec import CiviSQLSpecConfig

   config = CiviPluginConfig(
       sqlspec=SQLSpecPluginConfig(
           enabled=True,
           sqlspec_config=CiviSQLSpecConfig(
               adapter="aiosqlite",
               database="civi_cache.db",
           ),
           auto_run_migrations=True,
           provide_repositories=True,
       ),
   )

   app = Litestar(plugins=[CiviPlugin(config)])

Using Repositories in Handlers
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Repositories are automatically injected via dependency injection:

.. code-block:: python

   from typing import Annotated
   from litestar import get
   from litestar.params import Dependency
   from civi_py.contrib.sqlspec import ContactRepository
   from civi_py.core.client import CiviClient

   @get("/cached-contacts")
   async def list_cached_contacts(
       contact_repository: Annotated[ContactRepository, Dependency(skip_validation=True)],
   ) -> dict:
       async with contact_repository.get_session() as session:
           contacts = await contact_repository.filter(
               session,
               is_deleted=False,
               limit=50,
           )
           return {"contacts": [c.to_dict() for c in contacts]}

   @get("/sync-contacts")
   async def sync_contacts(
       contact_repository: Annotated[ContactRepository, Dependency(skip_validation=True)],
       civi_client: CiviClient,
   ) -> dict:
       async with contact_repository.get_session() as session:
           result = await contact_repository.sync_from_civi(
               session,
               civi_client,
               is_deleted=False,
               limit=100,
           )
           return {
               "synced": result.synced_count,
               "errors": result.error_count,
           }

Standalone SQLSpec Plugin
^^^^^^^^^^^^^^^^^^^^^^^^^

Use sqlspec independently of CiviPlugin:

.. code-block:: python

   from litestar import Litestar
   from civi_py.contrib.litestar.sqlspec_integration import (
       SQLSpecPlugin,
       SQLSpecPluginConfig,
   )

   app = Litestar(
       route_handlers=[...],
       plugins=[
           SQLSpecPlugin(SQLSpecPluginConfig(enabled=True)),
       ],
   )


Custom Repositories
-------------------

Create repositories for custom entities:

.. code-block:: python

   from civi_py.contrib.sqlspec import CiviRepository
   from civi_py.entities.base import BaseEntity

   class MyCustomEntity(BaseEntity):
       """Custom CiviCRM entity."""

       __entity_name__ = "Custom_MyEntity"

       id: int | None = None
       name: str | None = None
       description: str | None = None
       is_active: bool = True

   class MyCustomRepository(CiviRepository["MyCustomEntity"]):
       """Repository for MyCustomEntity."""

       @property
       def entity_type(self) -> type[MyCustomEntity]:
           return MyCustomEntity

   # Usage
   config = CiviSQLSpecConfig(database="cache.db")
   repo = MyCustomRepository(config)

   async with repo.get_session() as session:
       await repo.sync_from_civi(session, client, is_active=True)


Environment Variables
---------------------

Configure sqlspec via environment variables for Litestar integration:

.. code-block:: bash

   CIVI_SQLSPEC_ADAPTER=aiosqlite
   CIVI_SQLSPEC_DATABASE=/var/lib/civi/cache.db
   CIVI_SQLSPEC_TABLE_PREFIX=civi_cache_

   # For PostgreSQL
   CIVI_SQLSPEC_ADAPTER=asyncpg
   CIVI_SQLSPEC_DSN=postgresql://user:pass@localhost:5432/civi_cache
   CIVI_SQLSPEC_POOL_MIN_SIZE=5
   CIVI_SQLSPEC_POOL_MAX_SIZE=20
   CIVI_SQLSPEC_TIMEOUT=30


Complete Example
----------------

A full example combining sync, caching, and Litestar:

.. code-block:: python

   import asyncio
   from litestar import Litestar, get, post
   from litestar.params import Dependency
   from typing import Annotated

   from civi_py import CiviClient
   from civi_py.contrib.litestar import CiviPlugin, CiviPluginConfig
   from civi_py.contrib.litestar.sqlspec_integration import SQLSpecPluginConfig
   from civi_py.contrib.sqlspec import (
       CiviSQLSpecConfig,
       ContactRepository,
       SyncStatus,
   )


   @get("/contacts")
   async def list_contacts(
       contact_repository: Annotated[ContactRepository, Dependency(skip_validation=True)],
   ) -> dict:
       """List contacts from local cache."""
       async with contact_repository.get_session() as session:
           contacts = await contact_repository.filter(
               session,
               is_deleted=False,
               order_by="display_name",
               limit=100,
           )
           return {
               "contacts": [c.to_dict() for c in contacts],
               "count": len(contacts),
           }


   @post("/contacts/sync")
   async def sync_contacts(
       contact_repository: Annotated[ContactRepository, Dependency(skip_validation=True)],
       civi_client: CiviClient,
   ) -> dict:
       """Sync contacts from CiviCRM to local cache."""
       async with contact_repository.get_session() as session:
           result = await contact_repository.sync_from_civi(
               session,
               civi_client,
               is_deleted=False,
               contact_type="Individual",
               limit=500,
           )
           return {
               "synced": result.synced_count,
               "errors": result.error_count,
               "error_details": [
                   {"id": eid, "error": err}
                   for eid, err in result.errors[:10]
               ],
           }


   @get("/contacts/{contact_id:int}")
   async def get_contact(
       contact_id: int,
       contact_repository: Annotated[ContactRepository, Dependency(skip_validation=True)],
   ) -> dict:
       """Get a single contact from cache with sync metadata."""
       async with contact_repository.get_session() as session:
           contact = await contact_repository.get(session, entity_id=contact_id)
           if not contact:
               from litestar.exceptions import NotFoundException
               raise NotFoundException(f"Contact {contact_id} not found in cache")

           metadata = await contact_repository.get_sync_metadata(
               session, entity_id=contact_id
           )

           return {
               "contact": contact.to_dict(),
               "sync_status": metadata.sync_status.value if metadata else "unknown",
               "last_synced": str(metadata.last_synced_at) if metadata else None,
           }


   # Configure the application
   config = CiviPluginConfig(
       sqlspec=SQLSpecPluginConfig(
           enabled=True,
           sqlspec_config=CiviSQLSpecConfig(
               adapter="aiosqlite",
               database="./civi_cache.db",
           ),
           auto_run_migrations=True,
       ),
   )

   app = Litestar(
       route_handlers=[list_contacts, sync_contacts, get_contact],
       plugins=[CiviPlugin(config)],
   )
