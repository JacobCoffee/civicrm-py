Installation
============

Install civicrm-py using your preferred package manager.

.. tab-set::

   .. tab-item:: uv
      :selected:

      .. code-block:: bash

         uv add civicrm-py

   .. tab-item:: pip

      .. code-block:: bash

         pip install civicrm-py


Framework Extras
----------------

Install with optional framework integrations to unlock additional features.

.. tab-set::

   .. tab-item:: Django

      .. code-block:: bash

         uv add civicrm-py[django]
         # or
         pip install civicrm-py[django]

      Adds middleware, management commands, admin integration, and template tags.

   .. tab-item:: Litestar

      .. code-block:: bash

         uv add civicrm-py[litestar]
         # or
         pip install civicrm-py[litestar]

      Adds plugin, dependency injection, routes, and health checks.

   .. tab-item:: Flask

      .. code-block:: bash

         uv add civicrm-py[flask]
         # or
         pip install civicrm-py[flask]

      Adds extension and CLI commands.

   .. tab-item:: FastAPI

      .. code-block:: bash

         uv add civicrm-py[fastapi]
         # or
         pip install civicrm-py[fastapi]

      Adds dependency injection helpers.


Requirements
------------

- Python 3.11 or later
- httpx for HTTP requests
- msgspec for serialization

Optional dependencies vary by framework integration.


From Source
-----------

Clone and install for development:

.. code-block:: bash

   git clone https://github.com/JacobCoffee/civicrm-py
   cd civicrm-py
   uv sync --all-extras
