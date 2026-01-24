Litestar Integration
====================

Full plugin integration for Litestar 2+ with dependency injection, auto-generated routes, health checks, and DTOs.

Installation
------------

Install with the Litestar extra:

.. code-block:: bash

   pip install civicrm-py[litestar]


Plugin Setup
------------

Basic Usage
^^^^^^^^^^^

Add the plugin to your Litestar application:

.. code-block:: python

   from litestar import Litestar, get
   from civicrm_py.core.client import CiviClient
   from civicrm_py.contrib.litestar import CiviPlugin


   @get("/contacts")
   async def list_contacts(civi_client: CiviClient) -> dict:
       response = await civi_client.get("Contact", limit=10)
       return {"contacts": response.values}


   app = Litestar(
       route_handlers=[list_contacts],
       plugins=[CiviPlugin()],
   )

The plugin:

* Manages client lifecycle (startup/shutdown)
* Provides dependency injection via type hints
* Reads configuration from environment variables

With Configuration
^^^^^^^^^^^^^^^^^^

Customize the plugin behavior with ``CiviPluginConfig``:

.. code-block:: python

   from civicrm_py.contrib.litestar import CiviPlugin, CiviPluginConfig

   config = CiviPluginConfig(
       api_prefix="/api/v1/civi",           # CRUD routes prefix
       enable_health_check=True,            # Enable /health/civi endpoint
       include_entities=["Contact", "Activity"],  # Limit auto-generated routes
   )

   app = Litestar(plugins=[CiviPlugin(config)])


Environment Variables
---------------------

Set these environment variables for automatic configuration:

.. code-block:: bash

   CIVI_BASE_URL=https://example.org/civicrm/ajax/api4
   CIVI_API_KEY=your-api-key
   CIVI_SITE_KEY=your-site-key    # Optional
   CIVI_TIMEOUT=30                # Default: 30 seconds
   CIVI_VERIFY_SSL=true           # Default: true


Dependency Injection
--------------------

The plugin provides ``CiviClient`` via Litestar's dependency injection. Declare the dependency using a type hint:

.. code-block:: python

   from litestar import get, post, delete
   from civicrm_py.core.client import CiviClient


   @get("/contacts")
   async def list_contacts(civi_client: CiviClient) -> dict:
       response = await civi_client.get("Contact", limit=25)
       return {"contacts": response.values}


   @get("/contacts/{contact_id:int}")
   async def get_contact(contact_id: int, civi_client: CiviClient) -> dict:
       response = await civi_client.get(
           "Contact",
           where=[["id", "=", contact_id]],
           limit=1,
       )
       if not response.values:
           from litestar.exceptions import NotFoundException
           raise NotFoundException(f"Contact {contact_id} not found")
       return response.values[0]


   @post("/contacts")
   async def create_contact(data: dict, civi_client: CiviClient) -> dict:
       response = await civi_client.create("Contact", data)
       return response.values[0]


   @delete("/contacts/{contact_id:int}")
   async def delete_contact(contact_id: int, civi_client: CiviClient) -> None:
       await civi_client.delete("Contact", where=[["id", "=", contact_id]])

Manual Dependency Provider
^^^^^^^^^^^^^^^^^^^^^^^^^^

For custom dependency logic:

.. code-block:: python

   from litestar import Litestar
   from civicrm_py.contrib.litestar import provide_civi_client, CIVI_CLIENT_STATE_KEY

   app = Litestar(
       route_handlers=[...],
       dependencies={"civi_client": provide_civi_client},
   )


Auto-Generated Routes
---------------------

When ``api_prefix`` is set, the plugin generates CRUD routes for CiviCRM entities:

.. code-block:: python

   config = CiviPluginConfig(api_prefix="/api/civi")

Generated routes for each entity:

.. list-table::
   :header-rows: 1

   * - Method
     - Path
     - Action
   * - GET
     - ``{api_prefix}/Contact``
     - List contacts
   * - GET
     - ``{api_prefix}/Contact/{id}``
     - Get single contact
   * - POST
     - ``{api_prefix}/Contact``
     - Create contact
   * - PUT
     - ``{api_prefix}/Contact/{id}``
     - Update contact
   * - DELETE
     - ``{api_prefix}/Contact/{id}``
     - Delete contact

The same pattern applies to Activity, Contribution, Event, Membership, Participant, and Group.

Limiting Entities
^^^^^^^^^^^^^^^^^

Control which entities get routes:

.. code-block:: python

   # Only generate routes for specific entities
   config = CiviPluginConfig(
       api_prefix="/api/civi",
       include_entities=["Contact", "Activity", "Contribution"],
   )

Custom Controllers
^^^^^^^^^^^^^^^^^^

Use the built-in controllers directly:

.. code-block:: python

   from litestar import Litestar
   from civicrm_py.contrib.litestar import (
       CiviPlugin,
       ContactController,
       ActivityController,
   )

   app = Litestar(
       route_handlers=[ContactController, ActivityController],
       plugins=[CiviPlugin()],
   )

Create custom controllers:

.. code-block:: python

   from civicrm_py.contrib.litestar import create_entity_controller

   # Create a controller for a custom entity
   CustomEntityController = create_entity_controller(
       entity_name="CustomEntity",
       path="/custom-entities",
       tags=["Custom"],
   )


Health Checks
-------------

Enable the health check endpoint:

.. code-block:: python

   config = CiviPluginConfig(enable_health_check=True)

This adds ``GET /health/civi`` which returns:

.. code-block:: json

   {
       "status": "healthy",
       "civi_connected": true,
       "response_time_ms": 45.2,
       "api_version": "4",
       "timestamp": "2025-01-22T10:30:00Z"
   }

When unhealthy:

.. code-block:: json

   {
       "status": "unhealthy",
       "civi_connected": false,
       "timestamp": "2025-01-22T10:30:00Z",
       "error": "Connection refused"
   }

Manual Health Check
^^^^^^^^^^^^^^^^^^^

Use the health check function in custom routes:

.. code-block:: python

   from litestar import get
   from civicrm_py.contrib.litestar import civi_health_check, HealthCheckResponse


   @get("/my-health")
   async def custom_health(civi_client: CiviClient) -> HealthCheckResponse:
       return await civi_health_check(civi_client)


DTOs
----

The integration provides msgspec DTOs for request/response validation.

Filter DTOs
^^^^^^^^^^^

.. code-block:: python

   from civicrm_py.contrib.litestar import ContactFilterDTO, ActivityFilterDTO

   @get("/contacts")
   async def list_contacts(
       filters: ContactFilterDTO,
       civi_client: CiviClient,
   ) -> list[ContactResponseDTO]:
       # filters.contact_type, filters.is_deleted, etc.
       ...

Response DTOs
^^^^^^^^^^^^^

.. code-block:: python

   from civicrm_py.contrib.litestar import (
       ContactResponseDTO,
       ActivityResponseDTO,
       ContributionResponseDTO,
       APIResponseDTO,
   )

   @get("/contacts/{contact_id:int}")
   async def get_contact(
       contact_id: int,
       civi_client: CiviClient,
   ) -> ContactResponseDTO:
       response = await civi_client.get(
           "Contact",
           where=[["id", "=", contact_id]],
           limit=1,
       )
       return ContactResponseDTO(**response.values[0])

Create/Update DTOs
^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from civicrm_py.contrib.litestar import ContactCreateDTO, ContactUpdateDTO

   @post("/contacts")
   async def create_contact(
       data: ContactCreateDTO,
       civi_client: CiviClient,
   ) -> ContactResponseDTO:
       response = await civi_client.create("Contact", data.to_dict())
       return ContactResponseDTO(**response.values[0])

Pagination DTO
^^^^^^^^^^^^^^

.. code-block:: python

   from civicrm_py.contrib.litestar import PaginationDTO

   @get("/contacts")
   async def list_contacts(
       pagination: PaginationDTO,
       civi_client: CiviClient,
   ) -> APIResponseDTO:
       response = await civi_client.get(
           "Contact",
           limit=pagination.limit,
           offset=pagination.offset,
       )
       return APIResponseDTO(
           values=response.values,
           count=response.count,
           count_fetched=response.countFetched,
       )


Complete Example
----------------

.. code-block:: python

   from litestar import Litestar, get, post
   from litestar.exceptions import NotFoundException
   from civicrm_py.core.client import CiviClient
   from civicrm_py.contrib.litestar import (
       CiviPlugin,
       CiviPluginConfig,
       ContactCreateDTO,
       ContactResponseDTO,
       PaginationDTO,
   )


   @get("/api/contacts")
   async def list_contacts(
       pagination: PaginationDTO,
       civi_client: CiviClient,
   ) -> dict:
       response = await civi_client.get(
           "Contact",
           select=["id", "display_name", "email_primary.email"],
           where=[["is_deleted", "=", False]],
           limit=pagination.limit,
           offset=pagination.offset,
       )
       return {
           "contacts": response.values,
           "count": response.count,
       }


   @get("/api/contacts/{contact_id:int}")
   async def get_contact(
       contact_id: int,
       civi_client: CiviClient,
   ) -> ContactResponseDTO:
       response = await civi_client.get(
           "Contact",
           where=[["id", "=", contact_id]],
           limit=1,
       )
       if not response.values:
           raise NotFoundException(f"Contact {contact_id} not found")
       return ContactResponseDTO(**response.values[0])


   @post("/api/contacts")
   async def create_contact(
       data: ContactCreateDTO,
       civi_client: CiviClient,
   ) -> ContactResponseDTO:
       response = await civi_client.create("Contact", {
           "first_name": data.first_name,
           "last_name": data.last_name,
           "email_primary": data.email_primary,
           "contact_type": data.contact_type,
       })
       return ContactResponseDTO(**response.values[0])


   config = CiviPluginConfig(
       enable_health_check=True,
   )

   app = Litestar(
       route_handlers=[list_contacts, get_contact, create_contact],
       plugins=[CiviPlugin(config)],
   )


Manual Lifecycle Management
---------------------------

For fine-grained control over client lifecycle:

.. code-block:: python

   from litestar import Litestar
   from civicrm_py.contrib.litestar import (
       provide_civi_client,
       cleanup_client,
       CIVI_CLIENT_STATE_KEY,
   )
   from civicrm_py.core.client import CiviClient
   from civicrm_py.core.config import CiviSettings


   async def on_startup(app: Litestar) -> None:
       settings = CiviSettings.from_env()
       client = CiviClient(settings)
       app.state[CIVI_CLIENT_STATE_KEY] = client


   async def on_shutdown(app: Litestar) -> None:
       await cleanup_client(app)


   app = Litestar(
       route_handlers=[...],
       dependencies={"civi_client": provide_civi_client},
       on_startup=[on_startup],
       on_shutdown=[on_shutdown],
   )


Available Controllers
---------------------

Built-in controllers for common entities:

* ``ContactController``
* ``ActivityController``
* ``ContributionController``
* ``EventController``
* ``MembershipController``
* ``ParticipantController``
* ``GroupController``

Access via:

.. code-block:: python

   from civicrm_py.contrib.litestar import (
       ContactController,
       ActivityController,
       DEFAULT_CONTROLLERS,
       get_entity_controllers,
   )

   # Get all default controllers
   controllers = get_entity_controllers()

   # Or use specific ones
   app = Litestar(
       route_handlers=[ContactController, ActivityController],
       plugins=[CiviPlugin()],
   )


CLI Commands
------------

The plugin registers CLI commands with the Litestar CLI. These commands are available when running ``litestar`` with an application that uses ``CiviPlugin``.

Check Command
^^^^^^^^^^^^^

Verify CiviCRM connection and configuration:

.. code-block:: bash

   # Basic check
   litestar civi check

   # Verbose output with entity listing
   litestar civi check --verbose

   # Quiet mode (only errors)
   litestar civi check --quiet

   # Test with specific entity
   litestar civi check --test-entity Activity

The check command validates:

- Configuration (plugin settings or environment variables)
- API connectivity
- Entity accessibility
- Available entities (with ``--verbose``)

Shell Command
^^^^^^^^^^^^^

Start an interactive Python shell with CiviCRM client pre-configured:

.. code-block:: bash

   # Standard Python shell
   litestar civi shell

   # Use IPython if available
   litestar civi shell --notebook

   # Skip auto-imports
   litestar civi shell --no-startup

The shell provides:

- Pre-configured ``client`` (SyncCiviClient) and ``settings`` objects
- All entity classes imported (Contact, Activity, Contribution, etc.)
- Query utilities (QuerySet, EntityManager)
- Exception classes for error handling

Example session:

.. code-block:: python

   CiviCRM Interactive Shell
   ========================================

   Entities: Activity, Address, Contact, Contribution, ...
   Utilities: CiviClient, SyncCiviClient, EntityDiscovery, QuerySet

   A sync client is available as 'client'.
   Use 'settings' to view current configuration.

   >>> result = client.get('Contact', limit=5)
   >>> for contact in result.values:
   ...     print(contact['display_name'])

Sync Command
^^^^^^^^^^^^

Discover CiviCRM entities and generate Python stubs:

.. code-block:: bash

   # List all available entities
   litestar civi sync --list-entities

   # Filter by entity type
   litestar civi sync --list-entities --filter-type primary

   # Show only custom entities
   litestar civi sync --list-entities --custom-only

   # Inspect a specific entity
   litestar civi sync --entity Contact

   # Show field definitions
   litestar civi sync --entity Contact --show-fields

   # Show available actions
   litestar civi sync --entity Contact --show-actions

   # Generate Python stub file
   litestar civi sync --entity Custom_MyEntity --generate-stub

   # Save stub to file
   litestar civi sync --entity Custom_MyEntity --generate-stub --output my_entity.py

   # Include readonly fields in stub
   litestar civi sync --entity Contact --generate-stub --include-readonly

Generated stubs provide type-safe entity classes:

.. code-block:: python

   """Auto-generated entity stub for CiviCRM.

   Entity: Custom_MyEntity
   Generated by: litestar civi sync --generate-stub
   """

   from __future__ import annotations

   from typing import Any

   from civicrm_py.entities.base import BaseEntity


   class Custom_MyEntity(BaseEntity):
       """CiviCRM Custom_MyEntity entity."""

       __entity_name__ = "Custom_MyEntity"

       id: int
       name: str
       description: str | None = None


SQLSpec Integration
-------------------

Enable local database caching with the sqlspec integration. This requires the ``sqlspec`` extra:

.. code-block:: bash

   pip install 'civicrm-py[litestar,sqlspec]'

Configuration
^^^^^^^^^^^^^

Add SQLSpec configuration to ``CiviPluginConfig``:

.. code-block:: python

   from civicrm_py.contrib.litestar import CiviPlugin, CiviPluginConfig
   from civicrm_py.contrib.litestar.sqlspec_integration import SQLSpecPluginConfig
   from civicrm_py.contrib.sqlspec import CiviSQLSpecConfig

   config = CiviPluginConfig(
       sqlspec=SQLSpecPluginConfig(
           enabled=True,
           sqlspec_config=CiviSQLSpecConfig(
               adapter="aiosqlite",
               database="./civi_cache.db",
           ),
           auto_run_migrations=True,
           provide_repositories=True,
       ),
   )

   app = Litestar(plugins=[CiviPlugin(config)])

Using Repositories
^^^^^^^^^^^^^^^^^^

When ``provide_repositories=True``, repositories are injected automatically:

.. code-block:: python

   from typing import Annotated
   from litestar import get
   from litestar.params import Dependency
   from civicrm_py.contrib.sqlspec import ContactRepository

   @get("/cached-contacts")
   async def list_cached_contacts(
       contact_repository: Annotated[ContactRepository, Dependency(skip_validation=True)],
   ) -> dict:
       async with contact_repository.get_session() as session:
           contacts = await contact_repository.filter(session, is_deleted=False)
           return {"contacts": [c.to_dict() for c in contacts]}

Available repository dependencies:

- ``contact_repository``: ContactRepository
- ``activity_repository``: ActivityRepository
- ``contribution_repository``: ContributionRepository
- ``event_repository``: EventRepository
- ``membership_repository``: MembershipRepository

Sync from Handlers
^^^^^^^^^^^^^^^^^^

Sync CiviCRM data to local cache:

.. code-block:: python

   @post("/sync-contacts")
   async def sync_contacts(
       contact_repository: Annotated[ContactRepository, Dependency(skip_validation=True)],
       civi_client: CiviClient,
   ) -> dict:
       async with contact_repository.get_session() as session:
           result = await contact_repository.sync_from_civi(
               session,
               civi_client,
               is_deleted=False,
               limit=500,
           )
           return {"synced": result.synced_count, "errors": result.error_count}

See :doc:`sqlspec` for complete sqlspec documentation.


Workflow Integration
--------------------

Enable workflow automation with the workflows integration. This requires the ``workflows`` extra:

.. code-block:: bash

   pip install 'civicrm-py[litestar,workflows]'

Configuration
^^^^^^^^^^^^^

Add workflow configuration to ``CiviPluginConfig``:

.. code-block:: python

   from civicrm_py.contrib.litestar import CiviPlugin, CiviPluginConfig
   from civicrm_py.contrib.litestar.workflows_integration import WorkflowPluginConfig

   config = CiviPluginConfig(
       workflows=WorkflowPluginConfig(
           enabled=True,
           api_prefix="/api/workflows",
           register_builtins=True,
           execution_timeout=300,
       ),
   )

   app = Litestar(plugins=[CiviPlugin(config)])

REST API Endpoints
^^^^^^^^^^^^^^^^^^

When enabled, the workflow integration adds these endpoints:

.. list-table::
   :header-rows: 1
   :widths: 15 40 45

   * - Method
     - Path
     - Description
   * - GET
     - ``/api/workflows/``
     - List available workflow definitions
   * - POST
     - ``/api/workflows/{name}/start``
     - Start a new workflow instance
   * - GET
     - ``/api/workflows/instances``
     - List workflow instances
   * - GET
     - ``/api/workflows/instances/{id}``
     - Get instance details and history
   * - POST
     - ``/api/workflows/instances/{id}/complete``
     - Complete a pending human task
   * - GET
     - ``/api/workflows/tasks``
     - List all pending human tasks

Custom Workflows
^^^^^^^^^^^^^^^^

Register custom workflows via the configuration:

.. code-block:: python

   from civicrm_py.contrib.workflows.templates import ContactSyncWorkflow

   config = CiviPluginConfig(
       workflows=WorkflowPluginConfig(
           enabled=True,
           api_prefix="/api/workflows",
           register_builtins=True,
           custom_workflows=[
               ContactSyncWorkflow,
               # Add your custom workflow classes here
           ],
       ),
   )

See :doc:`workflows` for complete workflow documentation.


Combined Integration Example
----------------------------

Use all integrations together:

.. code-block:: python

   from litestar import Litestar, get, post
   from civicrm_py.contrib.litestar import CiviPlugin, CiviPluginConfig
   from civicrm_py.contrib.litestar.sqlspec_integration import SQLSpecPluginConfig
   from civicrm_py.contrib.litestar.workflows_integration import WorkflowPluginConfig
   from civicrm_py.contrib.sqlspec import CiviSQLSpecConfig

   config = CiviPluginConfig(
       # Health check endpoint
       enable_health_check=True,

       # Local database caching
       sqlspec=SQLSpecPluginConfig(
           enabled=True,
           sqlspec_config=CiviSQLSpecConfig(
               adapter="aiosqlite",
               database="./civi_cache.db",
           ),
           auto_run_migrations=True,
       ),

       # Workflow automation
       workflows=WorkflowPluginConfig(
           enabled=True,
           api_prefix="/api/workflows",
           register_builtins=True,
       ),
   )

   app = Litestar(
       route_handlers=[...],
       plugins=[CiviPlugin(config)],
   )
