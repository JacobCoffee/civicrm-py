Bulk Operations
===============

Process large numbers of records efficiently.


Batch Updates
-------------

Update contacts in batches to avoid timeouts:

.. code-block:: python

   async def batch_update_contacts(
       client,
       contact_ids: list[int],
       updates: dict,
       batch_size: int = 50,
   ):
       """Update contacts in batches."""
       for i in range(0, len(contact_ids), batch_size):
           batch = contact_ids[i:i + batch_size]

           await client.update(
               "Contact",
               values=updates,
               where=[["id", "IN", batch]],
           )

           print(f"Updated {min(i + batch_size, len(contact_ids))} of {len(contact_ids)}")


Page Through Results
--------------------

Process all matching records with pagination:

.. code-block:: python

   async def process_all_contacts(client, process_func):
       """Process all contacts in pages."""
       offset = 0
       page_size = 100

       while True:
           response = await client.get(
               "Contact",
               select=["id", "display_name", "email_primary.email"],
               where=[["is_deleted", "=", False]],
               limit=page_size,
               offset=offset,
           )

           if not response.values:
               break

           for contact in response.values:
               await process_func(contact)

           offset += page_size
           print(f"Processed {offset} contacts")


Import with Error Handling
--------------------------

Track successes and failures during import:

.. code-block:: python

   from dataclasses import dataclass
   from civicrm_py import CiviAPIError

   @dataclass
   class ImportResult:
       created: int = 0
       updated: int = 0
       errors: list = None

       def __post_init__(self):
           self.errors = self.errors or []

   async def import_contacts(client, records: list[dict]) -> ImportResult:
       result = ImportResult()

       for record in records:
           try:
               response = await client.create("Contact", values=record)
               result.created += 1
           except CiviAPIError as e:
               result.errors.append({"record": record, "error": str(e)})

       return result
