FastAPI Integration
===================

Integration for FastAPI with lifespan management, dependency injection, and auto-generated routes.

Installation
------------

Install with the FastAPI extra:

.. code-block:: bash

   pip install civicrm-py[fastapi]


Basic Setup
-----------

Use the lifespan context manager and dependency injection:

.. code-block:: python

   from fastapi import FastAPI, Depends
   from civicrm_py.core.client import CiviClient
   from civicrm_py.contrib.fastapi import civi_lifespan, get_civi_client

   app = FastAPI(lifespan=civi_lifespan)


   @app.get("/contacts")
   async def list_contacts(client: CiviClient = Depends(get_civi_client)):
       response = await client.get("Contact", limit=10)
       return {"contacts": response.values}

The lifespan handler:

* Initializes the client on startup from environment variables
* Stores the client in ``app.state``
* Closes the client on shutdown


Environment Variables
---------------------

Set these environment variables for automatic configuration:

.. code-block:: bash

   CIVI_BASE_URL=https://example.org/civicrm/ajax/api4
   CIVI_API_KEY=your-api-key
   CIVI_SITE_KEY=your-site-key    # Optional
   CIVI_TIMEOUT=30                # Default: 30 seconds
   CIVI_VERIFY_SSL=true           # Default: true


Custom Configuration
--------------------

Use ``CiviFastAPIConfig`` for custom settings:

.. code-block:: python

   from fastapi import FastAPI
   from civicrm_py.core.config import CiviSettings
   from civicrm_py.contrib.fastapi import CiviFastAPIConfig, create_civi_lifespan

   config = CiviFastAPIConfig(
       settings=CiviSettings(
           base_url="https://example.org/civicrm/ajax/api4",
           api_key="your-api-key",
           timeout=60,
       ),
       api_prefix="/api/civi",
       enable_health_check=True,
       debug=False,
   )

   app = FastAPI(lifespan=create_civi_lifespan(config))

Configuration options:

.. list-table::
   :header-rows: 1

   * - Option
     - Default
     - Description
   * - ``settings``
     - None
     - CiviSettings instance. If None, loads from environment.
   * - ``api_prefix``
     - ``/api/civi``
     - Prefix for auto-generated routes. Set to None to disable.
   * - ``enable_health_check``
     - True
     - Enable the health check endpoint.
   * - ``health_check_path``
     - ``/health/civi``
     - Path for the health check endpoint.
   * - ``openapi_tags``
     - ``["CiviCRM"]``
     - Tags for generated routes in OpenAPI docs.
   * - ``include_entities``
     - None
     - Entities to include. If None, includes all default entities.
   * - ``exclude_entities``
     - ``[]``
     - Entities to exclude from route generation.
   * - ``debug``
     - False
     - Enable debug logging.


Dependency Injection
--------------------

Basic Dependency
^^^^^^^^^^^^^^^^

Use ``Depends(get_civi_client)`` to inject the client:

.. code-block:: python

   from fastapi import FastAPI, Depends
   from civicrm_py.core.client import CiviClient
   from civicrm_py.contrib.fastapi import civi_lifespan, get_civi_client

   app = FastAPI(lifespan=civi_lifespan)


   @app.get("/contacts")
   async def list_contacts(client: CiviClient = Depends(get_civi_client)):
       response = await client.get("Contact", limit=10)
       return {"contacts": response.values}


   @app.get("/contacts/{contact_id}")
   async def get_contact(
       contact_id: int,
       client: CiviClient = Depends(get_civi_client),
   ):
       response = await client.get(
           "Contact",
           where=[["id", "=", contact_id]],
           limit=1,
       )
       if not response.values:
           from fastapi import HTTPException
           raise HTTPException(status_code=404, detail="Contact not found")
       return response.values[0]

Type Alias
^^^^^^^^^^

Use the ``CiviClientDep`` type alias for cleaner code:

.. code-block:: python

   from civicrm_py.contrib.fastapi import CiviClientDep


   @app.get("/contacts")
   async def list_contacts(client: CiviClientDep):
       response = await client.get("Contact", limit=10)
       return {"contacts": response.values}


Auto-Generated Routes
---------------------

Create CRUD routes using the router factory:

.. code-block:: python

   from fastapi import FastAPI
   from civicrm_py.contrib.fastapi import (
       civi_lifespan,
       create_civi_router,
       CiviFastAPIConfig,
   )

   config = CiviFastAPIConfig(
       api_prefix="/api/civi",
       include_entities=["Contact", "Activity", "Contribution"],
   )

   app = FastAPI(lifespan=civi_lifespan)
   app.include_router(create_civi_router(config))

Generated routes for each entity:

.. list-table::
   :header-rows: 1

   * - Method
     - Path
     - Action
   * - GET
     - ``/api/civi/contacts``
     - List contacts
   * - GET
     - ``/api/civi/contacts/{id}``
     - Get single contact
   * - POST
     - ``/api/civi/contacts``
     - Create contact
   * - PUT
     - ``/api/civi/contacts/{id}``
     - Update contact
   * - DELETE
     - ``/api/civi/contacts/{id}``
     - Delete contact

Default entities: Contact, Activity, Contribution, Event, Membership, Participant, Group.

Individual Entity Routers
^^^^^^^^^^^^^^^^^^^^^^^^^

Create routers for specific entities:

.. code-block:: python

   from civicrm_py.contrib.fastapi import (
       create_contact_router,
       create_entity_router,
   )

   # Contact-specific router with typed models
   app.include_router(create_contact_router(), prefix="/api")

   # Generic router for any entity
   app.include_router(
       create_entity_router("Activity"),
       prefix="/api",
   )

   # Custom entity
   app.include_router(
       create_entity_router(
           "CustomEntity",
           prefix="/custom-entities",
           tags=["Custom"],
       ),
       prefix="/api",
   )


Health Check
------------

Enable the health check endpoint:

.. code-block:: python

   config = CiviFastAPIConfig(enable_health_check=True)

The ``GET /health/civi`` endpoint returns:

.. code-block:: json

   {
       "status": "healthy",
       "civi_connected": true,
       "response_time_ms": 45.2,
       "api_version": "4",
       "timestamp": "2025-01-22T10:30:00Z"
   }

When unhealthy (returns 503):

.. code-block:: json

   {
       "status": "unhealthy",
       "civi_connected": false,
       "timestamp": "2025-01-22T10:30:00Z",
       "error": "Connection refused"
   }

Custom Health Check Router
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from civicrm_py.contrib.fastapi import create_health_check_router

   app.include_router(
       create_health_check_router(
           path="/status/civicrm",
           tags=["Status"],
       )
   )


Pydantic Models
---------------

The integration provides Pydantic models for request/response validation.

Contact Models
^^^^^^^^^^^^^^

.. code-block:: python

   from civicrm_py.contrib.fastapi import (
       ContactCreate,
       ContactUpdate,
       ContactResponse,
   )


   @app.post("/contacts", response_model=ContactResponse)
   async def create_contact(data: ContactCreate, client: CiviClientDep):
       response = await client.create(
           "Contact",
           data.model_dump(exclude_unset=True),
       )
       return ContactResponse(**response.values[0])


   @app.put("/contacts/{contact_id}", response_model=ContactResponse)
   async def update_contact(
       contact_id: int,
       data: ContactUpdate,
       client: CiviClientDep,
   ):
       response = await client.update(
           "Contact",
           values=data.model_dump(exclude_unset=True),
           where=[["id", "=", contact_id]],
       )
       return ContactResponse(**response.values[0])

Available Models
^^^^^^^^^^^^^^^^

Contact: ``ContactBase``, ``ContactCreate``, ``ContactUpdate``, ``ContactResponse``

Activity: ``ActivityBase``, ``ActivityCreate``, ``ActivityUpdate``, ``ActivityResponse``

Contribution: ``ContributionBase``, ``ContributionCreate``, ``ContributionUpdate``, ``ContributionResponse``

Event: ``EventBase``, ``EventCreate``, ``EventUpdate``, ``EventResponse``

Membership: ``MembershipBase``, ``MembershipCreate``, ``MembershipUpdate``, ``MembershipResponse``

Response Wrapper: ``APIResponse``, ``HealthCheckResponse``, ``PaginationParams``


Complete Example
----------------

.. code-block:: python

   from fastapi import FastAPI, HTTPException, Query
   from typing import Annotated
   from civicrm_py.contrib.fastapi import (
       civi_lifespan,
       CiviClientDep,
       ContactCreate,
       ContactUpdate,
       ContactResponse,
       APIResponse,
       create_health_check_router,
   )

   app = FastAPI(
       title="CiviCRM API",
       lifespan=civi_lifespan,
   )

   # Health check
   app.include_router(create_health_check_router())


   @app.get("/api/contacts", response_model=APIResponse)
   async def list_contacts(
       client: CiviClientDep,
       limit: Annotated[int, Query(ge=1, le=100)] = 25,
       offset: Annotated[int, Query(ge=0)] = 0,
       contact_type: str | None = None,
       search: str | None = None,
   ):
       where = [["is_deleted", "=", False]]

       if contact_type:
           where.append(["contact_type", "=", contact_type])
       if search:
           where.append(["display_name", "CONTAINS", search])

       response = await client.get(
           "Contact",
           select=["id", "display_name", "email_primary.email", "contact_type"],
           where=where,
           limit=limit,
           offset=offset,
       )

       return APIResponse(
           values=response.values or [],
           count=response.count or 0,
           count_fetched=response.countFetched or 0,
       )


   @app.get("/api/contacts/{contact_id}", response_model=ContactResponse)
   async def get_contact(contact_id: int, client: CiviClientDep):
       response = await client.get(
           "Contact",
           where=[["id", "=", contact_id]],
           limit=1,
       )

       if not response.values:
           raise HTTPException(status_code=404, detail="Contact not found")

       return ContactResponse(**response.values[0])


   @app.post("/api/contacts", response_model=ContactResponse, status_code=201)
   async def create_contact(data: ContactCreate, client: CiviClientDep):
       values = data.model_dump(exclude_unset=True)
       response = await client.create("Contact", values)

       if not response.values:
           raise HTTPException(status_code=500, detail="Failed to create contact")

       return ContactResponse(**response.values[0])


   @app.put("/api/contacts/{contact_id}", response_model=ContactResponse)
   async def update_contact(
       contact_id: int,
       data: ContactUpdate,
       client: CiviClientDep,
   ):
       values = data.model_dump(exclude_unset=True)

       response = await client.update(
           "Contact",
           values=values,
           where=[["id", "=", contact_id]],
       )

       if not response.values:
           raise HTTPException(status_code=404, detail="Contact not found")

       return ContactResponse(**response.values[0])


   @app.delete("/api/contacts/{contact_id}", status_code=204)
   async def delete_contact(contact_id: int, client: CiviClientDep):
       response = await client.delete(
           "Contact",
           where=[["id", "=", contact_id]],
       )

       if response.count == 0:
           raise HTTPException(status_code=404, detail="Contact not found")


Using ASGI Middleware
---------------------

As an alternative to lifespan handlers, use the generic ASGI middleware:

.. code-block:: python

   from fastapi import FastAPI, Request
   from civicrm_py.contrib.asgi import CiviASGIMiddleware
   from civicrm_py.core.config import CiviSettings

   app = FastAPI()

   settings = CiviSettings(
       base_url="https://example.org/civicrm/ajax/api4",
       api_key="your-api-key",
   )

   app.add_middleware(CiviASGIMiddleware, settings=settings)


   @app.get("/contacts")
   async def list_contacts(request: Request):
       client = request.state.civi_client
       response = await client.get("Contact", limit=10)
       return {"contacts": response.values}

See :doc:`other` for more details on the ASGI middleware.
