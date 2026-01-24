Error Handling
==============

civicrm-py raises specific exceptions for different error conditions.


Exception Hierarchy
-------------------

All civicrm-py exceptions inherit from ``CiviError``:

.. code-block:: text

   CiviError
   ├── CiviConfigError      # Configuration problems
   ├── CiviConnectionError  # Network failures
   ├── CiviTimeoutError     # Request timeout
   ├── CiviAuthError        # Authentication failed
   ├── CiviAPIError         # API returned an error
   │   ├── CiviNotFoundError     # Record not found
   │   ├── CiviValidationError   # Invalid data
   │   └── CiviPermissionError   # Permission denied


Catching Exceptions
-------------------

Catch specific exceptions for targeted handling:

.. code-block:: python

   from civicrm_py import (
       CiviClient,
       CiviConnectionError,
       CiviAuthError,
       CiviAPIError,
   )

   async with CiviClient() as client:
       try:
           response = await client.get("Contact")
       except CiviConnectionError:
           # Network problem, maybe retry later
           print("Cannot reach CiviCRM server")
       except CiviAuthError:
           # Bad credentials
           print("Check your API key")
       except CiviAPIError as e:
           # CiviCRM returned an error
           print(f"API error: {e}")


CiviConnectionError
-------------------

Raised when the HTTP request fails:

- Server unreachable
- DNS resolution failed
- Connection refused

.. code-block:: python

   try:
       await client.get("Contact")
   except CiviConnectionError:
       # Server down or network issue
       pass


CiviTimeoutError
----------------

Raised when the request exceeds the timeout:

.. code-block:: python

   try:
       await client.get("Contact")
   except CiviTimeoutError:
       # Request took too long
       pass


CiviAuthError
-------------

Raised when authentication fails:

- Invalid API key
- Invalid site key
- Expired JWT token

.. code-block:: python

   try:
       await client.get("Contact")
   except CiviAuthError:
       # Bad credentials
       pass


CiviAPIError
------------

Raised when CiviCRM returns an error response. Includes the error message from the API:

.. code-block:: python

   try:
       await client.create("Contact", values={"invalid_field": "value"})
   except CiviAPIError as e:
       print(f"Error: {e}")


CiviNotFoundError
~~~~~~~~~~~~~~~~~

Raised when a requested record does not exist:

.. code-block:: python

   try:
       await client.get("Contact", where=[["id", "=", 999999]])
   except CiviNotFoundError:
       print("Contact not found")


CiviValidationError
~~~~~~~~~~~~~~~~~~~

Raised when data validation fails:

.. code-block:: python

   try:
       await client.create("Contact", values={})  # Missing required fields
   except CiviValidationError as e:
       print(f"Invalid data: {e}")


CiviPermissionError
~~~~~~~~~~~~~~~~~~~

Raised when the API key lacks permission:

.. code-block:: python

   try:
       await client.delete("Contact", where=[["id", "=", 1]])
   except CiviPermissionError:
       print("Not allowed to delete contacts")


Retry Behavior
--------------

The client automatically retries on transient failures. Configure retry count:

.. code-block:: python

   client = CiviClient(max_retries=5)

Retried errors:

- Connection timeouts
- 503 Service Unavailable
- 502 Bad Gateway
- 504 Gateway Timeout

Not retried:

- Authentication errors
- Validation errors
- Permission errors
- 4xx client errors
