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

- :class:`~civicrm_py.CiviClient` --- Async client for CiviCRM API
- :class:`~civicrm_py.SyncCiviClient` --- Sync client for CiviCRM API
- :class:`~civicrm_py.CiviSettings` --- Configuration settings

**Request/Response**

- :class:`~civicrm_py.APIRequest` --- Request parameters
- :class:`~civicrm_py.APIResponse` --- API response wrapper

**Exceptions**

- :class:`~civicrm_py.CiviError` --- Base exception
- :class:`~civicrm_py.CiviAPIError` --- API error response
- :class:`~civicrm_py.CiviAuthError` --- Authentication failure
- :class:`~civicrm_py.CiviConnectionError` --- Network error
