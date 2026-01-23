Entities
========

CiviCRM organizes data into entities. Each entity type has its own fields and relationships.


Common Entities
---------------

CiviCRM includes dozens of entities. Here are the most common:

.. list-table::
   :widths: 20 80
   :header-rows: 1

   * - Entity
     - Description
   * - Contact
     - People and organizations in your database
   * - Activity
     - Interactions, meetings, calls, emails
   * - Contribution
     - Donations and financial transactions
   * - Membership
     - Membership records
   * - Event
     - Events you organize
   * - Participant
     - Event registrations
   * - Email
     - Email addresses for contacts
   * - Phone
     - Phone numbers for contacts
   * - Address
     - Mailing addresses for contacts
   * - Group
     - Contact groups (smart and static)
   * - Tag
     - Tags for categorizing records
   * - Note
     - Notes attached to records


Contact Types
-------------

Contacts come in three types:

- **Individual**: A person
- **Organization**: A company, nonprofit, government agency
- **Household**: A group of people at the same address

Filter by contact type:

.. code-block:: python

   # Get all organizations
   response = await client.get(
       "Contact",
       where=[["contact_type", "=", "Organization"]],
   )


Field Discovery
---------------

Use ``get_fields`` to discover available fields for any entity:

.. code-block:: python

   fields = await client.get_fields("Contact")
   for field in fields.values:
       print(f"{field['name']}: {field['data_type']}")


Related Fields
--------------

Access related entity fields with dot notation:

.. code-block:: python

   # Get contact with primary email
   response = await client.get(
       "Contact",
       select=["id", "display_name", "email_primary.email"],
   )

Common relationship patterns:

- ``email_primary.email``: Primary email address
- ``phone_primary.phone``: Primary phone number
- ``address_primary.city``: Primary address city


Custom Fields
-------------

Access custom fields using their API name:

.. code-block:: python

   response = await client.get(
       "Contact",
       select=["id", "display_name", "custom_field_1"],
   )

Find custom field names in CiviCRM under Administer > Customize Data and Screens > Custom Fields.
