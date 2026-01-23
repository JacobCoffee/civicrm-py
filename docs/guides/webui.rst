Web UI Explorer
===============

The civi-py Web UI provides an interactive browser for exploring CiviCRM data and
testing API queries. It integrates seamlessly with both Django and Litestar, offering
a clean, responsive interface with light and dark theme support.


Overview
--------

The Web UI includes three main features:

**Dashboard**
    A landing page with quick access to available entities and navigation links.

**Entity Browser**
    Browse, search, and paginate through CiviCRM entities. View individual records
    with all field values displayed in a readable format.

**API Playground**
    Execute live API queries with a form-based query builder. Select entities,
    choose actions, specify fields, and add where clauses. Results display as
    formatted JSON with query history tracking.

Both Django and Litestar integrations share the same Jinja2 templates, ensuring
a consistent experience across frameworks.


Features
--------

- **Theme Support**: Light, dark, and auto (system preference) themes
- **Entity Browser**: Grid view of entity types with pagination
- **Search**: Filter entities by display name
- **Record Details**: View all fields for individual records
- **API Playground**: Interactive query builder with JSON results
- **Query History**: Track recent queries in the playground
- **Authentication**: Staff/admin authentication with debug bypass option
- **Responsive Design**: Works on desktop and mobile devices


Django Integration
------------------

The Django Web UI uses class-based views with Jinja2 templating and integrates
with Django's authentication system.


Configuration
~~~~~~~~~~~~~

Create a ``WebUIConfig`` instance to customize the Web UI:

.. code-block:: python

    from civi_py.contrib.django.webui import WebUIConfig

    webui_config = WebUIConfig(
        title="CiviCRM Explorer",       # Header title
        theme="auto",                   # "light", "dark", or "auto"
        enable_playground=True,         # Show API playground
        enable_entity_browser=True,     # Show entity browser
        enable_request_history=True,    # Track query history
        default_entities=[              # Entities shown in browser
            "Contact",
            "Activity",
            "Contribution",
            "Event",
        ],
        items_per_page=25,              # Pagination size
        max_history_items=50,           # Max history entries
        require_staff=True,             # Require staff login
        login_url="/admin/login/",      # Login redirect URL
        debug=False,                    # Skip auth in debug mode
    )


Configuration Options
^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Option
     - Default
     - Description
   * - ``title``
     - "CiviCRM Explorer"
     - Title displayed in the header
   * - ``theme``
     - "auto"
     - Color theme: "light", "dark", or "auto" (follows system)
   * - ``enable_playground``
     - True
     - Show the API playground for testing queries
   * - ``enable_entity_browser``
     - True
     - Show the entity browser for exploring data
   * - ``enable_request_history``
     - True
     - Store and display query history in playground
   * - ``default_entities``
     - Contact, Activity, Contribution, Event
     - Entity types to show by default in the browser
   * - ``items_per_page``
     - 25
     - Number of records per page in entity lists
   * - ``max_history_items``
     - 50
     - Maximum query history entries to keep
   * - ``require_staff``
     - True
     - Require Django staff or superuser login
   * - ``login_url``
     - "/admin/login/"
     - URL to redirect unauthenticated users
   * - ``debug``
     - False
     - Skip authentication with warning (never use in production)


Template Setup
~~~~~~~~~~~~~~

Add the shared templates directory to your Django settings:

.. code-block:: python

    # settings.py
    from civi_py.contrib.django.webui import TEMPLATES_DIR

    TEMPLATES = [
        {
            "BACKEND": "django.template.backends.jinja2.Jinja2",
            "DIRS": [TEMPLATES_DIR],
            "APP_DIRS": True,
            "NAME": "webui_jinja2",
            "OPTIONS": {
                "environment": "your_app.jinja2.environment",
            },
        },
        # Keep your existing Django template backend
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [],
            "APP_DIRS": True,
            # ...
        },
    ]


URL Configuration
~~~~~~~~~~~~~~~~~

Include the Web UI URL patterns in your project:

.. code-block:: python

    # urls.py
    from django.urls import include, path
    from civi_py.contrib.django.webui import WebUIConfig, get_urlpatterns

    webui_config = WebUIConfig(
        title="My CiviCRM Explorer",
        theme="auto",
    )

    urlpatterns = [
        # ... your other URLs
        path("explorer/", include(get_urlpatterns(webui_config))),
    ]

This registers the following URL patterns:

.. list-table::
   :header-rows: 1
   :widths: 30 25 45

   * - URL Pattern
     - Name
     - Description
   * - ``/explorer/``
     - ``civi_webui_index``
     - Main dashboard
   * - ``/explorer/entities/``
     - ``civi_webui_entities``
     - Entity type selection
   * - ``/explorer/entities/<entity>/``
     - ``civi_webui_entity_list``
     - Entity list with pagination
   * - ``/explorer/entities/<entity>/<id>/``
     - ``civi_webui_entity_detail``
     - Single entity detail view
   * - ``/explorer/playground/``
     - ``civi_webui_playground``
     - API query playground
   * - ``/explorer/playground/execute/``
     - ``civi_webui_execute``
     - Query execution endpoint (JSON)


Views
~~~~~

The Django integration provides these class-based views:

``WebUIIndexView``
    Renders the main dashboard with links to the entity browser and playground.

``EntityBrowserView``
    Displays a grid of available entity types for browsing.

``EntityListView``
    Shows a paginated, searchable list of entities with ID, display name,
    and timestamps.

``EntityDetailView``
    Displays all fields for a single entity record in a key-value table format.

``PlaygroundView``
    Renders the interactive API query builder form.

``PlaygroundExecuteView``
    Handles query execution and returns JSON responses.

All views use the ``StaffRequiredMixin`` which checks ``WebUIConfig.require_staff``
and redirects unauthenticated users to the login page.


Authentication
~~~~~~~~~~~~~~

By default, the Web UI requires Django staff or superuser access. The authentication
flow works as follows:

1. User visits a Web UI page
2. If ``require_staff=True`` and not in debug mode:
   - Check if user is authenticated
   - Check if user has ``is_staff`` or ``is_superuser``
   - Redirect to ``login_url`` if either check fails
3. If ``debug=True`` or Django ``DEBUG=True``:
   - Skip authentication with a warning logged to console

.. warning::

   Never enable ``debug=True`` in production. The Web UI exposes CiviCRM data
   that should only be accessible to authorized staff.


Litestar Integration
--------------------

The Litestar Web UI uses async controllers with dependency injection for the
CiviClient instance.


Configuration
~~~~~~~~~~~~~

Configure the Web UI through ``WebUIConfig``:

.. code-block:: python

    from civi_py.contrib.litestar.webui import WebUIConfig

    webui_config = WebUIConfig(
        title="CiviCRM Explorer",       # Header title
        theme="auto",                   # "light", "dark", or "auto"
        enable_playground=True,         # Show API playground
        enable_entity_browser=True,     # Show entity browser
        enable_request_history=True,    # Track query history
        default_entities=[              # Entities shown in browser
            "Contact",
            "Activity",
            "Contribution",
            "Event",
        ],
        items_per_page=25,              # Pagination size
        max_history_items=50,           # Max history entries
        require_auth=True,              # Require authentication
        guards=None,                    # Custom Litestar guards
        auth_exclude_paths=["/static"], # Paths to skip auth
        debug=False,                    # Skip auth in debug mode
    )


Configuration Options
^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Option
     - Default
     - Description
   * - ``title``
     - "CiviCRM Explorer"
     - Title displayed in the header
   * - ``theme``
     - "auto"
     - Color theme: "light", "dark", or "auto"
   * - ``enable_playground``
     - True
     - Show the API playground
   * - ``enable_entity_browser``
     - True
     - Show the entity browser
   * - ``enable_request_history``
     - True
     - Track query history in playground
   * - ``default_entities``
     - Contact, Activity, Contribution, Event
     - Entity types to show by default
   * - ``items_per_page``
     - 25
     - Records per page in entity lists
   * - ``max_history_items``
     - 50
     - Maximum query history entries
   * - ``require_auth``
     - True
     - Require authentication for access
   * - ``guards``
     - None
     - Custom Litestar guard functions
   * - ``auth_exclude_paths``
     - ["/static"]
     - Paths to exclude from authentication
   * - ``debug``
     - False
     - Skip auth with warning (never use in production)


Plugin Integration
~~~~~~~~~~~~~~~~~~

Enable the Web UI through the CiviPlugin configuration:

.. code-block:: python

    from litestar import Litestar
    from civi_py.contrib.litestar import CiviPlugin, CiviPluginConfig
    from civi_py.contrib.litestar.webui import WebUIConfig

    civi_config = CiviPluginConfig(
        enable_webui=True,
        webui_path="/explorer",
        webui_config=WebUIConfig(
            title="CiviCRM Explorer",
            theme="auto",
        ),
    )

    app = Litestar(plugins=[CiviPlugin(civi_config)])


Manual Controller Setup
~~~~~~~~~~~~~~~~~~~~~~~

For more control, register the controllers directly:

.. code-block:: python

    from litestar import Litestar
    from civi_py.contrib.litestar.webui import WebUIConfig, get_webui_controllers
    from civi_py.contrib.litestar.webui.controllers import get_template_config

    webui_config = WebUIConfig(title="My Explorer")
    controllers = get_webui_controllers(webui_config, base_path="/explorer")

    app = Litestar(
        route_handlers=controllers,
        template_config=get_template_config(),
    )


Controllers
~~~~~~~~~~~

The Litestar integration provides these async controllers:

``WebUIController``
    Handles the main dashboard at the base path.

``EntityBrowserController``
    Manages entity browsing with routes for listing entity types, viewing
    entity lists with pagination, and displaying entity details.

``PlaygroundController``
    Provides the interactive API playground with query execution.

All controllers receive the ``CiviClient`` through Litestar's dependency injection
system, enabling async operations.


Custom Authentication
~~~~~~~~~~~~~~~~~~~~~

Provide custom guards for authentication:

.. code-block:: python

    from litestar.connection import ASGIConnection
    from litestar.handlers import BaseRouteHandler
    from litestar.exceptions import NotAuthorizedException

    async def require_admin(
        connection: ASGIConnection,
        _: BaseRouteHandler,
    ) -> None:
        """Guard that requires admin access."""
        user = connection.user
        if not user or not getattr(user, "is_admin", False):
            raise NotAuthorizedException("Admin access required")

    webui_config = WebUIConfig(
        require_auth=True,
        guards=[require_admin],
    )


Customization
-------------

Theme Customization
~~~~~~~~~~~~~~~~~~~

The Web UI supports three themes through the ``theme`` configuration option:

- ``"light"``: Light background with dark text
- ``"dark"``: Dark background with light text
- ``"auto"``: Follows the user's system preference using ``prefers-color-scheme``

The CSS uses CSS custom properties for theming:

.. code-block:: css

    :root {
        --bg-primary: #f8fafc;
        --bg-secondary: #ffffff;
        --text-primary: #1e293b;
        --text-secondary: #64748b;
        --accent-color: #0ea5e9;
        /* ... more variables */
    }

    [data-theme="dark"] {
        --bg-primary: #0f172a;
        --bg-secondary: #1e293b;
        --text-primary: #f1f5f9;
        --text-secondary: #94a3b8;
        /* ... */
    }


Entity Selection
~~~~~~~~~~~~~~~~

Control which entities appear in the browser:

.. code-block:: python

    config = WebUIConfig(
        default_entities=[
            "Contact",
            "Activity",
            "Contribution",
            "Event",
            "Membership",
            "Participant",
            "Campaign",
        ],
    )


Pagination
~~~~~~~~~~

Adjust the number of items per page:

.. code-block:: python

    config = WebUIConfig(
        items_per_page=50,  # Show 50 records per page
    )


UI Description
--------------

Dashboard
~~~~~~~~~

The dashboard displays:

- A header with the configured title and navigation links
- Cards for "Entity Browser" and "API Playground" with descriptions
- A grid of quick-access buttons for default entity types
- A quick reference section listing common API operations

Navigation includes links to Dashboard, Entities, and Playground, with the current
page highlighted.


Entity Browser
~~~~~~~~~~~~~~

The entity browser shows:

- A grid of cards, one for each configured entity type
- Each card links to the entity list view
- Cards display the entity name with a "Browse records" subtitle


Entity List
~~~~~~~~~~~

The entity list provides:

- A search input for filtering by display name
- Record count showing "X of Y records"
- A table with columns: ID, Display Name, Created, Modified, Actions
- Pagination controls for navigating through results
- A "View" button for each record linking to the detail view


Entity Detail
~~~~~~~~~~~~~

The entity detail view shows:

- The entity type and ID in the header
- A "Back to List" navigation button
- A two-column table with field names and values
- Special formatting for null, boolean, and nested object values


API Playground
~~~~~~~~~~~~~~

The playground offers:

- A two-column layout with Query Builder and Results
- Entity dropdown populated with configured entity types
- Action selector for "get" and "getFields" operations
- Text input for comma-separated field selection
- Textarea for JSON where clauses
- Limit input with validation
- Execute button to run queries
- Results panel showing count and formatted JSON
- Query history section tracking recent queries with timestamps


Security Considerations
-----------------------

The Web UI exposes CiviCRM data through a browser interface. Follow these
security practices:

1. **Always require authentication in production**. Set ``require_staff=True``
   (Django) or ``require_auth=True`` (Litestar).

2. **Never enable debug mode in production**. The ``debug=True`` option bypasses
   authentication entirely.

3. **Use HTTPS** to protect data in transit.

4. **Limit default entities** to only those users should access.

5. **Review Litestar guards** to ensure they properly verify user permissions.

When debug mode is enabled with authentication required, the Web UI logs a
prominent warning to the console:

.. code-block:: text

    WARNING: CiviCRM Web UI is running WITHOUT AUTHENTICATION

    The Web UI is accessible without login because debug mode is enabled.
    This exposes CiviCRM data to anyone with network access.

    DO NOT USE IN PRODUCTION!


Comparison: Django vs Litestar
------------------------------

.. tab-set::

   .. tab-item:: Django

      **Authentication**: Uses ``StaffRequiredMixin`` with ``is_staff``/``is_superuser`` checks

      **Client Access**: Gets client from request via middleware or creates new ``SyncCiviClient``

      **URL Generation**: Uses Django's ``reverse()`` function

      **Templates**: Jinja2 backend with ``using="webui_jinja2"``

      .. code-block:: python

          from civi_py.contrib.django.webui import WebUIConfig, get_urlpatterns

          urlpatterns = [
              path("explorer/", include(get_urlpatterns(WebUIConfig()))),
          ]

   .. tab-item:: Litestar

      **Authentication**: Uses Litestar guards (custom or built-in)

      **Client Access**: Dependency injection provides async ``CiviClient``

      **URL Generation**: Path-based helper function with base_path

      **Templates**: Standard Litestar ``TemplateConfig`` with Jinja2

      .. code-block:: python

          from civi_py.contrib.litestar.webui import WebUIConfig, get_webui_controllers

          controllers = get_webui_controllers(WebUIConfig(), base_path="/explorer")
