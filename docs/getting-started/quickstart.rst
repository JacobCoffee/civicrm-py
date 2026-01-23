Quickstart
==========

This tutorial shows you how to connect to CiviCRM and run your first queries.


Set Up Your Environment
-----------------------

You need three things from your CiviCRM installation:

1. **Base URL**: The API endpoint, usually ``https://yoursite.org/civicrm/ajax/api4``
2. **API Key**: Generate one in CiviCRM under your contact record
3. **Site Key**: Found in your CiviCRM settings (civicrm.settings.php)

Set these as environment variables:

.. code-block:: bash

   export CIVI_BASE_URL=https://yoursite.org/civicrm/ajax/api4
   export CIVI_API_KEY=your_api_key_here
   export CIVI_SITE_KEY=your_site_key_here


Connect and Query
-----------------

The async client:

.. code-block:: python

   import asyncio
   from civi_py import CiviClient

   async def main():
       async with CiviClient() as client:
           # Get first 10 contacts
           response = await client.get("Contact", limit=10)

           print(f"Found {response.count} contacts")
           for contact in response.values:
               print(f"  {contact['id']}: {contact['display_name']}")

   asyncio.run(main())

The sync client for traditional code:

.. code-block:: python

   from civi_py import SyncCiviClient

   with SyncCiviClient() as client:
       response = client.get("Contact", limit=10)

       for contact in response.values:
           print(f"{contact['id']}: {contact['display_name']}")


Filter and Select
-----------------

Get specific fields for contacts matching criteria:

.. code-block:: python

   async with CiviClient() as client:
       # Select specific fields
       response = await client.get(
           "Contact",
           select=["id", "display_name", "email_primary.email"],
           where=[
               ["contact_type", "=", "Individual"],
               ["is_deleted", "=", False],
           ],
           limit=25,
       )


Create Records
--------------

Create a new contact:

.. code-block:: python

   async with CiviClient() as client:
       response = await client.create(
           "Contact",
           values={
               "contact_type": "Individual",
               "first_name": "Jane",
               "last_name": "Doe",
               "email_primary.email": "jane@example.org",
           },
       )
       new_contact = response.values[0]
       print(f"Created contact {new_contact['id']}")


Update Records
--------------

Update existing records by ID:

.. code-block:: python

   async with CiviClient() as client:
       await client.update(
           "Contact",
           values={"preferred_communication_method": ["Email"]},
           where=[["id", "=", 123]],
       )


Delete Records
--------------

Delete records matching criteria:

.. code-block:: python

   async with CiviClient() as client:
       await client.delete(
           "Contact",
           where=[["id", "=", 123]],
       )


Handle Errors
-------------

Catch specific exceptions:

.. code-block:: python

   from civi_py import CiviClient, CiviAPIError, CiviConnectionError

   async with CiviClient() as client:
       try:
           response = await client.get("Contact", where=[["id", "=", 999999]])
       except CiviConnectionError:
           print("Could not connect to CiviCRM")
       except CiviAPIError as e:
           print(f"API error: {e}")


Next Steps
----------

- :doc:`configuration` for all configuration options
- :doc:`/concepts/index` for deeper understanding
- :doc:`/guides/index` for framework integrations
