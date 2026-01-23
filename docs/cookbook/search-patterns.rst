Search Patterns
===============

Advanced query techniques for CiviCRM.


Search by Custom Fields
-----------------------

.. code-block:: python

   # Custom fields use their API name
   response = await client.get(
       "Contact",
       select=["id", "display_name", "custom_volunteer_status"],
       where=[["custom_volunteer_status", "=", "Active"]],
   )


Date Range Queries
------------------

.. code-block:: python

   from datetime import date, timedelta

   # Contacts created in the last 30 days
   cutoff = (date.today() - timedelta(days=30)).isoformat()

   response = await client.get(
       "Contact",
       select=["id", "display_name", "created_date"],
       where=[["created_date", ">=", cutoff]],
       order_by={"created_date": "DESC"},
   )


Pattern Matching
----------------

.. code-block:: python

   # Names starting with "Smith"
   response = await client.get(
       "Contact",
       where=[["last_name", "LIKE", "Smith%"]],
   )

   # Email containing "gmail"
   response = await client.get(
       "Contact",
       where=[["email_primary.email", "LIKE", "%gmail%"]],
   )


Null Checks
-----------

.. code-block:: python

   # Contacts with email
   response = await client.get(
       "Contact",
       where=[["email_primary.email", "IS NOT NULL", True]],
   )

   # Contacts without phone
   response = await client.get(
       "Contact",
       where=[["phone_primary.phone", "IS NULL", True]],
   )


Combining Conditions
--------------------

All conditions in the where list are AND conditions:

.. code-block:: python

   response = await client.get(
       "Contact",
       where=[
           ["contact_type", "=", "Individual"],
           ["is_deleted", "=", False],
           ["email_primary.email", "IS NOT NULL", True],
           ["created_date", ">=", "2024-01-01"],
       ],
   )


Performance Tips
----------------

1. **Select only needed fields**: Reduces data transfer

   .. code-block:: python

      # Good: only get what you need
      select=["id", "display_name"]

      # Avoid: getting all fields
      select=None  # default

2. **Use limits**: Avoid loading entire database

   .. code-block:: python

      response = await client.get("Contact", limit=100)

3. **Filter early**: Let CiviCRM filter, not your code

   .. code-block:: python

      # Good: filter in query
      where=[["contact_type", "=", "Individual"]]

      # Avoid: filtering in Python after fetch
