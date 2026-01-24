"""CiviCRM entity synchronization and discovery management command.

Discovers available CiviCRM entities from the API, displays entity metadata,
and optionally generates Python stubs for custom entities.

Usage:
    python manage.py sync_civi --list-entities
    python manage.py sync_civi --entity Contact --show-fields
    python manage.py sync_civi --entity Contact --generate-stub
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.core.management.base import BaseCommand, CommandError

if TYPE_CHECKING:
    from argparse import ArgumentParser


class Command(BaseCommand):
    """Discover and synchronize CiviCRM entities."""

    help = "Discover CiviCRM entities and optionally generate Python stubs."

    def add_arguments(self, parser: ArgumentParser) -> None:
        """Add command arguments.

        Args:
            parser: Argument parser instance.
        """
        parser.add_argument(
            "--list-entities",
            "-l",
            action="store_true",
            default=False,
            help="List all available CiviCRM entities.",
        )
        parser.add_argument(
            "--entity",
            "-e",
            type=str,
            help="Specific entity to inspect.",
        )
        parser.add_argument(
            "--show-fields",
            "-f",
            action="store_true",
            default=False,
            help="Show field definitions for the specified entity.",
        )
        parser.add_argument(
            "--show-actions",
            "-a",
            action="store_true",
            default=False,
            help="Show available actions for the specified entity.",
        )
        parser.add_argument(
            "--generate-stub",
            "-g",
            action="store_true",
            default=False,
            help="Generate Python stub file for the specified entity.",
        )
        parser.add_argument(
            "--output",
            "-o",
            type=str,
            help="Output file path for generated stub (default: stdout).",
        )
        parser.add_argument(
            "--filter-type",
            type=str,
            help="Filter entities by type (primary, secondary, bridge, etc.).",
        )
        parser.add_argument(
            "--custom-only",
            action="store_true",
            default=False,
            help="Only show custom entities.",
        )
        parser.add_argument(
            "--include-readonly",
            action="store_true",
            default=False,
            help="Include readonly fields in stub generation.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Execute the sync command.

        Args:
            *args: Positional arguments.
            **options: Command options.
        """
        list_entities = options["list_entities"]
        entity_name = options["entity"]
        show_fields = options["show_fields"]
        show_actions = options["show_actions"]
        generate_stub = options["generate_stub"]
        output_path = options["output"]
        filter_type = options["filter_type"]
        custom_only = options["custom_only"]
        include_readonly = options["include_readonly"]

        # Validate arguments
        if not list_entities and not entity_name:
            self.stderr.write(
                self.style.ERROR(
                    "Please specify --list-entities or --entity <name>",
                ),
            )
            return

        if generate_stub and not entity_name:
            self.stderr.write(
                self.style.ERROR("--generate-stub requires --entity <name>"),
            )
            return

        # Get client
        client = self._get_client()
        if client is None:
            msg = "Could not configure CiviCRM client"
            raise CommandError(msg)

        try:
            if list_entities:
                self._list_entities(client, filter_type, custom_only)

            if entity_name:
                if show_fields:
                    self._show_entity_fields(client, entity_name)

                if show_actions:
                    self._show_entity_actions(client, entity_name)

                if generate_stub:
                    self._generate_entity_stub(
                        client,
                        entity_name,
                        output_path,
                        include_readonly,
                    )

                # If no specific action requested, show basic info
                if not show_fields and not show_actions and not generate_stub:
                    self._show_entity_info(client, entity_name)
        finally:
            client.close()

    def _get_client(self) -> Any:
        """Get a configured CiviCRM client.

        Returns:
            SyncCiviClient instance or None.
        """
        try:
            from django.conf import settings as django_settings

            from civicrm_py.core.client import SyncCiviClient
            from civicrm_py.core.config import CiviSettings

            if hasattr(django_settings, "CIVI_SETTINGS"):
                settings = CiviSettings(**django_settings.CIVI_SETTINGS)
            else:
                settings = CiviSettings.from_env()

            return SyncCiviClient(settings)

        except ValueError as e:
            self.stderr.write(self.style.ERROR(f"Configuration error: {e}"))
            return None
        except ImportError as e:
            self.stderr.write(self.style.ERROR(f"Import error: {e}"))
            return None

    def _list_entities(
        self,
        client: Any,
        filter_type: str | None,
        custom_only: bool,
    ) -> None:
        """List available CiviCRM entities.

        Args:
            client: CiviCRM client.
            filter_type: Filter by entity type.
            custom_only: Only show custom entities.
        """
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("Available CiviCRM Entities"))
        self.stdout.write("=" * 60)
        self.stdout.write("")

        try:
            response = client.request("Entity", "get", {})
            entities = response.values or []

            # Apply filters
            if custom_only:
                entities = [e for e in entities if e.get("name", "").startswith("Custom_")]

            if filter_type:
                entities = [e for e in entities if e.get("type") == filter_type]

            if not entities:
                self.stdout.write(self.style.WARNING("No entities found matching criteria"))
                return

            # Group by type
            by_type: dict[str, list[dict[str, Any]]] = {}
            for entity in entities:
                etype = entity.get("type", "other")
                if etype not in by_type:
                    by_type[etype] = []
                by_type[etype].append(entity)

            # Display
            for etype in sorted(by_type.keys()):
                type_entities = by_type[etype]
                self.stdout.write(
                    self.style.MIGRATE_HEADING(f"{etype.title()} Entities ({len(type_entities)})"),
                )

                for entity in sorted(type_entities, key=lambda x: x.get("name", "")):
                    name = entity.get("name", "unknown")
                    title = entity.get("title") or entity.get("label", "")
                    description = entity.get("description", "")

                    line = f"  {name}"
                    if title and title != name:
                        line += f" - {title}"

                    self.stdout.write(line)

                    if description:
                        # Truncate long descriptions
                        if len(description) > 70:
                            description = description[:67] + "..."
                        self.stdout.write(f"    {description}")

                self.stdout.write("")

            self.stdout.write(self.style.SUCCESS(f"Total: {len(entities)} entities"))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to list entities: {e}"))

    def _show_entity_info(self, client: Any, entity_name: str) -> None:
        """Show basic information about an entity.

        Args:
            client: CiviCRM client.
            entity_name: Entity name.
        """
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO(f"Entity: {entity_name}"))
        self.stdout.write("=" * 60)
        self.stdout.write("")

        try:
            # Get entity metadata
            response = client.request(
                "Entity",
                "get",
                {"where": [["name", "=", entity_name]]},
            )

            if not response.values:
                self.stderr.write(
                    self.style.ERROR(f"Entity '{entity_name}' not found"),
                )
                return

            entity = response.values[0]

            self.stdout.write(f"Name:        {entity.get('name', 'N/A')}")
            self.stdout.write(f"Title:       {entity.get('title') or entity.get('label', 'N/A')}")
            self.stdout.write(f"Type:        {entity.get('type', 'N/A')}")
            self.stdout.write(f"Description: {entity.get('description', 'N/A')}")
            self.stdout.write(f"Searchable:  {entity.get('searchable', True)}")
            self.stdout.write(f"Label Field: {entity.get('label_field', 'N/A')}")

            pk = entity.get("primary_key")
            if pk:
                if isinstance(pk, list):
                    pk = ", ".join(pk)
                self.stdout.write(f"Primary Key: {pk}")

            self.stdout.write("")
            self.stdout.write("Use --show-fields to see field definitions")
            self.stdout.write("Use --show-actions to see available actions")

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to get entity info: {e}"))

    def _show_entity_fields(self, client: Any, entity_name: str) -> None:
        """Show field definitions for an entity.

        Args:
            client: CiviCRM client.
            entity_name: Entity name.
        """
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO(f"Fields for {entity_name}"))
        self.stdout.write("=" * 60)
        self.stdout.write("")

        try:
            response = client.get_fields(entity_name)
            fields = response.values or []

            if not fields:
                self.stdout.write(self.style.WARNING("No fields found"))
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
                self.stdout.write(self.style.MIGRATE_HEADING("Required Fields"))
                for field in sorted(required_fields, key=lambda x: x.get("name", "")):
                    self._print_field(field)
                self.stdout.write("")

            # Display optional fields
            if optional_fields:
                self.stdout.write(self.style.MIGRATE_HEADING("Optional Fields"))
                for field in sorted(optional_fields, key=lambda x: x.get("name", "")):
                    self._print_field(field)
                self.stdout.write("")

            # Display readonly fields
            if readonly_fields:
                self.stdout.write(self.style.MIGRATE_HEADING("Read-only Fields"))
                for field in sorted(readonly_fields, key=lambda x: x.get("name", "")):
                    self._print_field(field)
                self.stdout.write("")

            self.stdout.write(
                self.style.SUCCESS(
                    f"Total: {len(fields)} fields "
                    f"({len(required_fields)} required, "
                    f"{len(optional_fields)} optional, "
                    f"{len(readonly_fields)} readonly)",
                ),
            )

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to get fields: {e}"))

    def _print_field(self, field: dict[str, Any]) -> None:
        """Print a single field definition.

        Args:
            field: Field definition dictionary.
        """
        name = field.get("name", "unknown")
        data_type = field.get("data_type", "unknown")
        title = field.get("title", "")
        description = field.get("description", "")
        fk_entity = field.get("fk_entity")
        default = field.get("default_value")

        line = f"  {name}: {data_type}"

        if fk_entity:
            line += f" -> {fk_entity}"

        if default is not None:
            line += f" = {default!r}"

        self.stdout.write(line)

        if title and title != name:
            self.stdout.write(f"    Title: {title}")

        if description:
            if len(description) > 70:
                description = description[:67] + "..."
            self.stdout.write(f"    {description}")

    def _show_entity_actions(self, client: Any, entity_name: str) -> None:
        """Show available actions for an entity.

        Args:
            client: CiviCRM client.
            entity_name: Entity name.
        """
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO(f"Actions for {entity_name}"))
        self.stdout.write("=" * 60)
        self.stdout.write("")

        try:
            response = client.request(entity_name, "getActions", {})
            actions = response.values or []

            if not actions:
                self.stdout.write(self.style.WARNING("No actions found"))
                return

            for action in sorted(actions, key=lambda x: x.get("name", "")):
                name = action.get("name", "unknown")
                description = action.get("description", "")

                self.stdout.write(f"  {name}")
                if description:
                    if len(description) > 60:
                        description = description[:57] + "..."
                    self.stdout.write(f"    {description}")

            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS(f"Total: {len(actions)} actions"))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to get actions: {e}"))

    def _generate_entity_stub(
        self,
        client: Any,
        entity_name: str,
        output_path: str | None,
        include_readonly: bool,
    ) -> None:
        """Generate Python stub file for an entity.

        Args:
            client: CiviCRM client.
            entity_name: Entity name.
            output_path: Output file path or None for stdout.
            include_readonly: Include readonly fields.
        """
        try:
            response = client.get_fields(entity_name)
            fields = response.values or []

            if not fields:
                self.stderr.write(
                    self.style.ERROR(f"No fields found for {entity_name}"),
                )
                return

            # Generate stub content
            stub = self._build_stub(entity_name, fields, include_readonly)

            if output_path:
                path = Path(output_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(stub)
                self.stdout.write(
                    self.style.SUCCESS(f"Generated stub: {output_path}"),
                )
            else:
                self.stdout.write("")
                self.stdout.write(self.style.HTTP_INFO(f"Stub for {entity_name}"))
                self.stdout.write("=" * 60)
                self.stdout.write(stub)

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to generate stub: {e}"))

    def _build_stub(
        self,
        entity_name: str,
        fields: list[dict[str, Any]],
        include_readonly: bool,
    ) -> str:
        """Build Python stub content for an entity.

        Args:
            entity_name: Entity name.
            fields: Field definitions.
            include_readonly: Include readonly fields.

        Returns:
            Python stub file content.
        """
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
            "Generated by: python manage.py sync_civi --generate-stub",
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
        for field in sorted(fields, key=lambda x: (not x.get("required", False), x.get("name", ""))):
            name = field.get("name", "")

            # Skip internal fields
            if name.startswith("_"):
                continue

            # Skip readonly unless requested
            if field.get("readonly") and not include_readonly:
                continue

            data_type = field.get("data_type", "String")
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
                comment_parts.append(description)
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
