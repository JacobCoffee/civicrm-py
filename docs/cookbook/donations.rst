Donations
=========

Record and manage contributions.


Record a Donation
-----------------

Create a contribution for a contact:

.. code-block:: python

   from datetime import date

   async def record_donation(
       client,
       contact_id: int,
       amount: float,
       financial_type: str = "Donation",
   ) -> dict:
       response = await client.create(
           "Contribution",
           values={
               "contact_id": contact_id,
               "total_amount": amount,
               "financial_type_id:name": financial_type,
               "receive_date": date.today().isoformat(),
               "contribution_status_id:name": "Completed",
           },
       )
       return response.values[0]


Donation with New Contact
-------------------------

Create contact and donation together:

.. code-block:: python

   async def process_online_donation(
       client,
       email: str,
       first_name: str,
       last_name: str,
       amount: float,
   ):
       # Find or create contact
       contact_response = await client.get(
           "Contact",
           select=["id"],
           where=[["email_primary.email", "=", email]],
           limit=1,
       )

       if contact_response.values:
           contact_id = contact_response.values[0]["id"]
       else:
           contact_result = await client.create(
               "Contact",
               values={
                   "contact_type": "Individual",
                   "first_name": first_name,
                   "last_name": last_name,
                   "email_primary.email": email,
               },
           )
           contact_id = contact_result.values[0]["id"]

       # Record donation
       donation = await record_donation(client, contact_id, amount)
       return {"contact_id": contact_id, "contribution_id": donation["id"]}


Donation Summary
----------------

Get donation totals for a contact:

.. code-block:: python

   async def get_donation_summary(client, contact_id: int) -> dict:
       response = await client.get(
           "Contribution",
           select=["total_amount", "receive_date"],
           where=[
               ["contact_id", "=", contact_id],
               ["contribution_status_id:name", "=", "Completed"],
           ],
       )

       total = sum(c["total_amount"] for c in response.values)
       count = len(response.values)

       return {"total": total, "count": count, "contributions": response.values}
