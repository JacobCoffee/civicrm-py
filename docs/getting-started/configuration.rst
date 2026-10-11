Configuration
=============

civicrm-py reads configuration from environment variables or accepts parameters directly.


Environment Variables
---------------------

.. list-table::
   :widths: 25 15 60
   :header-rows: 1

   * - Variable
     - Required
     - Description
   * - ``CIVI_BASE_URL``
     - Yes
     - CiviCRM API endpoint (e.g., ``https://example.org/civicrm/ajax/api4``)
   * - ``CIVI_API_KEY``
     - Yes*
     - API key for authentication
   * - ``CIVI_SITE_KEY``
     - No
     - Site key, sent as ``X-Civi-Key`` (satisfies AuthX's site-key guard)
   * - ``CIVI_TIMEOUT``
     - No
     - Request timeout in seconds (default: 30)
   * - ``CIVI_VERIFY_SSL``
     - No
     - Verify SSL certificates (default: true)
   * - ``CIVI_DEBUG``
     - No
     - Enable debug logging (default: false)
   * - ``CIVI_MAX_RETRIES``
     - No
     - Retry attempts for failed requests (default: 3)
   * - ``CIVI_AUTH_TYPE``
     - No
     - Authentication type: api_key, jwt, or basic (default: api_key)

\* Required when using api_key authentication


Programmatic Configuration
--------------------------

Pass settings directly to the client:

.. code-block:: python

   from civicrm_py import CiviClient

   client = CiviClient(
       base_url="https://example.org/civicrm/ajax/api4",
       api_key="your_key",
       site_key="your_site_key",
       timeout=60,
       max_retries=5,
   )

Or use a settings object:

.. code-block:: python

   from civicrm_py import CiviClient, CiviSettings

   settings = CiviSettings(
       base_url="https://example.org/civicrm/ajax/api4",
       api_key="your_key",
       timeout=60,
   )

   client = CiviClient(settings=settings)


Authentication Types
--------------------

API Key (Default)
~~~~~~~~~~~~~~~~~

Most common method. Get your API key from CiviCRM:

1. Go to your contact record
2. Click the API Key tab
3. Generate or copy your key

.. code-block:: bash

   export CIVI_AUTH_TYPE=api_key
   export CIVI_API_KEY=your_key_here


JWT Token
~~~~~~~~~

For installations using JWT authentication:

.. code-block:: bash

   export CIVI_AUTH_TYPE=jwt
   export CIVI_JWT_TOKEN=your_jwt_token


Basic Auth
~~~~~~~~~~

For installations behind basic auth:

.. code-block:: bash

   export CIVI_AUTH_TYPE=basic
   export CIVI_USERNAME=your_username
   export CIVI_PASSWORD=your_password


Framework Settings
------------------

See the framework guides for integration specific settings:

- :doc:`/guides/django` for Django settings
- :doc:`/guides/litestar` for Litestar configuration
- :doc:`/guides/flask` for Flask configuration
