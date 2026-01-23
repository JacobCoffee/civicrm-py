Installation
============

Install civi-py using your preferred package manager.

.. tab-set::

   .. tab-item:: uv
      :selected:

      .. code-block:: bash

         uv add civi-py

   .. tab-item:: pip

      .. code-block:: bash

         pip install civi-py


Framework Extras
----------------

Install with optional framework integrations to unlock additional features.

.. tab-set::

   .. tab-item:: Django

      .. code-block:: bash

         uv add civi-py[django]
         # or
         pip install civi-py[django]

      Adds middleware, management commands, admin integration, and template tags.

   .. tab-item:: Litestar

      .. code-block:: bash

         uv add civi-py[litestar]
         # or
         pip install civi-py[litestar]

      Adds plugin, dependency injection, routes, and health checks.

   .. tab-item:: Flask

      .. code-block:: bash

         uv add civi-py[flask]
         # or
         pip install civi-py[flask]

      Adds extension and CLI commands.

   .. tab-item:: FastAPI

      .. code-block:: bash

         uv add civi-py[fastapi]
         # or
         pip install civi-py[fastapi]

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

   git clone https://github.com/JacobCoffee/civi-py
   cd civi-py
   uv sync --all-extras
