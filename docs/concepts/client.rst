The Client
==========

civi-py provides two client classes for interacting with CiviCRM API v4. Choose based on your codebase.

.. tab-set::

   .. tab-item:: Async
      :selected:

      Use ``CiviClient`` for async/await code:

      .. code-block:: python

         from civi_py import CiviClient

         async with CiviClient() as client:
             response = await client.get("Contact")

      The client manages HTTP connections and handles authentication automatically. Always use it as a context manager to ensure connections close properly.

   .. tab-item:: Sync

      Use ``SyncCiviClient`` for traditional synchronous code:

      .. code-block:: python

         from civi_py import SyncCiviClient

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
