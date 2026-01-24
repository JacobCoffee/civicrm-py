Framework Guides
================

Integrate civicrm-py with your web framework.

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Framework
     - Tier
     - Features
   * - :doc:`django`
     - 1
     - Full plugin, admin, middleware, commands, template tags
   * - :doc:`litestar`
     - 1
     - Full plugin, DI, routes, health checks, DTOs
   * - :doc:`flask`
     - 2
     - Extension, CLI, context management
   * - :doc:`fastapi`
     - 2
     - Dependencies, lifespan, middleware
   * - :doc:`other`
     - 3
     - Base ASGI/WSGI middleware for other frameworks


Support Tiers
-------------

**Tier 1** frameworks get full integration with plugins, middleware, and admin UIs.

**Tier 2** frameworks have solid support with extensions and dependencies.

**Tier 3** covers everything else with base middleware you can build on.


Ecosystem Integrations
----------------------

Additional integrations for advanced features.

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Integration
     - Description
   * - :doc:`sqlspec`
     - Local database caching with PostgreSQL or SQLite repositories
   * - :doc:`workflows`
     - Multi-step automation with human approval workflows
   * - :doc:`pytest-databases`
     - Real database testing for contributors


.. toctree::
   :maxdepth: 2

   django
   litestar
   flask
   fastapi
   other
   webui

.. toctree::
   :maxdepth: 2
   :caption: Ecosystem

   sqlspec
   workflows
   pytest-databases
