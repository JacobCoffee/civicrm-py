"""Litestar CLI commands for CiviCRM integration.

Provides CLI commands for CiviCRM operations when using the Litestar framework:
- ``litestar civi check`` - Verify CiviCRM connection and configuration
- ``litestar civi shell`` - Interactive Python shell with CiviCRM client
- ``litestar civi sync`` - Discover entities and generate stubs

Usage:
    litestar civi check
    litestar civi check --verbose
    litestar civi shell
    litestar civi shell --notebook
    litestar civi sync --list-entities
    litestar civi sync --entity Contact --show-fields
"""

from __future__ import annotations

import code
import sys
from typing import TYPE_CHECKING

from click import group, option
from litestar.cli._utils import LitestarGroup, console

from civicrm_py.core.client import SyncCiviClient

if TYPE_CHECKING:
    from litestar import Litestar


@group(cls=LitestarGroup, name="civi")
def civi_group() -> None:
    """Manage CiviCRM operations."""


@civi_group.command(name="check", help="Verify CiviCRM connection and configuration.")
@option("--verbose", "-v", is_flag=True, default=False, help="Enable verbose output.")
@option("--quiet", "-q", is_flag=True, default=False, help="Only show errors and final status.")
@option("--test-entity", type=str, default="Contact", help="Entity to use for API test.")
def civi_check(
    app: Litestar,
    verbose: bool,
    quiet: bool,
    test_entity: str,
) -> None:
    """Verify CiviCRM connection, settings, and API connectivity."""
    from civicrm_py.contrib.litestar.plugin import CiviPlugin

    plugin = app.plugins.get(CiviPlugin)
    if plugin is None:
        console.print("[red]Error: CiviPlugin not found in application[/]")
        sys.exit(1)

    issues: list[str] = []
    warnings: list[str] = []

    if not quiet:
        console.print()
        console.rule("[bold blue]CiviCRM Configuration Check[/]", align="left")
        console.print()

    # Step 1: Check configuration
    settings = _check_configuration(plugin, issues, verbose, quiet)

    # Step 2: Check connection if settings are available
    if settings is not None:
        _check_connection(settings, test_entity, issues, warnings, verbose, quiet)

    # Summary
    _print_summary(issues, warnings, quiet)


def _check_configuration(
    plugin: object,
    issues: list[str],
    verbose: bool,
    quiet: bool,
) -> object | None:
    """Check CiviCRM configuration."""
    if not quiet:
        console.print("[bold]1. Configuration[/]")

    settings = None

    try:
        # Get settings from plugin config
        config = plugin.config  # type: ignore[attr-defined]
        if config.settings is not None:
            settings = config.settings
            if not quiet:
                console.print("   [green]✓[/] Plugin configured with explicit settings")
        else:
            # Try to load from environment
            from civicrm_py.core.config import CiviSettings

            try:
                settings = CiviSettings.from_env()
                if not quiet:
                    console.print("   [green]✓[/] Loaded settings from environment variables")
            except ValueError as e:
                issues.append(f"Environment configuration error: {e}")
                if not quiet:
                    console.print(f"   [red]✗[/] {e}")
                return None

        # Display settings info
        if settings and verbose and not quiet:
            api_key_display = "****" if settings.api_key else "(not set)"
            site_key_display = "****" if settings.site_key else "(not set)"
            console.print(f"   Base URL: {settings.base_url}")
            console.print(f"   Auth Type: {settings.auth_type}")
            console.print(f"   API Key: {api_key_display}")
            console.print(f"   Site Key: {site_key_display}")
            console.print(f"   Timeout: {settings.timeout}s")
            console.print(f"   Verify SSL: {settings.verify_ssl}")

    except Exception as e:
        issues.append(f"Configuration error: {e}")
        if not quiet:
            console.print(f"   [red]✗[/] {e}")

    if not quiet:
        console.print()

    return settings


def _check_connection(
    settings: object,
    test_entity: str,
    issues: list[str],
    warnings: list[str],
    verbose: bool,
    quiet: bool,
) -> None:
    """Check API connection."""
    if not quiet:
        console.print("[bold]2. API Connection[/]")

    try:
        from civicrm_py.core.client import SyncCiviClient

        with SyncCiviClient(settings) as client:  # type: ignore[arg-type]
            if not quiet:
                console.print(f"   Testing connection to: {settings.base_url}")  # type: ignore[attr-defined]

            try:
                response = client.get_fields(test_entity)
                field_count = len(response.values or [])

                if not quiet:
                    console.print("   [green]✓[/] Connected successfully")
                    console.print(
                        f"   [green]✓[/] {test_entity} entity accessible ({field_count} fields)",
                    )

                if verbose and response.values:
                    console.print()
                    console.print(f"   Sample fields from {test_entity}:")
                    for field in (response.values or [])[:5]:
                        field_name = field.get("name", "unknown")
                        field_type = field.get("data_type", "unknown")
                        console.print(f"     - {field_name}: {field_type}")
                    if field_count > 5:
                        console.print(f"     ... and {field_count - 5} more")

            except Exception as e:
                issues.append(f"Failed to query {test_entity}: {e}")
                if not quiet:
                    console.print(f"   [red]✗[/] {e}")
                return

            # List available entities if verbose
            if verbose:
                _check_available_entities(client, warnings, quiet)

    except ImportError as e:
        issues.append(f"Could not import civicrm_py: {e}")
        if not quiet:
            console.print(f"   [red]✗[/] Import error: {e}")

    except Exception as e:
        error_msg = str(e)
        if "connection" in error_msg.lower() or "connect" in error_msg.lower():
            issues.append(f"Connection failed: {error_msg}")
        elif "auth" in error_msg.lower() or "401" in error_msg:
            issues.append(f"Authentication failed: {error_msg}")
        elif "403" in error_msg:
            issues.append(f"Permission denied: {error_msg}")
        elif "404" in error_msg:
            issues.append(f"API endpoint not found: {error_msg}")
        else:
            issues.append(f"API error: {error_msg}")

        if not quiet:
            console.print(f"   [red]✗[/] {error_msg}")

    if not quiet:
        console.print()


def _check_available_entities(
    client: object,
    warnings: list[str],
    quiet: bool,
) -> None:
    """Check and list available entities."""
    if not quiet:
        console.print()
        console.print("[bold]3. Available Entities[/]")

    try:
        response = client.request("Entity", "get", {})  # type: ignore[attr-defined]
        entities = response.values or []

        if not quiet:
            console.print(f"   [green]✓[/] Found {len(entities)} entities")

            # Group by type
            by_type: dict[str, list[str]] = {}
            for entity in entities:
                etype = entity.get("type", "other")
                name = entity.get("name", "unknown")
                if etype not in by_type:
                    by_type[etype] = []
                by_type[etype].append(name)

            for etype, names in sorted(by_type.items()):
                preview = ", ".join(sorted(names)[:5])
                if len(names) > 5:
                    preview += f", ... ({len(names)} total)"
                console.print(f"   {etype.title()}: {preview}")

    except Exception as e:
        warnings.append(f"Could not list entities: {e}")
        if not quiet:
            console.print(f"   [yellow]![/] Could not list entities: {e}")


def _print_summary(issues: list[str], warnings: list[str], quiet: bool) -> None:
    """Print check summary."""
    if quiet and not issues:
        console.print("[green]CiviCRM configuration OK[/]")
        return

    if not quiet:
        console.print()
        console.print("[bold]Summary[/]")

    if issues:
        console.print(f"   [red]{len(issues)} issue(s) found:[/]")
        for issue in issues:
            console.print(f"     [red]•[/] {issue}")
        console.print()
        sys.exit(1)

    if warnings:
        console.print(f"   [yellow]{len(warnings)} warning(s):[/]")
        for warning in warnings:
            console.print(f"     [yellow]•[/] {warning}")

    console.print()
    console.print("   [green]✓ All checks passed![/]")


@civi_group.command(name="shell", help="Interactive Python shell with CiviCRM client.")
@option("--notebook", "-n", is_flag=True, default=False, help="Use IPython if available.")
@option("--no-startup", is_flag=True, default=False, help="Skip importing CiviCRM entities.")
def civi_shell(
    app: Litestar,
    notebook: bool,
    no_startup: bool,
) -> None:
    """Start an interactive Python shell with CiviCRM client pre-configured."""
    from civicrm_py.contrib.litestar.plugin import CiviPlugin

    plugin = app.plugins.get(CiviPlugin)
    if plugin is None:
        console.print("[red]Error: CiviPlugin not found in application[/]")
        sys.exit(1)

    # Build namespace
    namespace = _build_shell_namespace(plugin, no_startup)

    # Build banner
    banner = _build_shell_banner(namespace, no_startup)

    if notebook:
        _run_ipython_shell(namespace, banner)
    else:
        _run_python_shell(namespace, banner)


def _build_shell_namespace(plugin: object, no_startup: bool) -> dict[str, object]:
    """Build the shell namespace with CiviCRM imports."""
    namespace: dict[str, object] = {}

    if no_startup:
        return namespace

    # Import CiviCRM core
    try:
        from civicrm_py.core.client import CiviClient, SyncCiviClient
        from civicrm_py.core.config import CiviSettings, get_settings

        namespace["CiviClient"] = CiviClient
        namespace["SyncCiviClient"] = SyncCiviClient
        namespace["CiviSettings"] = CiviSettings
        namespace["get_settings"] = get_settings
    except ImportError as e:
        console.print(f"[yellow]Could not import civicrm_py.core: {e}[/]")

    # Import entities
    try:
        from civicrm_py.entities import (
            Activity,
            Address,
            BaseEntity,
            Contact,
            Contribution,
            Email,
            EntityDiscovery,
            Event,
            Group,
            GroupContact,
            Household,
            Individual,
            Membership,
            Note,
            Organization,
            Participant,
            Phone,
            Tag,
        )

        namespace["Activity"] = Activity
        namespace["Address"] = Address
        namespace["BaseEntity"] = BaseEntity
        namespace["Contact"] = Contact
        namespace["Contribution"] = Contribution
        namespace["Email"] = Email
        namespace["EntityDiscovery"] = EntityDiscovery
        namespace["Event"] = Event
        namespace["Group"] = Group
        namespace["GroupContact"] = GroupContact
        namespace["Household"] = Household
        namespace["Individual"] = Individual
        namespace["Membership"] = Membership
        namespace["Note"] = Note
        namespace["Organization"] = Organization
        namespace["Participant"] = Participant
        namespace["Phone"] = Phone
        namespace["Tag"] = Tag
    except ImportError as e:
        console.print(f"[yellow]Could not import civicrm_py.entities: {e}[/]")

    # Import query components
    try:
        from civicrm_py.query import EntityManager, QuerySet

        namespace["EntityManager"] = EntityManager
        namespace["QuerySet"] = QuerySet
    except ImportError as e:
        console.print(f"[yellow]Could not import civicrm_py.query: {e}[/]")

    # Import exceptions
    try:
        from civicrm_py.core.exceptions import (
            CiviAPIError,
            CiviAuthError,
            CiviConfigError,
            CiviConnectionError,
            CiviError,
            DoesNotExist,
            MultipleObjectsReturned,
        )

        namespace["CiviError"] = CiviError
        namespace["CiviAPIError"] = CiviAPIError
        namespace["CiviAuthError"] = CiviAuthError
        namespace["CiviConfigError"] = CiviConfigError
        namespace["CiviConnectionError"] = CiviConnectionError
        namespace["DoesNotExist"] = DoesNotExist
        namespace["MultipleObjectsReturned"] = MultipleObjectsReturned
    except ImportError as e:
        console.print(f"[yellow]Could not import civicrm_py.core.exceptions: {e}[/]")

    # Create client from plugin settings
    try:
        config = plugin.config  # type: ignore[attr-defined]
        if config.settings is not None:
            settings = config.settings
        else:
            from civicrm_py.core.config import CiviSettings

            settings = CiviSettings.from_env()

        namespace["settings"] = settings
        namespace["client"] = SyncCiviClient(settings)
        console.print("[green]Created client from plugin settings (sync mode)[/]")
    except Exception as e:
        console.print(
            f"[yellow]Could not auto-configure client: {e}\n"
            "Use SyncCiviClient(base_url=..., api_key=...) to create manually.[/]",
        )

    # Import asyncio for async operations
    import asyncio

    namespace["asyncio"] = asyncio

    return namespace


def _build_shell_banner(namespace: dict[str, object], no_startup: bool) -> str:
    """Build the shell startup banner."""
    if no_startup:
        return "CiviCRM Shell (no auto-imports)"

    lines = [
        "",
        "CiviCRM Interactive Shell",
        "=" * 40,
        "",
    ]

    # List imported entities
    entities = [
        "Activity",
        "Address",
        "Contact",
        "Contribution",
        "Email",
        "Event",
        "Group",
        "Household",
        "Individual",
        "Membership",
        "Note",
        "Organization",
        "Participant",
        "Phone",
        "Tag",
    ]
    available_entities = [e for e in entities if e in namespace]
    if available_entities:
        lines.append("Entities: " + ", ".join(available_entities))

    # List available utilities
    utils = ["CiviClient", "SyncCiviClient", "EntityDiscovery", "QuerySet"]
    available_utils = [u for u in utils if u in namespace]
    if available_utils:
        lines.append("Utilities: " + ", ".join(available_utils))

    # Note about pre-configured client
    if "client" in namespace:
        lines.append("")
        lines.append("A sync client is available as 'client'.")
        lines.append("Use 'settings' to view current configuration.")
    else:
        lines.append("")
        lines.append("No client configured. Create one with:")
        lines.append("  client = SyncCiviClient(base_url=..., api_key=...)")

    lines.extend(
        [
            "",
            "Example usage:",
            "  result = client.get('Contact', limit=10)",
            "  for contact in result.values:",
            "      print(contact['display_name'])",
            "",
            "For async operations:",
            "  async with CiviClient() as async_client:",
            "      result = await async_client.get('Contact')",
            "",
        ],
    )

    return "\n".join(lines)


def _run_ipython_shell(namespace: dict[str, object], banner: str) -> None:
    """Start IPython shell if available."""
    try:
        from IPython import start_ipython

        console.print(banner)
        start_ipython(
            argv=["--InteractiveShellApp.exec_lines=['import asyncio']"],
            user_ns=namespace,
        )
    except ImportError:
        console.print(
            "[yellow]IPython is not installed. Falling back to standard Python shell.\n"
            "Install IPython with: pip install ipython[/]",
        )
        _run_python_shell(namespace, banner)


def _run_python_shell(namespace: dict[str, object], banner: str) -> None:
    """Start standard Python interactive shell."""
    try:
        import readline
        import rlcompleter

        readline.set_completer(rlcompleter.Completer(namespace).complete)
        readline.parse_and_bind("tab: complete")
    except ImportError:
        pass  # readline not available on all platforms

    shell = code.InteractiveConsole(locals=namespace)
    shell.interact(banner=banner, exitmsg="Exiting CiviCRM shell...")


@civi_group.command(name="sync", help="Discover CiviCRM entities and generate stubs.")
@option("--list-entities", "-l", is_flag=True, default=False, help="List all available entities.")
@option("--entity", "-e", type=str, help="Specific entity to inspect.")
@option("--show-fields", "-f", is_flag=True, default=False, help="Show field definitions.")
@option("--show-actions", "-a", is_flag=True, default=False, help="Show available actions.")
@option("--generate-stub", "-g", is_flag=True, default=False, help="Generate Python stub file.")
@option("--output", "-o", type=str, help="Output file path for stub (default: stdout).")
@option("--filter-type", type=str, help="Filter entities by type.")
@option("--custom-only", is_flag=True, default=False, help="Only show custom entities.")
@option("--include-readonly", is_flag=True, default=False, help="Include readonly fields in stub.")
def civi_sync(
    app: Litestar,
    list_entities: bool,
    entity: str | None,
    show_fields: bool,
    show_actions: bool,
    generate_stub: bool,
    output: str | None,
    filter_type: str | None,
    custom_only: bool,
    include_readonly: bool,
) -> None:
    """Discover CiviCRM entities and optionally generate Python stubs."""
    from civicrm_py.contrib.litestar.plugin import CiviPlugin

    plugin = app.plugins.get(CiviPlugin)
    if plugin is None:
        console.print("[red]Error: CiviPlugin not found in application[/]")
        sys.exit(1)

    # Validate arguments
    if not list_entities and not entity:
        console.print("[red]Please specify --list-entities or --entity <name>[/]")
        sys.exit(1)

    if generate_stub and not entity:
        console.print("[red]--generate-stub requires --entity <name>[/]")
        sys.exit(1)

    # Get client
    client = _get_sync_client(plugin)
    if client is None:
        sys.exit(1)
        return  # Unreachable, but helps type narrowing
    try:
        if list_entities:
            _list_entities(client, filter_type, custom_only)

        if entity:
            if show_fields:
                _show_entity_fields(client, entity)

            if show_actions:
                _show_entity_actions(client, entity)

            if generate_stub:
                _generate_entity_stub(client, entity, output, include_readonly)

            # If no specific action requested, show basic info
            if not show_fields and not show_actions and not generate_stub:
                _show_entity_info(client, entity)
    finally:
        client.close()


def _get_sync_client(plugin: object) -> SyncCiviClient | None:
    """Get a configured sync CiviCRM client."""
    try:
        from civicrm_py.core.client import SyncCiviClient
        from civicrm_py.core.config import CiviSettings

        config = plugin.config  # type: ignore[attr-defined]
        if config.settings is not None:
            settings = config.settings
        else:
            settings = CiviSettings.from_env()

        return SyncCiviClient(settings)

    except ValueError as e:
        console.print(f"[red]Configuration error: {e}[/]")
        return None
    except ImportError as e:
        console.print(f"[red]Import error: {e}[/]")
        return None


def _list_entities(
    client: object,
    filter_type: str | None,
    custom_only: bool,
) -> None:
    """List available CiviCRM entities."""
    console.print()
    console.rule("[bold blue]Available CiviCRM Entities[/]", align="left")
    console.print()

    try:
        response = client.request("Entity", "get", {})  # type: ignore[attr-defined]
        entities = response.values or []

        # Apply filters
        if custom_only:
            entities = [e for e in entities if e.get("name", "").startswith("Custom_")]

        if filter_type:
            entities = [e for e in entities if e.get("type") == filter_type]

        if not entities:
            console.print("[yellow]No entities found matching criteria[/]")
            return

        # Group by type
        by_type: dict[str, list[dict[str, object]]] = {}
        for ent in entities:
            etype = ent.get("type", "other")
            if etype not in by_type:
                by_type[etype] = []
            by_type[etype].append(ent)

        # Display
        for etype in sorted(by_type.keys()):
            type_entities = by_type[etype]
            console.print(f"[bold]{etype.title()} Entities ({len(type_entities)})[/]")

            for ent in sorted(type_entities, key=lambda x: x.get("name", "")):
                name = ent.get("name", "unknown")
                title = ent.get("title") or ent.get("label", "")
                description = ent.get("description", "")

                line = f"  {name}"
                if title and title != name:
                    line += f" - {title}"
                console.print(line)

                if description:
                    if len(str(description)) > 70:
                        description = str(description)[:67] + "..."
                    console.print(f"    [dim]{description}[/]")

            console.print()

        console.print(f"[green]Total: {len(entities)} entities[/]")

    except Exception as e:
        console.print(f"[red]Failed to list entities: {e}[/]")


def _show_entity_info(client: object, entity_name: str) -> None:
    """Show basic information about an entity."""
    console.print()
    console.rule(f"[bold blue]Entity: {entity_name}[/]", align="left")
    console.print()

    try:
        response = client.request(  # type: ignore[attr-defined]
            "Entity",
            "get",
            {"where": [["name", "=", entity_name]]},
        )

        if not response.values:
            console.print(f"[red]Entity '{entity_name}' not found[/]")
            return

        ent = response.values[0]

        console.print(f"Name:        {ent.get('name', 'N/A')}")
        console.print(f"Title:       {ent.get('title') or ent.get('label', 'N/A')}")
        console.print(f"Type:        {ent.get('type', 'N/A')}")
        console.print(f"Description: {ent.get('description', 'N/A')}")
        console.print(f"Searchable:  {ent.get('searchable', True)}")
        console.print(f"Label Field: {ent.get('label_field', 'N/A')}")

        pk = ent.get("primary_key")
        if pk:
            if isinstance(pk, list):
                pk = ", ".join(pk)
            console.print(f"Primary Key: {pk}")

        console.print()
        console.print("[dim]Use --show-fields to see field definitions[/]")
        console.print("[dim]Use --show-actions to see available actions[/]")

    except Exception as e:
        console.print(f"[red]Failed to get entity info: {e}[/]")


def _show_entity_fields(client: object, entity_name: str) -> None:
    """Show field definitions for an entity."""
    console.print()
    console.rule(f"[bold blue]Fields for {entity_name}[/]", align="left")
    console.print()

    try:
        response = client.get_fields(entity_name)  # type: ignore[attr-defined]
        fields = response.values or []

        if not fields:
            console.print("[yellow]No fields found[/]")
            return

        # Group fields
        required_fields = []
        optional_fields = []
        readonly_fields = []

        for field in fields:
            if field.get("readonly"):
                readonly_fields.append(field)
            elif field.get("required"):
                required_fields.append(field)
            else:
                optional_fields.append(field)

        # Display required fields
        if required_fields:
            console.print("[bold]Required Fields[/]")
            for field in sorted(required_fields, key=lambda x: x.get("name", "")):
                _print_field(field)
            console.print()

        # Display optional fields
        if optional_fields:
            console.print("[bold]Optional Fields[/]")
            for field in sorted(optional_fields, key=lambda x: x.get("name", "")):
                _print_field(field)
            console.print()

        # Display readonly fields
        if readonly_fields:
            console.print("[bold]Read-only Fields[/]")
            for field in sorted(readonly_fields, key=lambda x: x.get("name", "")):
                _print_field(field)
            console.print()

        console.print(
            f"[green]Total: {len(fields)} fields "
            f"({len(required_fields)} required, "
            f"{len(optional_fields)} optional, "
            f"{len(readonly_fields)} readonly)[/]",
        )

    except Exception as e:
        console.print(f"[red]Failed to get fields: {e}[/]")


def _print_field(field: dict[str, object]) -> None:
    """Print a single field definition."""
    name = field.get("name", "unknown")
    data_type = field.get("data_type", "unknown")
    title = field.get("title", "")
    description = field.get("description", "")
    fk_entity = field.get("fk_entity")
    default = field.get("default_value")

    line = f"  {name}: [cyan]{data_type}[/]"

    if fk_entity:
        line += f" [dim]-> {fk_entity}[/]"

    if default is not None:
        line += f" [dim]= {default!r}[/]"

    console.print(line)

    if title and title != name:
        console.print(f"    [dim]Title: {title}[/]")

    if description:
        desc_str = str(description)
        if len(desc_str) > 70:
            desc_str = desc_str[:67] + "..."
        console.print(f"    [dim]{desc_str}[/]")


def _show_entity_actions(client: object, entity_name: str) -> None:
    """Show available actions for an entity."""
    console.print()
    console.rule(f"[bold blue]Actions for {entity_name}[/]", align="left")
    console.print()

    try:
        response = client.request(entity_name, "getActions", {})  # type: ignore[attr-defined]
        actions = response.values or []

        if not actions:
            console.print("[yellow]No actions found[/]")
            return

        for action in sorted(actions, key=lambda x: x.get("name", "")):
            name = action.get("name", "unknown")
            description = action.get("description", "")

            console.print(f"  [cyan]{name}[/]")
            if description:
                desc_str = str(description)
                if len(desc_str) > 60:
                    desc_str = desc_str[:57] + "..."
                console.print(f"    [dim]{desc_str}[/]")

        console.print()
        console.print(f"[green]Total: {len(actions)} actions[/]")

    except Exception as e:
        console.print(f"[red]Failed to get actions: {e}[/]")


def _generate_entity_stub(
    client: object,
    entity_name: str,
    output_path: str | None,
    include_readonly: bool,
) -> None:
    """Generate Python stub file for an entity."""
    from pathlib import Path

    try:
        response = client.get_fields(entity_name)  # type: ignore[attr-defined]
        fields = response.values or []

        if not fields:
            console.print(f"[red]No fields found for {entity_name}[/]")
            return

        # Generate stub content
        stub = _build_stub(entity_name, fields, include_readonly)

        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(stub)
            console.print(f"[green]Generated stub: {output_path}[/]")
        else:
            console.print()
            console.rule(f"[bold blue]Stub for {entity_name}[/]", align="left")
            console.print(stub)

    except Exception as e:
        console.print(f"[red]Failed to generate stub: {e}[/]")


def _build_stub(
    entity_name: str,
    fields: list[dict[str, object]],
    include_readonly: bool,
) -> str:
    """Build Python stub content for an entity."""
    # Type mapping
    type_map = {
        "String": "str",
        "Text": "str",
        "Memo": "str",
        "Integer": "int",
        "Boolean": "bool",
        "Float": "float",
        "Money": "float",
        "Date": "str",
        "Datetime": "str",
        "Timestamp": "int",
        "Array": "list[Any]",
        "Object": "dict[str, Any]",
        "Json": "dict[str, Any]",
        "Blob": "bytes",
    }

    lines = [
        '"""Auto-generated entity stub for CiviCRM.',
        "",
        f"Entity: {entity_name}",
        "Generated by: litestar civi sync --generate-stub",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Any",
        "",
        "from civicrm_py.entities.base import BaseEntity",
        "",
        "",
        f"class {entity_name}(BaseEntity):",
        f'    """CiviCRM {entity_name} entity.',
        "",
        "    Auto-generated from CiviCRM API metadata.",
        '    """',
        "",
        f'    __entity_name__ = "{entity_name}"',
        "",
    ]

    # Process fields
    field_lines = []
    for field in sorted(
        fields,
        key=lambda x: (not x.get("required", False), str(x.get("name", ""))),
    ):
        name = field.get("name", "")

        # Skip internal fields
        if str(name).startswith("_"):
            continue

        # Skip readonly unless requested
        if field.get("readonly") and not include_readonly:
            continue

        data_type = str(field.get("data_type", "String"))
        py_type = type_map.get(data_type, "Any")

        required = field.get("required", False)
        default = field.get("default_value")
        description = field.get("title") or field.get("description", "")
        fk_entity = field.get("fk_entity")

        # Build type annotation
        if not required:
            py_type = f"{py_type} | None"

        # Build default value
        if default is not None:
            if isinstance(default, str):
                default_str = f' = "{default}"'
            else:
                default_str = f" = {default!r}"
        elif not required:
            default_str = " = None"
        else:
            default_str = ""

        # Build comment
        comment_parts = []
        if description:
            comment_parts.append(str(description))
        if fk_entity:
            comment_parts.append(f"FK -> {fk_entity}")
        if field.get("readonly"):
            comment_parts.append("(readonly)")

        comment = f"  # {'; '.join(comment_parts)}" if comment_parts else ""

        field_lines.append(f"    {name}: {py_type}{default_str}{comment}")

    if field_lines:
        lines.extend(field_lines)
    else:
        lines.append("    pass")

    lines.append("")
    return "\n".join(lines)


__all__ = ["civi_check", "civi_group", "civi_shell", "civi_sync"]
