Events
======

Create events and manage registrations.


Create an Event
---------------

.. code-block:: python

   async def create_event(
       client,
       title: str,
       start_date: str,
       event_type: str = "Workshop",
   ) -> dict:
       response = await client.create(
           "Event",
           values={
               "title": title,
               "event_type_id:name": event_type,
               "start_date": start_date,
               "is_active": True,
               "is_public": True,
           },
       )
       return response.values[0]


Register a Participant
----------------------

.. code-block:: python

   from datetime import date

   async def register_participant(
       client,
       event_id: int,
       contact_id: int,
       status: str = "Registered",
   ) -> dict:
       response = await client.create(
           "Participant",
           values={
               "event_id": event_id,
               "contact_id": contact_id,
               "status_id:name": status,
               "register_date": date.today().isoformat(),
           },
       )
       return response.values[0]


Get Event Attendees
-------------------

.. code-block:: python

   async def get_attendees(client, event_id: int) -> list:
       response = await client.get(
           "Participant",
           select=[
               "id",
               "contact_id.display_name",
               "contact_id.email_primary.email",
               "status_id:name",
           ],
           where=[["event_id", "=", event_id]],
       )
       return response.values
