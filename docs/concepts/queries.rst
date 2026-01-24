Queries
=======

CiviCRM API v4 uses a structured query format. civicrm-py provides convenience parameters that translate to the underlying API.


Basic Query
-----------

Get all records from an entity:

.. code-block:: python

   response = await client.get("Contact")


Selecting Fields
----------------

By default, CiviCRM returns all fields. Use ``select`` to get specific fields:

.. code-block:: python

   response = await client.get(
       "Contact",
       select=["id", "display_name", "email_primary.email"],
   )

Use dot notation to access related fields like ``email_primary.email``.


Filtering with Where
--------------------

The ``where`` parameter takes a list of conditions. Each condition is a list with three elements: field, operator, value.

.. code-block:: python

   # Single condition
   response = await client.get(
       "Contact",
       where=[["contact_type", "=", "Individual"]],
   )

   # Multiple conditions (AND)
   response = await client.get(
       "Contact",
       where=[
           ["contact_type", "=", "Individual"],
           ["is_deleted", "=", False],
       ],
   )


Operators
~~~~~~~~~

Common operators:

.. list-table::
   :widths: 20 80
   :header-rows: 1

   * - Operator
     - Description
   * - ``=``
     - Equals
   * - ``!=``
     - Not equals
   * - ``>``
     - Greater than
   * - ``>=``
     - Greater than or equal
   * - ``<``
     - Less than
   * - ``<=``
     - Less than or equal
   * - ``LIKE``
     - Pattern match (use % as wildcard)
   * - ``CONTAINS``
     - Substring match (case insensitive)
   * - ``NOT CONTAINS``
     - Inverse substring match
   * - ``IN``
     - Value in list
   * - ``NOT IN``
     - Value not in list
   * - ``IS NULL``
     - Field is null
   * - ``IS NOT NULL``
     - Field is not null

Examples:

.. code-block:: python

   # Pattern matching with wildcard
   where=[["display_name", "LIKE", "Smith%"]]

   # Substring matching (case insensitive)
   where=[["display_name", "CONTAINS", "smith"]]

   # In list
   where=[["contact_type", "IN", ["Individual", "Organization"]]]

   # Null check
   where=[["email_primary.email", "IS NOT NULL", True]]


Ordering
--------

Sort results with ``order_by``:

.. code-block:: python

   response = await client.get(
       "Contact",
       order_by={"display_name": "ASC"},
   )

   # Multiple sort fields
   response = await client.get(
       "Contact",
       order_by={"last_name": "ASC", "first_name": "ASC"},
   )

Use ``ASC`` for ascending or ``DESC`` for descending.


Pagination
----------

Use ``limit`` and ``offset`` for pagination:

.. code-block:: python

   # First page
   response = await client.get("Contact", limit=25, offset=0)

   # Second page
   response = await client.get("Contact", limit=25, offset=25)


Raw Requests
------------

For full control, use the ``request`` method directly:

.. code-block:: python

   from civicrm_py import APIRequest

   params = APIRequest(
       select=["id", "display_name"],
       where=[["contact_type", "=", "Individual"]],
       orderBy={"display_name": "ASC"},
       limit=25,
   )

   response = await client.request("Contact", "get", params)

This gives access to any CiviCRM action (get, create, update, delete, save, getFields, etc).
