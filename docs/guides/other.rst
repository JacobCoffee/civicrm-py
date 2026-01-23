Custom Framework Integration
============================

This guide shows you how to build civi-py integrations for frameworks that do not have dedicated support. You will learn the integration architecture, implement a complete custom integration, test it properly, and optionally publish it as a community package.


When to Build a Custom Integration
----------------------------------

Before building a custom integration, consider whether the built-in ASGI or WSGI middleware meets your needs.

Use Built-in Middleware When
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The generic middleware works well for simple use cases:

- You need basic client injection into requests
- Your framework supports standard ASGI or WSGI interfaces
- You do not need framework specific features like dependency injection or CLI commands
- You want minimal configuration and quick setup

.. code-block:: python

   # ASGI middleware works with Starlette, Quart, Blacksheep, etc.
   from civi_py.contrib.asgi import CiviASGIMiddleware

   app = CiviASGIMiddleware(your_asgi_app)

   # WSGI middleware works with Bottle, Falcon, Werkzeug, etc.
   from civi_py.contrib.wsgi import CiviWSGIMiddleware

   app = CiviWSGIMiddleware(your_wsgi_app)

Build a Custom Integration When
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A custom integration provides significant benefits:

- **Idiomatic API**: Use patterns native to your framework (e.g., Flask's ``init_app()``, Litestar's plugins)
- **Dependency Injection**: Integrate with the framework's DI system for clean handler signatures
- **Configuration**: Load settings from framework specific config systems
- **CLI Commands**: Add framework CLI commands for connectivity checks and interactive shells
- **Lifecycle Management**: Hook into framework startup and shutdown events properly
- **Testing Support**: Provide test utilities that work with framework testing patterns

The effort pays off when you use civi-py extensively within a specific framework.


Integration Architecture
------------------------

The civi-py integration system consists of three layers: protocols that define the interface, a base class that provides common functionality, and a registry for discovery.

Protocols
^^^^^^^^^

The ``civi_py.contrib.base`` module defines three protocols that integrations can implement.

**IntegrationProtocol** defines core client access:

.. code-block:: python

   from typing import Protocol, runtime_checkable

   @runtime_checkable
   class IntegrationProtocol(Protocol):
       """Core interface for framework integrations."""

       def get_client(self) -> CiviClient | SyncCiviClient:
           """Return the configured CiviCRM client."""
           ...

       def get_settings(self) -> CiviSettings:
           """Return the CiviCRM configuration."""
           ...

       def is_async(self) -> bool:
           """Return True if using async client."""
           ...

**LifecycleHooks** defines application lifecycle events:

.. code-block:: python

   @runtime_checkable
   class LifecycleHooks(Protocol):
       """Hooks for application startup and shutdown."""

       async def on_startup(self) -> None:
           """Initialize client on application start (async)."""
           ...

       async def on_shutdown(self) -> None:
           """Close client on application shutdown (async)."""
           ...

       def on_startup_sync(self) -> None:
           """Initialize client on application start (sync)."""
           ...

       def on_shutdown_sync(self) -> None:
           """Close client on application shutdown (sync)."""
           ...

**RequestContext** defines request scoped access:

.. code-block:: python

   @runtime_checkable
   class RequestContext(Protocol):
       """Request-scoped dependency injection."""

       def get_client(self) -> CiviClient | SyncCiviClient:
           """Get client for current request."""
           ...

       def set_client(self, client: CiviClient | SyncCiviClient) -> None:
           """Set client for current request (useful for testing)."""
           ...

BaseIntegration Class
^^^^^^^^^^^^^^^^^^^^^

The ``BaseIntegration`` class in ``civi_py.contrib.integration`` provides a complete implementation you can extend:

.. code-block:: python

   from civi_py.contrib.integration import BaseIntegration

   class MyFrameworkIntegration(BaseIntegration):
       """Integration for MyFramework."""

       def setup(self, app):
           """Configure the integration with your framework."""
           # Hook into framework lifecycle
           app.on_startup.append(self.on_startup)
           app.on_shutdown.append(self.on_shutdown)

           # Register with framework DI
           app.dependency_overrides[CiviClient] = self.get_client

The base class handles:

- Settings loading from environment or explicit configuration
- Async and sync client lifecycle management
- Context manager support for testing
- Proper resource cleanup

Key methods from BaseIntegration:

.. list-table:: BaseIntegration Methods
   :header-rows: 1
   :widths: 30 70

   * - Method
     - Description
   * - ``from_env()``
     - Class method to create from environment variables
   * - ``from_settings(settings)``
     - Class method to create from explicit CiviSettings
   * - ``startup()`` / ``shutdown()``
     - Async client lifecycle management
   * - ``startup_sync()`` / ``shutdown_sync()``
     - Sync client lifecycle management
   * - ``get_client()``
     - Get initialized async CiviClient
   * - ``get_sync_client()``
     - Get initialized sync SyncCiviClient
   * - ``settings``
     - Property to access CiviSettings

Integration Registry
^^^^^^^^^^^^^^^^^^^^

The registry in ``civi_py.contrib.registry`` enables automatic discovery of integrations.

Register your integration:

.. code-block:: python

   from civi_py.contrib.registry import register_integration
   from civi_py.contrib.integration import BaseIntegration

   @register_integration("myframework")
   class MyFrameworkIntegration(BaseIntegration):
       """Integration for MyFramework."""
       pass

Discover and use integrations:

.. code-block:: python

   from civi_py.contrib.registry import (
       discover_integrations,
       get_integration,
       list_integrations,
   )

   # Auto-discover from entry points
   discover_integrations()

   # List available integrations
   print(list_integrations())  # ['django', 'litestar', 'flask', 'myframework']

   # Get and use an integration
   IntegrationClass = get_integration("myframework")
   integration = IntegrationClass.from_env()


Step by Step: Building a Custom Integration
-------------------------------------------

This section walks through building an integration for a hypothetical async framework called ``Rocket``. The same patterns apply to any framework.

Step 1: Define the Integration Class
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Start by extending BaseIntegration and adding framework specific configuration:

.. code-block:: python

   # civi_rocket/__init__.py
   """CiviCRM integration for Rocket framework."""

   from __future__ import annotations

   import logging
   from dataclasses import dataclass, field
   from typing import TYPE_CHECKING

   from civi_py.contrib.integration import BaseIntegration
   from civi_py.contrib.registry import register_integration

   if TYPE_CHECKING:
       from civi_py.core.client import CiviClient
       from civi_py.core.config import CiviSettings

   logger = logging.getLogger(__name__)


   @dataclass
   class CiviRocketConfig:
       """Configuration for the Rocket CiviCRM plugin.

       Attributes:
           settings: Pre-configured CiviSettings. If None, loads from environment.
           register_routes: Whether to register CRUD routes for entities.
           api_prefix: URL prefix for auto-generated routes.
           enable_health_check: Add a health check endpoint.
           health_check_path: Path for health check endpoint.
           debug: Enable debug logging.
       """

       settings: CiviSettings | None = None
       register_routes: bool = False
       api_prefix: str = "/api/civi"
       enable_health_check: bool = True
       health_check_path: str = "/health/civi"
       debug: bool = False


   @register_integration("rocket")
   class CiviRocket(BaseIntegration):
       """Rocket framework plugin for CiviCRM API integration.

       Provides automatic client lifecycle management, dependency injection,
       and optional route generation for CiviCRM API access.

       Example:
           Basic usage:

           >>> from rocket import Rocket
           >>> from civi_rocket import CiviRocket, CiviRocketConfig
           >>>
           >>> app = Rocket()
           >>> config = CiviRocketConfig(enable_health_check=True)
           >>> civi = CiviRocket(config)
           >>> civi.init_app(app)

           Using the client in handlers:

           >>> @app.route("/contacts")
           ... async def list_contacts(civi_client: CiviClient):
           ...     response = await civi_client.get("Contact", limit=10)
           ...     return {"contacts": response.values}
       """

       __slots__ = ("_config", "_app")

       def __init__(self, config: CiviRocketConfig | None = None) -> None:
           """Initialize the Rocket plugin.

           Args:
               config: Plugin configuration. Uses defaults if None.
           """
           self._config = config or CiviRocketConfig()

           # Initialize base class with settings
           super().__init__(
               settings=self._config.settings,
               is_async=True,  # Rocket is async
           )

           self._app = None

           if self._config.debug:
               logging.getLogger("civi_py").setLevel(logging.DEBUG)

       @property
       def config(self) -> CiviRocketConfig:
           """Get the plugin configuration."""
           return self._config

Step 2: Implement Framework Hooks
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Connect your integration to the framework's lifecycle:

.. code-block:: python

   # Continuing civi_rocket/__init__.py

       def init_app(self, app) -> None:
           """Initialize the plugin with a Rocket application.

           Args:
               app: Rocket application instance.
           """
           self._app = app

           # Register lifecycle hooks
           app.on_startup(self._startup_handler)
           app.on_shutdown(self._shutdown_handler)

           # Register dependency provider
           app.dependency(CiviClient, self._provide_client)

           # Register health check if enabled
           if self._config.enable_health_check:
               self._register_health_check(app)

           # Register CRUD routes if enabled
           if self._config.register_routes:
               self._register_routes(app)

           # Store reference on app for access elsewhere
           app.extensions["civi"] = self

           logger.info(
               "CiviRocket initialized for %s",
               self._settings.base_url,
           )

       async def _startup_handler(self) -> None:
           """Handle application startup."""
           await self.startup()
           logger.debug("CiviClient ready")

       async def _shutdown_handler(self) -> None:
           """Handle application shutdown."""
           await self.shutdown()
           logger.debug("CiviClient closed")

       async def _provide_client(self) -> CiviClient:
           """Dependency provider for CiviClient.

           Returns:
               The initialized CiviClient instance.
           """
           return self.get_client()

Step 3: Add Health Check and Routes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Provide optional features that enhance the integration:

.. code-block:: python

   # Continuing civi_rocket/__init__.py

       def _register_health_check(self, app) -> None:
           """Register the health check endpoint.

           Args:
               app: Rocket application instance.
           """
           @app.route(self._config.health_check_path, methods=["GET"])
           async def civi_health_check():
               """Check CiviCRM API connectivity."""
               try:
                   client = self.get_client()
                   # Perform a lightweight API call
                   response = await client.get("Contact", select=["id"], limit=1)
                   return {
                       "status": "healthy",
                       "service": "civicrm",
                       "base_url": self._settings.base_url,
                   }
               except Exception as e:
                   logger.exception("Health check failed")
                   return {
                       "status": "unhealthy",
                       "service": "civicrm",
                       "error": str(e),
                   }, 503

           logger.debug("Registered health check at %s", self._config.health_check_path)

       def _register_routes(self, app) -> None:
           """Register CRUD routes for CiviCRM entities.

           Args:
               app: Rocket application instance.
           """
           prefix = self._config.api_prefix

           @app.route(f"{prefix}/contacts", methods=["GET"])
           async def list_contacts(civi_client: CiviClient):
               """List contacts."""
               response = await civi_client.get("Contact", limit=25)
               return {"values": response.values, "count": response.count}

           @app.route(f"{prefix}/contacts/<int:contact_id>", methods=["GET"])
           async def get_contact(contact_id: int, civi_client: CiviClient):
               """Get a single contact."""
               response = await civi_client.get(
                   "Contact",
                   where=[["id", "=", contact_id]],
                   limit=1,
               )
               if not response.values:
                   return {"error": "Contact not found"}, 404
               return response.values[0]

           logger.debug("Registered CRUD routes at %s", prefix)

Step 4: Add Configuration Loading
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Support loading settings from framework configuration:

.. code-block:: python

   # Continuing civi_rocket/__init__.py

       @classmethod
       def from_rocket_config(cls, app) -> "CiviRocket":
           """Create integration from Rocket app configuration.

           Loads settings from app.config with CIVI_ prefix.

           Args:
               app: Rocket application instance.

           Returns:
               Configured CiviRocket instance.

           Example:
               >>> app = Rocket()
               >>> app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
               >>> app.config["CIVI_API_KEY"] = "your-api-key"
               >>> civi = CiviRocket.from_rocket_config(app)
               >>> civi.init_app(app)
           """
           from civi_py.core.config import CiviSettings

           settings = CiviSettings(
               base_url=app.config["CIVI_BASE_URL"],
               api_key=app.config.get("CIVI_API_KEY"),
               site_key=app.config.get("CIVI_SITE_KEY"),
               timeout=app.config.get("CIVI_TIMEOUT", 30),
               verify_ssl=app.config.get("CIVI_VERIFY_SSL", True),
               debug=app.config.get("CIVI_DEBUG", False),
               max_retries=app.config.get("CIVI_MAX_RETRIES", 3),
           )

           config = CiviRocketConfig(
               settings=settings,
               debug=settings.debug,
           )

           return cls(config)

Step 5: Add Convenience Functions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Provide helper functions for common access patterns:

.. code-block:: python

   # Continuing civi_rocket/__init__.py

   def get_civi_client(app) -> CiviClient:
       """Get the CiviClient from a Rocket application.

       Args:
           app: Rocket application instance.

       Returns:
           The CiviClient instance.

       Raises:
           RuntimeError: If CiviRocket is not initialized.

       Example:
           >>> from civi_rocket import get_civi_client
           >>> client = get_civi_client(app)
           >>> response = await client.get("Contact", limit=10)
       """
       civi = app.extensions.get("civi")
       if civi is None:
           msg = "CiviRocket not initialized. Call CiviRocket().init_app(app) first."
           raise RuntimeError(msg)
       return civi.get_client()


   __all__ = [
       "CiviRocket",
       "CiviRocketConfig",
       "get_civi_client",
   ]

Step 6: Add CLI Commands (Litestar)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Litestar supports CLI plugins through the ``CLIPluginProtocol``. This allows your integration to add commands to the ``litestar`` CLI tool. Implement this protocol alongside ``InitPluginProtocol`` to provide commands like connectivity checks and interactive shells.

**Implementing CLIPluginProtocol**

Modify your plugin class to implement both protocols:

.. code-block:: python

   # civi_rocket/__init__.py (Litestar-style integration)
   """CiviCRM integration for Litestar framework with CLI support."""

   from __future__ import annotations

   from typing import TYPE_CHECKING

   from litestar.plugins import CLIPluginProtocol, InitPluginProtocol

   if TYPE_CHECKING:
       from click import Group
       from litestar import Litestar
       from litestar.config.app import AppConfig

   from civi_py.contrib.integration import BaseIntegration


   class CiviLitestarPlugin(BaseIntegration, InitPluginProtocol, CLIPluginProtocol):
       """Litestar plugin for CiviCRM API integration with CLI commands."""

       def on_app_init(self, app_config: AppConfig) -> AppConfig:
           """Configure the application on initialization."""
           app_config.on_startup.append(self.startup)
           app_config.on_shutdown.append(self.shutdown)
           return app_config

       def on_cli_init(self, cli: Group) -> None:
           """Register CLI commands with the Litestar CLI."""
           from civi_rocket.cli import civi_group

           cli.add_command(civi_group)

**Creating the Command Group**

Define CLI commands in a separate module using Click decorators. Litestar provides ``LitestarGroup`` for commands that need access to the application instance:

.. code-block:: python

   # civi_rocket/cli.py
   """CLI commands for CiviCRM operations."""

   from __future__ import annotations

   from typing import TYPE_CHECKING

   from click import group, option
   from litestar.cli._utils import LitestarGroup, console

   if TYPE_CHECKING:
       from litestar import Litestar

   from civi_rocket import CiviLitestarPlugin


   @group(cls=LitestarGroup, name="civi")
   def civi_group() -> None:
       """Manage CiviCRM operations."""


   @civi_group.command(name="check", help="Check CiviCRM API connectivity.")
   @option(
       "--verbose",
       type=bool,
       help="Enable verbose output.",
       default=False,
       is_flag=True,
   )
   def civi_check(app: "Litestar", verbose: bool) -> None:
       """Verify the CiviCRM API connection is working."""
       import asyncio

       plugin = app.plugins.get(CiviLitestarPlugin)
       if plugin is None:
           console.print("[red]CiviLitestarPlugin not registered with this app.[/]")
           raise SystemExit(1)

       async def _check() -> None:
           await plugin.startup()
           try:
               client = plugin.get_client()
               # Perform a lightweight API call to verify connectivity
               response = await client.get("Contact", select=["id"], limit=1)

               if verbose:
                   console.print(f"[dim]Base URL: {plugin.settings.base_url}[/]")
                   console.print(f"[dim]Response count: {response.count}[/]")

               console.print("[green]Connected to CiviCRM[/]")
           except Exception as e:
               console.print(f"[red]Connection failed: {e}[/]")
               raise SystemExit(1)
           finally:
               await plugin.shutdown()

       asyncio.run(_check())


   @civi_group.command(name="shell", help="Start an interactive CiviCRM shell.")
   def civi_shell(app: "Litestar") -> None:
       """Launch an interactive Python shell with CiviCRM client configured."""
       import asyncio
       import code

       plugin = app.plugins.get(CiviLitestarPlugin)
       if plugin is None:
           console.print("[red]CiviLitestarPlugin not registered with this app.[/]")
           raise SystemExit(1)

       async def _setup_shell() -> None:
           await plugin.startup()
           client = plugin.get_client()

           banner = """
   CiviCRM Interactive Shell
   -------------------------
   Available objects:
     client  - Async CiviClient instance
     plugin  - CiviLitestarPlugin instance

   Example:
     >>> import asyncio
     >>> response = asyncio.run(client.get("Contact", limit=5))
     >>> print(response.values)
   """
           local_vars = {
               "client": client,
               "plugin": plugin,
               "asyncio": asyncio,
           }

           console.print("[green]Starting CiviCRM shell...[/]")
           code.interact(banner=banner, local=local_vars)
           await plugin.shutdown()

       asyncio.run(_setup_shell())

**Accessing the Plugin from Commands**

The ``LitestarGroup`` class automatically injects the ``Litestar`` application instance as the first argument to command handlers. Use ``app.plugins.get()`` to retrieve your plugin:

.. code-block:: python

   @civi_group.command(name="sync-contacts")
   @option("--limit", type=int, default=100, help="Maximum contacts to sync.")
   def sync_contacts(app: "Litestar", limit: int) -> None:
       """Sync contacts from CiviCRM to local database."""
       plugin = app.plugins.get(CiviLitestarPlugin)
       if plugin is None:
           console.print("[red]Plugin not found.[/]")
           raise SystemExit(1)

       # Access plugin configuration
       console.print(f"[dim]Syncing from: {plugin.settings.base_url}[/]")

       # Perform sync operation...
       console.print(f"[green]Synced {limit} contacts.[/]")

**Using Rich Console for Output**

Litestar provides a Rich console instance for formatted output. Use markup syntax for colors and styling:

.. code-block:: python

   from litestar.cli._utils import console

   # Success messages
   console.print("[green]Operation completed successfully.[/]")

   # Warnings
   console.print("[yellow]Warning: Rate limit approaching.[/]")

   # Errors
   console.print("[red]Error: Connection refused.[/]")

   # Informational with dim styling
   console.print(f"[dim]Processing {count} records...[/]")

   # Tables for structured data
   from rich.table import Table

   table = Table(title="CiviCRM Entities")
   table.add_column("Entity", style="cyan")
   table.add_column("Count", justify="right")
   table.add_row("Contact", "1,234")
   table.add_row("Activity", "5,678")
   console.print(table)

**Running CLI Commands**

Once your plugin is registered, commands are available through the Litestar CLI:

.. code-block:: bash

   # Check API connectivity
   litestar civi check --verbose

   # Start interactive shell
   litestar civi shell

   # Custom commands you define
   litestar civi sync-contacts --limit 500

Complete Example
^^^^^^^^^^^^^^^^

Here is the complete integration in context:

.. code-block:: python

   # example_app.py
   """Example Rocket application with CiviCRM integration."""

   from rocket import Rocket
   from civi_rocket import CiviRocket, CiviRocketConfig

   # Create application
   app = Rocket()

   # Configure CiviCRM integration
   config = CiviRocketConfig(
       enable_health_check=True,
       register_routes=True,
       api_prefix="/api/v1/crm",
       debug=True,
   )

   civi = CiviRocket(config)
   civi.init_app(app)


   # Custom route using dependency injection
   @app.route("/my-contacts")
   async def my_contacts(civi_client):
       """Custom endpoint using injected client."""
       response = await civi_client.get(
           "Contact",
           select=["id", "display_name", "email_primary.email"],
           where=[["is_deleted", "=", False]],
           limit=50,
       )
       return {
           "contacts": response.values,
           "total": response.count,
       }


   if __name__ == "__main__":
       app.run(debug=True)


Testing Your Integration
------------------------

Thorough testing ensures your integration works correctly. Test at three levels: unit tests for the integration class, integration tests with a mock framework, and end to end tests with a real framework instance.

Unit Tests
^^^^^^^^^^

Test the integration class in isolation:

.. code-block:: python

   # tests/test_civi_rocket.py
   """Unit tests for CiviRocket integration."""

   import pytest
   from unittest.mock import AsyncMock, MagicMock, patch

   from civi_py.core.config import CiviSettings
   from civi_rocket import CiviRocket, CiviRocketConfig


   @pytest.fixture
   def settings():
       """Create test settings."""
       return CiviSettings(
           base_url="https://test.example.org/civicrm/ajax/api4",
           api_key="test-api-key",
       )


   @pytest.fixture
   def config(settings):
       """Create test config."""
       return CiviRocketConfig(settings=settings)


   class TestCiviRocketInit:
       """Tests for CiviRocket initialization."""

       def test_init_with_config(self, config):
           """Integration initializes with provided config."""
           integration = CiviRocket(config)

           assert integration.config is config
           assert integration._settings == config.settings

       def test_init_default_config(self):
           """Integration creates default config when none provided."""
           with patch.dict("os.environ", {
               "CIVI_BASE_URL": "https://example.org/civicrm/ajax/api4",
               "CIVI_API_KEY": "env-key",
           }):
               integration = CiviRocket()

               assert integration.config is not None
               assert integration.config.register_routes is False


   class TestLifecycle:
       """Tests for client lifecycle management."""

       @pytest.mark.asyncio
       async def test_startup_creates_client(self, config):
           """Startup initializes the async client."""
           integration = CiviRocket(config)

           await integration.startup()

           assert integration._client is not None

       @pytest.mark.asyncio
       async def test_shutdown_closes_client(self, config):
           """Shutdown closes and clears the client."""
           integration = CiviRocket(config)
           await integration.startup()

           await integration.shutdown()

           assert integration._client is None

       @pytest.mark.asyncio
       async def test_context_manager(self, config):
           """Integration works as async context manager."""
           async with CiviRocket(config) as integration:
               client = integration.get_client()
               assert client is not None

           # Client should be closed after exiting context
           assert integration._client is None


   class TestClientAccess:
       """Tests for client access methods."""

       @pytest.mark.asyncio
       async def test_get_client_after_startup(self, config):
           """get_client returns client after startup."""
           integration = CiviRocket(config)
           await integration.startup()

           client = integration.get_client()

           assert client is not None

       def test_get_client_before_startup_raises(self, config):
           """get_client raises before startup is called."""
           integration = CiviRocket(config)

           with pytest.raises(Exception) as exc_info:
               integration.get_client()

           assert "not initialized" in str(exc_info.value).lower()

Integration Tests
^^^^^^^^^^^^^^^^^

Test the integration with a mock framework:

.. code-block:: python

   # tests/test_civi_rocket_integration.py
   """Integration tests for CiviRocket with mock Rocket framework."""

   import pytest
   from unittest.mock import AsyncMock, MagicMock

   from civi_py.core.config import CiviSettings
   from civi_rocket import CiviRocket, CiviRocketConfig, get_civi_client


   @pytest.fixture
   def mock_app():
       """Create a mock Rocket application."""
       app = MagicMock()
       app.extensions = {}
       app.config = {}

       # Track registered handlers
       app._startup_handlers = []
       app._shutdown_handlers = []
       app._routes = {}
       app._dependencies = {}

       def on_startup(handler):
           app._startup_handlers.append(handler)

       def on_shutdown(handler):
           app._shutdown_handlers.append(handler)

       def route(path, methods=None):
           def decorator(func):
               app._routes[path] = {"handler": func, "methods": methods}
               return func
           return decorator

       def dependency(type_hint, provider):
           app._dependencies[type_hint] = provider

       app.on_startup = on_startup
       app.on_shutdown = on_shutdown
       app.route = route
       app.dependency = dependency

       return app


   @pytest.fixture
   def settings():
       """Create test settings."""
       return CiviSettings(
           base_url="https://test.example.org/civicrm/ajax/api4",
           api_key="test-api-key",
       )


   class TestInitApp:
       """Tests for init_app method."""

       def test_registers_lifecycle_hooks(self, mock_app, settings):
           """init_app registers startup and shutdown hooks."""
           config = CiviRocketConfig(settings=settings)
           integration = CiviRocket(config)

           integration.init_app(mock_app)

           assert len(mock_app._startup_handlers) == 1
           assert len(mock_app._shutdown_handlers) == 1

       def test_registers_health_check_when_enabled(self, mock_app, settings):
           """Health check route is registered when enabled."""
           config = CiviRocketConfig(
               settings=settings,
               enable_health_check=True,
               health_check_path="/health/civi",
           )
           integration = CiviRocket(config)

           integration.init_app(mock_app)

           assert "/health/civi" in mock_app._routes

       def test_no_health_check_when_disabled(self, mock_app, settings):
           """Health check route not registered when disabled."""
           config = CiviRocketConfig(
               settings=settings,
               enable_health_check=False,
           )
           integration = CiviRocket(config)

           integration.init_app(mock_app)

           assert "/health/civi" not in mock_app._routes

       def test_stores_extension_reference(self, mock_app, settings):
           """Integration stored in app.extensions."""
           config = CiviRocketConfig(settings=settings)
           integration = CiviRocket(config)

           integration.init_app(mock_app)

           assert mock_app.extensions["civi"] is integration


   class TestGetCiviClient:
       """Tests for get_civi_client helper function."""

       def test_returns_client_when_initialized(self, mock_app, settings):
           """Returns client from initialized integration."""
           config = CiviRocketConfig(settings=settings)
           integration = CiviRocket(config)
           integration.init_app(mock_app)

           # Simulate startup
           integration._client = MagicMock()

           client = get_civi_client(mock_app)

           assert client is integration._client

       def test_raises_when_not_initialized(self, mock_app):
           """Raises RuntimeError when integration not initialized."""
           with pytest.raises(RuntimeError) as exc_info:
               get_civi_client(mock_app)

           assert "not initialized" in str(exc_info.value).lower()

End to End Tests
^^^^^^^^^^^^^^^^

If your framework supports test clients, write end to end tests:

.. code-block:: python

   # tests/test_civi_rocket_e2e.py
   """End to end tests with real Rocket test client."""

   import pytest
   from unittest.mock import AsyncMock, patch

   # Assuming Rocket provides a test client
   # from rocket.testing import TestClient

   from civi_py.core.config import CiviSettings
   from civi_rocket import CiviRocket, CiviRocketConfig


   @pytest.fixture
   def settings():
       """Create test settings."""
       return CiviSettings(
           base_url="https://test.example.org/civicrm/ajax/api4",
           api_key="test-api-key",
       )


   @pytest.fixture
   def app(settings):
       """Create a configured Rocket application."""
       from rocket import Rocket

       app = Rocket()
       config = CiviRocketConfig(
           settings=settings,
           enable_health_check=True,
       )
       civi = CiviRocket(config)
       civi.init_app(app)
       return app


   class TestHealthCheck:
       """Tests for health check endpoint."""

       @pytest.mark.asyncio
       async def test_health_check_success(self, app):
           """Health check returns healthy status."""
           # Mock the CiviClient.get method
           mock_response = MagicMock()
           mock_response.values = [{"id": 1}]

           with patch.object(
               app.extensions["civi"],
               "get_client",
           ) as mock_get_client:
               mock_client = AsyncMock()
               mock_client.get.return_value = mock_response
               mock_get_client.return_value = mock_client

               # Use framework test client
               # async with TestClient(app) as client:
               #     response = await client.get("/health/civi")
               #     assert response.status_code == 200
               #     data = response.json()
               #     assert data["status"] == "healthy"
               pass  # Replace with actual test client usage


Publishing Your Integration
---------------------------

Once your integration is tested and working, you can publish it as a community package for others to use.

Package Structure
^^^^^^^^^^^^^^^^^

Organize your package following Python packaging best practices:

.. code-block:: text

   civi-rocket/
   +-- src/
   |   +-- civi_rocket/
   |       +-- __init__.py      # Main integration code
   |       +-- py.typed         # PEP 561 marker for type hints
   +-- tests/
   |   +-- __init__.py
   |   +-- test_integration.py
   |   +-- conftest.py
   +-- pyproject.toml
   +-- README.md
   +-- LICENSE

pyproject.toml Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Configure your package with proper entry points for auto discovery:

.. code-block:: toml

   [project]
   name = "civi-rocket"
   version = "1.0.0"
   description = "CiviCRM integration for Rocket framework"
   readme = "README.md"
   requires-python = ">=3.10"
   license = "MIT"
   authors = [
       { name = "Your Name", email = "you@example.com" },
   ]
   classifiers = [
       "Development Status :: 4 - Beta",
       "Framework :: Rocket",
       "Intended Audience :: Developers",
       "License :: OSI Approved :: MIT License",
       "Programming Language :: Python :: 3",
       "Programming Language :: Python :: 3.10",
       "Programming Language :: Python :: 3.11",
       "Programming Language :: Python :: 3.12",
       "Topic :: Software Development :: Libraries :: Python Modules",
   ]
   dependencies = [
       "civi-py>=1.0.0",
       "rocket>=2.0.0",
   ]

   [project.optional-dependencies]
   dev = [
       "pytest>=7.0",
       "pytest-asyncio>=0.21",
       "pytest-cov>=4.0",
   ]

   [project.entry-points."civi_py.integrations"]
   rocket = "civi_rocket:CiviRocket"

   [build-system]
   requires = ["hatchling"]
   build-backend = "hatchling.build"

   [tool.hatch.build.targets.wheel]
   packages = ["src/civi_rocket"]

The ``[project.entry-points."civi_py.integrations"]`` section enables automatic discovery. When users install your package, they can discover it with:

.. code-block:: python

   from civi_py.contrib.registry import discover_integrations, get_integration

   discover_integrations()
   RocketIntegration = get_integration("rocket")

README Template
^^^^^^^^^^^^^^^

Include a clear README with installation and usage instructions:

.. code-block:: markdown

   # civi-rocket

   CiviCRM integration for the Rocket framework.

   ## Installation

   ```bash
   pip install civi-rocket
   ```

   ## Quick Start

   ```python
   from rocket import Rocket
   from civi_rocket import CiviRocket

   app = Rocket()
   civi = CiviRocket()
   civi.init_app(app)

   @app.route("/contacts")
   async def list_contacts(civi_client):
       response = await civi_client.get("Contact", limit=10)
       return {"contacts": response.values}
   ```

   ## Configuration

   Set environment variables:

   ```bash
   export CIVI_BASE_URL=https://your-site.org/civicrm/ajax/api4
   export CIVI_API_KEY=your-api-key
   ```

   Or configure in code:

   ```python
   from civi_py.core.config import CiviSettings
   from civi_rocket import CiviRocket, CiviRocketConfig

   settings = CiviSettings(
       base_url="https://your-site.org/civicrm/ajax/api4",
       api_key="your-api-key",
   )
   config = CiviRocketConfig(settings=settings)
   civi = CiviRocket(config)
   ```

   ## Features

   - Automatic client lifecycle management
   - Dependency injection integration
   - Health check endpoint
   - Full type hints

   ## License

   MIT


Generic ASGI Middleware Reference
---------------------------------

For simple integrations, the built-in ASGI middleware provides a solid foundation.

``CiviASGIMiddleware`` works with any ASGI framework: Starlette, Quart, Falcon (ASGI mode), Blacksheep, and others.

Basic Usage
^^^^^^^^^^^

.. code-block:: python

   from civi_py.contrib.asgi import CiviASGIMiddleware
   from civi_py.core.config import CiviSettings

   settings = CiviSettings(
       base_url="https://example.org/civicrm/ajax/api4",
       api_key="your-api-key",
   )

   # Wrap your ASGI application
   app = CiviASGIMiddleware(your_app, settings=settings)

The middleware:

* Manages client lifecycle via ASGI lifespan protocol
* Injects the client into ``scope["state"]["civi_client"]``
* Falls back to lazy initialization if lifespan is not supported

Starlette Example
^^^^^^^^^^^^^^^^^

.. code-block:: python

   from starlette.applications import Starlette
   from starlette.routing import Route
   from starlette.responses import JSONResponse
   from civi_py.contrib.asgi import CiviASGIMiddleware


   async def list_contacts(request):
       client = request.state.civi_client
       response = await client.get("Contact", limit=10)
       return JSONResponse({"contacts": response.values})


   async def get_contact(request):
       contact_id = request.path_params["contact_id"]
       client = request.state.civi_client

       response = await client.get(
           "Contact",
           where=[["id", "=", contact_id]],
           limit=1,
       )

       if not response.values:
           return JSONResponse({"error": "Not found"}, status_code=404)

       return JSONResponse(response.values[0])


   routes = [
       Route("/contacts", list_contacts),
       Route("/contacts/{contact_id:int}", get_contact),
   ]

   app = Starlette(routes=routes)
   app = CiviASGIMiddleware(app)

Using Environment Variables
^^^^^^^^^^^^^^^^^^^^^^^^^^^

If no settings are provided, the middleware loads from environment:

.. code-block:: bash

   export CIVI_BASE_URL=https://example.org/civicrm/ajax/api4
   export CIVI_API_KEY=your-api-key

.. code-block:: python

   # Settings loaded from environment automatically
   app = CiviASGIMiddleware(your_app)

Accessing the Client
^^^^^^^^^^^^^^^^^^^^

The client is stored in the ASGI scope state:

.. code-block:: python

   # In a raw ASGI handler
   async def my_handler(scope, receive, send):
       client = scope["state"]["civi_client"]
       response = await client.get("Contact", limit=5)
       # ...

   # In Starlette/FastAPI
   async def my_route(request):
       client = request.state.civi_client
       # ...

Using the helper function:

.. code-block:: python

   from civi_py.contrib.asgi import get_civi_client


   async def my_handler(scope, receive, send):
       try:
           client = get_civi_client(scope)
       except RuntimeError:
           # Middleware not installed
           ...

Custom Client Key
^^^^^^^^^^^^^^^^^

Change the key used to store the client:

.. code-block:: python

   app = CiviASGIMiddleware(
       your_app,
       settings=settings,
       client_key="civicrm",
   )

   # Access via custom key
   client = request.state.civicrm


Generic WSGI Middleware Reference
---------------------------------

``CiviWSGIMiddleware`` works with any WSGI framework: Bottle, Falcon (WSGI mode), Werkzeug, and others.

Basic Usage
^^^^^^^^^^^

.. code-block:: python

   from civi_py.contrib.wsgi import CiviWSGIMiddleware
   from civi_py.core.config import CiviSettings

   settings = CiviSettings(
       base_url="https://example.org/civicrm/ajax/api4",
       api_key="your-api-key",
   )

   # Wrap your WSGI application
   app = CiviWSGIMiddleware(your_app, settings=settings)

The middleware:

* Injects a ``SyncCiviClient`` into the WSGI environ
* Supports thread-local storage for multi-threaded servers
* Provides lazy initialization on first request

Bottle Example
^^^^^^^^^^^^^^

.. code-block:: python

   from bottle import Bottle, request, response
   from civi_py.contrib.wsgi import CiviWSGIMiddleware

   app = Bottle()


   @app.route("/contacts")
   def list_contacts():
       client = request.environ["civi.client"]
       result = client.get("Contact", limit=10)
       response.content_type = "application/json"
       return {"contacts": result.values}


   @app.route("/contacts/<contact_id:int>")
   def get_contact(contact_id):
       client = request.environ["civi.client"]
       result = client.get(
           "Contact",
           where=[["id", "=", contact_id]],
           limit=1,
       )

       if not result.values:
           response.status = 404
           return {"error": "Not found"}

       return result.values[0]


   # Wrap the WSGI app
   application = CiviWSGIMiddleware(app)

Falcon Example
^^^^^^^^^^^^^^

.. code-block:: python

   import falcon
   from civi_py.contrib.wsgi import CiviWSGIMiddleware


   class ContactResource:
       def on_get(self, req, resp):
           client = req.env["civi.client"]
           result = client.get("Contact", limit=10)
           resp.media = {"contacts": result.values}


   class ContactDetailResource:
       def on_get(self, req, resp, contact_id):
           client = req.env["civi.client"]
           result = client.get(
               "Contact",
               where=[["id", "=", contact_id]],
               limit=1,
           )

           if not result.values:
               raise falcon.HTTPNotFound()

           resp.media = result.values[0]


   app = falcon.App()
   app.add_route("/contacts", ContactResource())
   app.add_route("/contacts/{contact_id:int}", ContactDetailResource())

   application = CiviWSGIMiddleware(app)

Accessing the Client
^^^^^^^^^^^^^^^^^^^^

The client is stored in the WSGI environ dictionary:

.. code-block:: python

   # Direct access
   client = environ["civi.client"]

   # Using helper function
   from civi_py.contrib.wsgi import get_client_from_environ

   client = get_client_from_environ(environ)

Framework specific access:

.. code-block:: python

   # Flask
   from flask import request
   client = request.environ["civi.client"]

   # Bottle
   from bottle import request
   client = request.environ["civi.client"]

   # Falcon
   client = req.env["civi.client"]

   # Werkzeug
   client = request.environ["civi.client"]

Thread Safety
^^^^^^^^^^^^^

Thread-local mode (default) creates a separate client per thread:

.. code-block:: python

   # Safe for Gunicorn sync workers
   app = CiviWSGIMiddleware(your_app, use_thread_local=True)

Shared mode uses a single client across all threads:

.. code-block:: python

   # Single threaded environments only
   app = CiviWSGIMiddleware(your_app, use_thread_local=False)

Cleanup
^^^^^^^

Call ``close()`` during application shutdown:

.. code-block:: python

   import atexit

   middleware = CiviWSGIMiddleware(your_app)
   atexit.register(middleware.close)

   application = middleware


Environment Variables
---------------------

All middleware and integrations use these environment variables when settings are not explicitly provided:

.. code-block:: bash

   CIVI_BASE_URL=https://example.org/civicrm/ajax/api4
   CIVI_API_KEY=your-api-key
   CIVI_SITE_KEY=your-site-key    # Optional
   CIVI_TIMEOUT=30                # Default: 30 seconds
   CIVI_VERIFY_SSL=true           # Default: true
   CIVI_DEBUG=false               # Default: false
   CIVI_MAX_RETRIES=3             # Default: 3


Summary
-------

Building a custom framework integration provides idiomatic access to civi-py within your framework of choice. The integration architecture supports three levels of complexity:

1. **Quick start**: Use ``CiviASGIMiddleware`` or ``CiviWSGIMiddleware`` for basic client injection
2. **Custom integration**: Extend ``BaseIntegration`` for framework specific features like dependency injection and CLI commands
3. **Community package**: Publish your integration with entry points for automatic discovery

The key steps for a custom integration are:

1. Extend ``BaseIntegration`` and define your configuration dataclass
2. Implement ``init_app()`` to hook into framework lifecycle events
3. Register dependency providers for clean handler signatures
4. Add optional features like health checks and CLI commands
5. Write comprehensive tests at unit, integration, and E2E levels
6. Publish with the ``civi_py.integrations`` entry point for discovery


See Also
--------

* :doc:`/getting-started/quickstart` for basic civi-py usage
* :doc:`/concepts/client` for CiviClient API details
* :doc:`/api/config` for CiviSettings reference
* :doc:`django` for a Tier 1 integration example
* :doc:`flask` for a Tier 2 integration example
