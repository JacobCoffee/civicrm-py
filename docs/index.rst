civi-py
=======

.. rst-class:: lead

   Modern Python client for CiviCRM API v4 with async support and web framework integrations.

----

**civi-py** gives you a clean, typed Python interface to CiviCRM. It works async or sync,
plays well with Django, Litestar, Flask, and FastAPI, and uses msgspec for fast serialization.

.. grid:: 1 1 2 2
   :gutter: 2

   .. grid-item-card:: Getting Started
      :link: getting-started/index
      :link-type: doc

      Install civi-py and make your first API call in five minutes.

   .. grid-item-card:: Core Concepts
      :link: concepts/index
      :link-type: doc

      Learn about the client, queries, entities, and error handling.

   .. grid-item-card:: Framework Guides
      :link: guides/index
      :link-type: doc

      Integrate with Django, Litestar, Flask, FastAPI, and other frameworks.

   .. grid-item-card:: API Reference
      :link: api/index
      :link-type: doc

      Complete documentation for all public classes and functions.

   .. grid-item-card:: Cookbook
      :link: cookbook/index
      :link-type: doc

      Real examples for common CiviCRM tasks like contact sync, bulk updates, and reporting.


Key Features
------------

- **Async and Sync**: Use ``CiviClient`` for async code or ``SyncCiviClient`` for traditional apps
- **Type Safe**: Full type hints with msgspec models for IDE support and validation
- **Framework Integrations**: First class support for Django, Litestar, Flask, FastAPI
- **Retries and Timeouts**: Built in retry logic and configurable timeouts
- **Clean API**: Simple methods for get, create, update, delete operations


Quick Example
-------------

.. tab-set::

   .. tab-item:: Async

      .. code-block:: python

         from civi_py import CiviClient

         async with CiviClient(base_url="...", api_key="...") as client:
             response = await client.get("Contact", limit=10)
             for contact in response.values:
                 print(contact["display_name"])

   .. tab-item:: Sync

      .. code-block:: python

         from civi_py import SyncCiviClient

         with SyncCiviClient(base_url="...", api_key="...") as client:
             response = client.get("Contact", limit=10)
             for contact in response.values:
                 print(contact["display_name"])


Installation
------------

.. code-block:: bash

   pip install civi-py

   # With framework extras
   pip install civi-py[django]    # Django integration
   pip install civi-py[litestar]  # Litestar integration
   pip install civi-py[flask]     # Flask integration
   pip install civi-py[fastapi]   # FastAPI integration

   # With ecosystem extras
   pip install civi-py[sqlspec]   # Local database caching
   pip install civi-py[workflows] # Workflow automation

   # Combined extras
   pip install 'civi-py[litestar,sqlspec,workflows]'


.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: Learn

   getting-started/index
   concepts/index
   guides/index
   cookbook/index

.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: Reference

   api/index
   changelog

.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: Contributing

   contributing/index

.. toctree::
   :hidden:
   :caption: Project

   GitHub <https://github.com/JacobCoffee/civi-py>
   CiviCRM <https://civicrm.org/>


Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
