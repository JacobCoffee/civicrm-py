"""Flask CLI commands for civi-py.

Provides CLI commands for Flask applications to interact with CiviCRM:

- flask civi-check: Verify CiviCRM API connectivity
- flask civi-shell: Interactive Python shell with CiviCRM client pre-loaded

Example:
    After registering the extension, use CLI commands:

    $ flask civi-check
    CiviCRM API Status:
      URL: https://example.org/civicrm/ajax/api4
      Status: Connected
      Response Time: 45ms

    $ flask civi-shell
    >>> client.get("Contact", limit=1)
    APIResponse(values=[...], count=1)
"""

from __future__ import annotations

import code
import logging
import sys
import time
from typing import TYPE_CHECKING, Any

import click

# Check if Flask is available
try:
    from flask import current_app
    from flask.cli import with_appcontext

    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

    class _CurrentAppStub:
        """Stub for Flask current_app when Flask is not installed."""

        def __getattr__(self, name: str) -> Any:
            raise ImportError("Flask required: pip install civi-py[flask]")

    current_app = _CurrentAppStub()

    def with_appcontext(f: Any) -> Any:
        """Stub decorator when Flask is not installed."""
        return f


if TYPE_CHECKING:
    from civicrm_py.core.client import SyncCiviClient
    from civicrm_py.core.config import CiviSettings

logger = logging.getLogger(__name__)


def _get_civi_settings() -> CiviSettings:
    """Get CiviSettings from Flask app config.

    Returns:
        CiviSettings instance.

    Raises:
        RuntimeError: If CiviFlask extension is not initialized.
    """
    civi_ext = current_app.extensions.get("civi")
    if civi_ext is None:
        msg = "CiviFlask extension not initialized. Call init_app() on your Flask app."
        raise RuntimeError(msg)
    return civi_ext.settings


def _get_civi_client() -> SyncCiviClient:
    """Get SyncCiviClient instance.

    Returns:
        SyncCiviClient instance.

    Raises:
        RuntimeError: If CiviFlask extension is not initialized.
    """
    civi_ext = current_app.extensions.get("civi")
    if civi_ext is None:
        msg = "CiviFlask extension not initialized. Call init_app() on your Flask app."
        raise RuntimeError(msg)
    return civi_ext.get_client()


@click.command("civi-check")
@with_appcontext
def civi_check_command() -> None:
    """Check CiviCRM API connectivity and display status.

    Performs a lightweight API call to verify that the CiviCRM API is
    reachable and responding. Displays connection status, response time,
    and configuration details.

    Example:
        $ flask civi-check
        CiviCRM API Status:
          URL: https://example.org/civicrm/ajax/api4
          Status: Connected
          API Version: 4
          Response Time: 45ms
    """
    try:
        settings = _get_civi_settings()
        client = _get_civi_client()
    except RuntimeError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)

    click.echo("CiviCRM API Status:")
    click.echo(f"  URL: {settings.base_url}")
    click.echo(f"  Auth Type: {settings.auth_type}")
    click.echo(f"  Timeout: {settings.timeout}s")
    click.echo(f"  Verify SSL: {settings.verify_ssl}")
    click.echo()

    # Perform connectivity check
    click.echo("Checking connectivity...")
    start_time = time.perf_counter()

    try:
        # Use System.check for lightweight connectivity test
        response = client.request("System", "check", {})
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        click.echo(click.style("  Status: Connected", fg="green"))
        click.echo("  API Version: 4")
        click.echo(f"  Response Time: {elapsed_ms:.1f}ms")

        # Display some system info if available
        if response.values:
            click.echo()
            click.echo("System Info:")
            for item in response.values[:5]:  # Show first 5 items
                if isinstance(item, dict):
                    name = item.get("name", item.get("title", "Unknown"))
                    status = item.get("status", item.get("severity", "info"))
                    message = item.get("message", "")
                    color = "green" if status in ("ok", "info") else "yellow" if status == "warning" else "red"
                    click.echo(f"    {click.style(name, fg=color)}: {message}")

    except Exception as e:  # noqa: BLE001 - CLI commands should catch all errors for user feedback
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        click.echo(click.style("  Status: Failed", fg="red"))
        click.echo(f"  Response Time: {elapsed_ms:.1f}ms")
        click.echo(f"  Error: {e}")
        sys.exit(1)


@click.command("civi-shell")
@click.option(
    "--no-banner",
    is_flag=True,
    default=False,
    help="Skip printing the banner on startup.",
)
@with_appcontext
def civi_shell_command(*, no_banner: bool) -> None:
    """Launch an interactive Python shell with CiviCRM client pre-loaded.

    Provides an interactive Python environment with the CiviCRM client
    and common imports pre-loaded for quick exploration and debugging.

    Available variables in the shell:
        - client: SyncCiviClient instance for API calls
        - settings: CiviSettings with current configuration
        - app: Flask application instance

    Example:
        $ flask civi-shell
        CiviCRM Shell
        Available:
          client  - SyncCiviClient (connected to https://example.org/...)
          settings - CiviSettings
          app     - Flask application

        >>> contacts = client.get("Contact", limit=5)
        >>> print(contacts.values)
        [{'id': 1, 'display_name': 'John Doe'}, ...]

        >>> response = client.get_fields("Contact")
        >>> [f["name"] for f in response.values[:5]]
        ['id', 'contact_type', 'do_not_email', ...]
    """
    try:
        settings = _get_civi_settings()
        client = _get_civi_client()
    except RuntimeError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)

    # Prepare the namespace with useful imports and objects
    # Note: _get_current_object is the documented way to unwrap LocalProxy
    namespace: dict[str, object] = {
        "client": client,
        "settings": settings,
        "app": current_app._get_current_object(),  # noqa: SLF001 - Documented Flask API
    }

    # Try to import additional useful modules
    try:
        from civicrm_py.core.serialization import APIRequest, APIResponse

        namespace["APIRequest"] = APIRequest
        namespace["APIResponse"] = APIResponse
    except ImportError:
        pass

    # Print banner unless suppressed
    if not no_banner:
        banner_lines = [
            "",
            click.style("CiviCRM Shell", bold=True),
            f"Connected to: {settings.base_url}",
            "",
            "Available:",
            f"  {click.style('client', fg='cyan')}   - SyncCiviClient instance",
            f"  {click.style('settings', fg='cyan')} - CiviSettings configuration",
            f"  {click.style('app', fg='cyan')}      - Flask application instance",
            "",
            "Example:",
            "  >>> contacts = client.get('Contact', limit=5)",
            "  >>> print(contacts.values)",
            "",
        ]
        banner = "\n".join(banner_lines)
    else:
        banner = ""

    # Try to use IPython if available for better experience
    try:
        from IPython import start_ipython

        sys.exit(start_ipython(argv=[], user_ns=namespace))
    except ImportError:
        # Fall back to standard Python REPL
        code.interact(banner=banner, local=namespace, exitmsg="")


__all__ = [
    "civi_check_command",
    "civi_shell_command",
]
