Contact Sync
============

Sync contacts from external systems into CiviCRM.


Find or Create Contact
----------------------

Check if a contact exists before creating:

.. code-block:: python

   async def find_or_create_contact(
       client,
       email: str,
       first_name: str,
       last_name: str,
   ) -> dict:
       """Find existing contact by email or create new one."""
       # Search by email
       response = await client.get(
           "Contact",
           select=["id", "display_name"],
           where=[["email_primary.email", "=", email]],
           limit=1,
       )

       if response.values:
           return response.values[0]

       # Create new contact
       response = await client.create(
           "Contact",
           values={
               "contact_type": "Individual",
               "first_name": first_name,
               "last_name": last_name,
               "email_primary.email": email,
           },
       )
       return response.values[0]


Sync from CSV
-------------

Import contacts from a CSV file:

.. code-block:: python

   import csv
   from civi_py import CiviClient

   async def sync_contacts_from_csv(filepath: str):
       async with CiviClient() as client:
           with open(filepath) as f:
               reader = csv.DictReader(f)

               for row in reader:
                   contact = await find_or_create_contact(
                       client,
                       email=row["email"],
                       first_name=row["first_name"],
                       last_name=row["last_name"],
                   )
                   print(f"Synced: {contact['display_name']}")


Update on Sync
--------------

Update existing contacts with new data:

.. code-block:: python

   async def sync_with_update(client, email: str, data: dict) -> dict:
       """Find contact and update, or create new."""
       response = await client.get(
           "Contact",
           select=["id"],
           where=[["email_primary.email", "=", email]],
           limit=1,
       )

       if response.values:
           contact_id = response.values[0]["id"]
           await client.update(
               "Contact",
               values=data,
               where=[["id", "=", contact_id]],
           )
           return {"id": contact_id, "action": "updated"}

       data["contact_type"] = "Individual"
       data["email_primary.email"] = email
       response = await client.create("Contact", values=data)
       return {"id": response.values[0]["id"], "action": "created"}
