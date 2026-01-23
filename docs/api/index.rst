API Reference
=============

Complete documentation for all public classes and functions.

.. toctree::
   :maxdepth: 2

   client
   config
   serialization
   exceptions


Quick Links
-----------

**Core Classes**

- :class:`~civi_py.CiviClient` --- Async client for CiviCRM API
- :class:`~civi_py.SyncCiviClient` --- Sync client for CiviCRM API
- :class:`~civi_py.CiviSettings` --- Configuration settings

**Request/Response**

- :class:`~civi_py.APIRequest` --- Request parameters
- :class:`~civi_py.APIResponse` --- API response wrapper

**Exceptions**

- :class:`~civi_py.CiviError` --- Base exception
- :class:`~civi_py.CiviAPIError` --- API error response
- :class:`~civi_py.CiviAuthError` --- Authentication failure
- :class:`~civi_py.CiviConnectionError` --- Network error
