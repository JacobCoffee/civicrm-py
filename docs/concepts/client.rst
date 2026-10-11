The Client
==========

civicrm-py provides two client classes for interacting with CiviCRM API v4. Choose based on your codebase.

.. tab-set::

   .. tab-item:: Async
      :selected:

      Use ``CiviClient`` for async/await code:

      .. code-block:: python

         from civicrm_py import CiviClient

         async with CiviClient() as client:
             response = await client.get("Contact")

      The client manages HTTP connections and handles authentication automatically. Always use it as a context manager to ensure connections close properly.

   .. tab-item:: Sync

      Use ``SyncCiviClient`` for traditional synchronous code:

      .. code-block:: python

         from civicrm_py import SyncCiviClient

         with SyncCiviClient() as client:
             response = client.get("Contact")

      The sync client provides the same interface without async/await syntax.


Client Methods
--------------

Both clients provide the same methods:

get(entity, ...)
    Retrieve records with optional filtering, sorting, and pagination.

create(entity, values)
    Create a new record with the given field values.

update(entity, values, where)
    Update records matching the where clause.

delete(entity, where)
    Delete records matching the where clause.

get_fields(entity)
    Get metadata about an entity's fields.

request(entity, action, params)
    Make a raw API request for actions not covered by convenience methods.

request_v3(entity, action, params)
    Make a legacy APIv3 request, for calls with no APIv4 equivalent (such as ``Order.create``).
    Returns an ``APIv3Response``. See `Legacy APIv3`_.


Response Object
---------------

All methods return an ``APIResponse`` object:

.. tab-set::

   .. tab-item:: Async
      :selected:

      .. code-block:: python

         response = await client.get("Contact", limit=10)

         response.values      # List of records
         response.count       # Number of records returned
         response.countFetched  # Total matching records (if available)

   .. tab-item:: Sync

      .. code-block:: python

         response = client.get("Contact", limit=10)

         response.values      # List of records
         response.count       # Number of records returned
         response.countFetched  # Total matching records (if available)

The values are dictionaries with field names as keys:

.. code-block:: python

   for contact in response.values:
       print(contact["id"])
       print(contact["display_name"])
       print(contact.get("email_primary.email"))


Legacy APIv3
------------

Some CiviCRM operations are only exposed through APIv3, most notably ``Order.create``, which
creates a contribution together with its line items and financial transactions. Use
``request_v3`` for these:

.. code-block:: python

   with SyncCiviClient() as client:
       response = client.request_v3("Order", "create", {
           "contact_id": 42,
           "total_amount": 25.00,
           "financial_type_id": 1,
           "contribution_status_id": 2,  # Pending
       })
       contribution_id = response.id

The APIv3 endpoint is derived from ``base_url``: ``https://example.org/civicrm/ajax/api4``
becomes ``https://example.org/civicrm/ajax/rest``. ``request_v3`` raises ``CiviConfigError``
if ``base_url`` does not end in ``/ajax/api4``.

``APIv3Response`` differs from ``APIResponse``:

- ``values`` is keyed by record ID unless you pass ``"sequential": 1``; ``records`` always returns a list.
- ``id`` holds the ID of the created/affected record.
- APIv3 reports errors inside an HTTP 200 body (``is_error: 1``); these are raised as ``CiviAPIError``.


Retries
-------

Requests that never reached CiviCRM (connection refused, connect or pool timeouts) are retried
up to ``max_retries`` times with exponential backoff, for every action.

Read and write timeouts are only retried for read-only actions (those starting with ``get``).
For writes such as ``create``, ``update`` or ``Order.create``, the server may already have
applied the change before the response was lost, so the timeout is raised instead of risking
a duplicate record.


Resource Management
-------------------

The client manages an HTTP connection pool. Use the context manager pattern to ensure cleanup:

.. tab-set::

   .. tab-item:: Async
      :selected:

      .. code-block:: python

         # Good: connection closes automatically
         async with CiviClient() as client:
             await client.get("Contact")

         # Also fine: manual close
         client = CiviClient()
         try:
             await client.get("Contact")
         finally:
             await client.close()

      For long running applications, keep the client open and reuse it:

      .. code-block:: python

         # In your app initialization
         client = CiviClient()

         # Use throughout your app
         await client.get("Contact")

         # Close on shutdown
         await client.close()

   .. tab-item:: Sync

      .. code-block:: python

         # Good: connection closes automatically
         with SyncCiviClient() as client:
             client.get("Contact")

         # Also fine: manual close
         client = SyncCiviClient()
         try:
             client.get("Contact")
         finally:
             client.close()

      For long running applications, keep the client open and reuse it:

      .. code-block:: python

         # In your app initialization
         client = SyncCiviClient()

         # Use throughout your app
         client.get("Contact")

         # Close on shutdown
         client.close()
