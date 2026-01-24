civicrm-py
==========

.. rst-class:: lead

   Modern Python client for CiviCRM API v4 with async support and web framework integrations.

----

**civicrm-py** gives you a clean, typed Python interface to CiviCRM. It works async or sync,
plays well with Django, Litestar, Flask, and FastAPI, and uses msgspec for fast serialization.

.. grid:: 1 1 2 2
   :gutter: 2

   .. grid-item-card:: Getting Started
      :link: getting-started/index
      :link-type: doc

      Install civicrm-py and make your first API call in five minutes.

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

         from civicrm_py import CiviClient

         async with CiviClient(base_url="...", api_key="...") as client:
             response = await client.get("Contact", limit=10)
             for contact in response.values:
                 print(contact["display_name"])

   .. tab-item:: Sync

      .. code-block:: python

         from civicrm_py import SyncCiviClient

         with SyncCiviClient(base_url="...", api_key="...") as client:
             response = client.get("Contact", limit=10)
             for contact in response.values:
                 print(contact["display_name"])


Installation
------------

.. code-block:: bash

   pip install civicrm-py

   # With framework extras
   pip install civicrm-py[django]    # Django integration
   pip install civicrm-py[litestar]  # Litestar integration
   pip install civicrm-py[flask]     # Flask integration
   pip install civicrm-py[fastapi]   # FastAPI integration

   # With ecosystem extras
   pip install civicrm-py[sqlspec]   # Local database caching
   pip install civicrm-py[workflows] # Workflow automation

   # Combined extras
   pip install 'civicrm-py[litestar,sqlspec,workflows]'

See docs for :doc:`sqlspec </guides/sqlspec>`, :doc:`workflows </guides/workflows>`, and :doc:`pytest-databases </guides/pytest-databases>`.


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

   GitHub <https://github.com/JacobCoffee/civicrm-py>
   CiviCRM <https://civicrm.org/>


Alternatives
------------

- `civipy <https://github.com/indepndnt/civipy>`_ - Another Python client for CiviCRM. No built-in web framework integrations.


Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
