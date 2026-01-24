.. _compatibility-testing:

=========================
API Compatibility Testing
=========================

civicrm-py includes a comprehensive compatibility testing infrastructure to ensure the library
works correctly across CiviCRM versions and detects API changes before they cause problems
in production.

This guide covers:

- Overview of the testing strategy
- Adding new entity tests
- Recording and replaying cassettes
- Troubleshooting compatibility failures
- Version support policy

Overview
========

The compatibility testing system validates civicrm-py against CiviCRM API v4 through
several mechanisms:

**Schema Validation**
    Compares Pydantic entity models against actual CiviCRM field definitions
    fetched via ``getFields()``. Detects missing fields, type mismatches, and
    required field discrepancies.

**Coverage Validation**
    Tracks which CiviCRM entities and actions the library implements. Generates
    reports showing coverage percentages and prioritized TODO lists for missing
    implementations.

**Drift Detection**
    Compares current API schemas against stored snapshots to detect when CiviCRM
    changes its API. Categorizes changes as breaking or non-breaking and generates
    changelogs.

**Cassette Recording**
    Records HTTP interactions with a live CiviCRM instance and replays them during
    testing. Enables offline testing without requiring a CiviCRM server.

**Contract Testing**
    Validates that QuerySet operations produce the correct API v4 JSON format and
    that response parsing handles all expected formats.

Directory Structure
-------------------

.. code-block:: text

    tests/compat/
    |-- __init__.py              # Module docstring and exports
    |-- conftest.py              # Pytest fixtures for compatibility tests
    |-- cassettes.py             # VCR style HTTP recording/replay
    |-- schema_validator.py      # Entity model vs API schema validation
    |-- coverage_validator.py    # Entity and action coverage tracking
    |-- drift_detector.py        # API schema drift detection
    |-- action_mapping.py        # CiviCRM action to EntityManager mapping
    |-- field_coverage.py        # Per field coverage analysis
    |-- report_generator.py      # HTML/Markdown coverage reports
    |-- contracts/
    |   |-- __init__.py
    |   `-- fixtures.py          # Request/response contract definitions
    |-- schemas/                  # Cached API schemas from getFields()
    |   |-- Contact.json
    |   |-- Activity.json
    |   `-- snapshots/           # Versioned snapshots for drift detection
    `-- test_*.py                # Test modules


Adding New Entity Tests
=======================

When adding support for a new CiviCRM entity, follow these steps to ensure full
test coverage.

Step 1: Create the Entity Model
-------------------------------

First, create the entity model in ``src/civi/entities/``:

.. code-block:: python

    # src/civi/entities/relationship.py
    from __future__ import annotations

    from typing import TYPE_CHECKING

    import msgspec

    from civicrm_py.entities.base import BaseEntity

    if TYPE_CHECKING:
        from datetime import date

    class Relationship(BaseEntity):
        """CiviCRM Relationship entity.

        Represents a relationship between two contacts.
        """

        __entity_name__ = "Relationship"

        id: int | None = None
        contact_id_a: int | None = None
        contact_id_b: int | None = None
        relationship_type_id: int | None = None
        start_date: str | None = None
        end_date: str | None = None
        is_active: bool | None = None
        description: str | None = None

Export the entity from ``src/civi/entities/__init__.py``.

Step 2: Cache the API Schema
----------------------------

Fetch and cache the entity schema from a live CiviCRM instance:

.. code-block:: python

    import asyncio
    from civicrm_py import CiviClient
    from tests.compat.schema_validator import SchemaCache

    async def cache_relationship_schema():
        cache = SchemaCache()

        async with CiviClient() as client:
            await cache.refresh_from_api(client, ["Relationship"])

    asyncio.run(cache_relationship_schema())

Alternatively, manually create ``tests/compat/schemas/Relationship.json`` by copying
the output of ``Relationship.getFields()`` from the CiviCRM API Explorer.

Step 3: Add Schema Validation Tests
-----------------------------------

Create a test file in ``tests/compat/``:

.. code-block:: python

    # tests/compat/test_relationship_schema.py
    from __future__ import annotations

    import pytest

    from civicrm_py.entities import Relationship
    from tests.compat.schema_validator import SchemaValidator


    class TestRelationshipSchema:
        """Schema validation tests for Relationship entity."""

        @pytest.fixture
        def validator(self, production_schema_cache):
            """Create schema validator with production cache."""
            return SchemaValidator(cache=production_schema_cache)

        def test_schema_compatibility(self, validator):
            """Relationship model matches API schema."""
            result = validator.validate_entity_from_cache(Relationship)

            assert result is not None, "No cached schema for Relationship"
            assert result.is_valid, f"Schema errors: {result.errors}"

        def test_no_type_mismatches(self, validator):
            """All field types are compatible."""
            result = validator.validate_entity_from_cache(Relationship)

            type_errors = [
                e for e in result.errors
                if e.mismatch_type.value == "type_mismatch"
            ]
            assert len(type_errors) == 0, f"Type mismatches: {type_errors}"

        def test_required_fields_covered(self, validator):
            """Required API fields have non-optional types."""
            result = validator.validate_entity_from_cache(Relationship)

            required_warnings = [
                w for w in result.warnings
                if w.mismatch_type.value == "required_mismatch"
            ]
            # Document any required field gaps
            for warning in required_warnings:
                print(f"Required field gap: {warning.field_name}")

Step 4: Add to Coverage Validator
---------------------------------

Register the entity in ``tests/compat/coverage_validator.py`` by adding it to
``EntityCoverageValidator.IMPLEMENTED_ENTITIES``:

.. code-block:: python

    IMPLEMENTED_ENTITIES: ClassVar[dict[str, type[Any]]] = {
        # ... existing entities ...
        "Relationship": Relationship,
    }

Step 5: Add Contract Tests
--------------------------

Add contract tests to verify QuerySet operations produce correct API requests:

.. code-block:: python

    # tests/compat/test_relationship_contracts.py
    from __future__ import annotations

    import pytest

    from civicrm_py.entities import Relationship


    class TestRelationshipContracts:
        """Contract tests for Relationship queries."""

        def test_filter_by_contact(self):
            """Filter produces correct where clause."""
            qs = Relationship.objects.filter(contact_id_a=123)
            params = qs._build_params()

            assert params["where"] == [["contact_id_a", "=", 123]]

        def test_select_fields(self):
            """Select produces correct select clause."""
            qs = Relationship.objects.select("id", "contact_id_a", "relationship_type_id")
            params = qs._build_params()

            assert params["select"] == ["id", "contact_id_a", "relationship_type_id"]

        def test_active_relationships(self):
            """Common pattern for active relationships."""
            qs = (
                Relationship.objects
                .filter(is_active=True)
                .filter(contact_id_a=123)
                .select("id", "contact_id_b", "relationship_type_id")
            )
            params = qs._build_params()

            assert ["is_active", "=", True] in params["where"]
            assert ["contact_id_a", "=", 123] in params["where"]

Step 6: Create a Snapshot for Drift Detection
---------------------------------------------

Store a baseline schema snapshot for future drift detection:

.. code-block:: python

    from tests.compat.drift_detector import SchemaSnapshot

    # After caching the schema
    snapshot = SchemaSnapshot.from_api_fields(
        entity_name="Relationship",
        fields=cached_fields,
        version="5.74",
        civicrm_version="5.74",
    )
    snapshot.save()  # Saves to tests/compat/schemas/snapshots/


Cassette Recording
==================

Cassettes record HTTP interactions with CiviCRM so tests can run without a live
server. This is essential for CI pipelines and offline development.

What Are Cassettes?
-------------------

A cassette is a JSON file containing HTTP request/response pairs. When a test runs
in replay mode, the cassette system intercepts HTTP calls and returns the recorded
response instead of making a real network request.

.. code-block:: json

    {
      "name": "Contact_get_by_id",
      "version": "5.74",
      "interactions": [
        {
          "request": {
            "method": "POST",
            "url": "https://example.org/civicrm/ajax/api4/Contact/get",
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
            "body": {"params": "{\"where\": [[\"id\", \"=\", 1]]}"}
          },
          "response": {
            "status_code": 200,
            "headers": {"Content-Type": "application/json"},
            "body": {
              "values": [{"id": 1, "display_name": "Test Contact"}],
              "count": 1,
              "countFetched": 1
            }
          },
          "recorded_at": "2025-01-22T12:00:00Z"
        }
      ]
    }

Recording New Cassettes
-----------------------

To record new cassettes, set the environment variables and run tests against a
live CiviCRM instance:

.. code-block:: bash

    # Required: Point to your CiviCRM instance
    export CIVI_BASE_URL=https://your-site.org/civicrm/ajax/api4
    export CIVI_API_KEY=your-api-key
    export CIVI_SITE_KEY=your-site-key

    # Set recording mode
    export CIVI_CASSETTE_MODE=record
    export CIVI_VERSION=5.74

    # Run the tests you want to record
    pytest tests/compat/test_contact_schema.py -v

Recorded cassettes are saved to ``tests/cassettes/v{version}/entities/``.

Using Cassettes in Tests
------------------------

Mark tests to use cassettes with the ``@pytest.mark.cassette`` decorator:

.. code-block:: python

    import pytest

    @pytest.mark.cassette("Contact_get_all")
    async def test_get_all_contacts(cassette_client):
        """Test fetching all contacts using recorded cassette."""
        response = await cassette_client.get("Contact", limit=10)

        assert response.count >= 0
        assert len(response.values) <= 10

Or use the context manager for more control:

.. code-block:: python

    async def test_custom_cassette(use_cassette, civi_client):
        """Test with explicit cassette context."""
        with use_cassette("Contact_complex_query"):
            response = await civi_client.get(
                "Contact",
                where=[["is_deleted", "=", False]],
                select=["id", "display_name"],
            )
            assert response.values is not None

Updating Existing Cassettes
---------------------------

When the API changes or you need fresh recordings:

1. Delete the existing cassette file
2. Set ``CIVI_CASSETTE_MODE=record``
3. Run the test
4. Verify the new cassette looks correct
5. Commit the updated cassette

.. code-block:: bash

    # Remove old cassette
    rm tests/cassettes/v5.74/entities/Contact_get_all.json

    # Record fresh cassette
    CIVI_CASSETTE_MODE=record pytest tests/compat/test_contact.py::test_get_all -v

    # Verify and commit
    git diff tests/cassettes/
    git add tests/cassettes/
    git commit -m "test: update Contact_get_all cassette for 5.74"

CI Replay Mode
--------------

In CI environments, cassettes automatically run in replay mode. The ``CI``
environment variable triggers this behavior:

.. code-block:: yaml

    # .github/workflows/test.yml
    env:
      CI: true  # Automatically detected by GitHub Actions

    steps:
      - name: Run compatibility tests
        run: pytest tests/compat/ -v

If a cassette is missing in CI, the test fails with ``FileNotFoundError`` rather
than attempting a live request. This ensures tests are deterministic and do not
depend on external services.

Cassette Modes Reference
------------------------

.. list-table::
   :header-rows: 1
   :widths: 15 85

   * - Mode
     - Behavior
   * - ``record``
     - Always record, overwrite existing cassettes
   * - ``replay``
     - Always replay, fail if cassette missing
   * - ``auto``
     - Replay if exists, record if missing (default for local dev)
   * - ``none``
     - Disable cassettes, always make live requests


Troubleshooting Compatibility Failures
======================================

Common failure patterns and how to resolve them.

Schema Validation Errors
------------------------

**TYPE_MISMATCH: API expects Integer, model has str**

The entity model field type does not match the CiviCRM field type. Fix by
updating the model:

.. code-block:: python

    # Before
    contact_id: str | None = None

    # After
    contact_id: int | None = None

Use the ``TypeMapping`` class to check valid Python types for CiviCRM types:

.. code-block:: python

    from tests.compat.schema_validator import TypeMapping

    # What Python types work for CiviCRM Integer?
    TypeMapping.get_expected_python_types("Integer")
    # Returns: (int,)

    # What Python types work for CiviCRM Timestamp?
    TypeMapping.get_expected_python_types("Timestamp")
    # Returns: (int, str)

**MISSING_FIELD: API field 'foo' not defined in model**

The CiviCRM API has a field that your model does not define. Either add the field
or document why it is intentionally omitted:

.. code-block:: python

    class Contact(BaseEntity):
        # Add the missing field
        new_api_field: str | None = None

        # Or document why omitted (in SchemaValidator.IGNORED_API_FIELDS)

**REQUIRED_MISMATCH: API marks 'foo' as required, but model allows None**

The API requires this field, but your model allows ``None``. Consider making it
required or documenting the discrepancy:

.. code-block:: python

    # If truly required for create operations
    contact_type: str  # No None default

    # If only required sometimes, keep Optional but document
    contact_type: str | None = None  # Required by API for create

Drift Detection Alerts
----------------------

**Breaking change detected: field removed**

A field that existed in the stored snapshot no longer exists in the current API.
This breaks any code using that field.

1. Check if the field was renamed (look for a similar new field)
2. Update your entity model to remove the field
3. Update the snapshot with the new schema
4. Add deprecation warnings if needed

.. code-block:: python

    # Update snapshot after verifying the change
    from tests.compat.drift_detector import DriftDetector, SchemaSnapshot

    detector = DriftDetector(cache)
    detector.update_snapshots({"Contact": new_fields}, version="5.75")

**Breaking change detected: type changed**

A field changed its data type. This may break serialization or validation.

1. Review the CiviCRM release notes for context
2. Update your model type annotation
3. Add migration notes to your changelog

**Non-breaking change: field added**

New fields do not break existing code but indicate new API capabilities.
Consider adding them to your model if useful.

Cassette Replay Failures
------------------------

**FileNotFoundError: Cassette not found**

The test expects a cassette that does not exist. Either:

1. Record the cassette: ``CIVI_CASSETTE_MODE=record pytest ...``
2. Remove the ``@pytest.mark.cassette`` marker if live testing is acceptable

**Response mismatch: recorded vs actual**

If running in ``auto`` mode and getting unexpected results, the cassette may be
stale. Re-record it:

.. code-block:: bash

    rm tests/cassettes/v5.74/entities/MyTest.json
    CIVI_CASSETTE_MODE=record pytest tests/compat/test_mytest.py -v

Debugging Schema Issues
-----------------------

Use the schema validator interactively to diagnose issues:

.. code-block:: python

    from civicrm_py.entities import Contact
    from tests.compat.schema_validator import SchemaCache, SchemaValidator

    cache = SchemaCache()
    validator = SchemaValidator(cache, strict=False, ignore_extra_api_fields=False)

    result = validator.validate_entity_from_cache(Contact)

    print(f"Valid: {result.is_valid}")
    print(f"Errors: {len(result.errors)}")
    print(f"Warnings: {len(result.warnings)}")

    for error in result.errors:
        print(f"  {error.field_name}: {error.message}")

    for warning in result.warnings:
        print(f"  {warning.field_name}: {warning.message}")

Generating Coverage Reports
---------------------------

Generate HTML coverage reports to see overall compatibility status:

.. code-block:: bash

    python -m tests.compat.report_generator -o ./coverage_reports

This creates:

- ``coverage_report.json``: Machine readable full report
- ``entity_coverage.txt``: Console friendly entity coverage summary
- ``action_coverage_detailed.txt``: Per entity action coverage
- Individual entity reports in subdirectories


Version Support Policy
======================

Supported CiviCRM Versions
--------------------------

civicrm-py supports the following CiviCRM versions:

- **Current stable release**: Full support with complete test coverage
- **Previous stable release**: Full support
- **ESR (Extended Security Release)**: Best effort support

Check CiviCRM versions at https://civicrm.org/download for current releases.

As of January 2026, this means:

+----------+--------------------+------------------+
| Version  | Status             | Support Level    |
+==========+====================+==================+
| 6.x      | Current            | Full             |
+----------+--------------------+------------------+
| 5.75+    | Previous           | Full             |
+----------+--------------------+------------------+
| 5.57 ESR | Extended Security  | Best Effort      |
+----------+--------------------+------------------+
| < 5.57   | End of Life        | Not Supported    |
+----------+--------------------+------------------+

How Version Compatibility Is Tested
-----------------------------------

**Cassette Based Testing**

Each supported version has its own cassette directory:

.. code-block:: text

    tests/cassettes/
    |-- v5.74/
    |   `-- entities/
    |-- v5.73/
    |   `-- entities/
    `-- v5.57-esr/
        `-- entities/

Run tests against a specific version:

.. code-block:: bash

    CIVI_VERSION=5.73 pytest tests/compat/ -v

**Schema Snapshots**

Version specific schema snapshots enable drift detection across versions:

.. code-block:: text

    tests/compat/schemas/snapshots/
    |-- Contact_5.73.json
    |-- Contact_5.74.json
    `-- Activity_5.74.json

**CI Matrix Testing**

The CI pipeline tests against multiple CiviCRM versions in parallel:

.. code-block:: yaml

    strategy:
      matrix:
        civicrm-version: ["5.74", "5.73", "5.57-esr"]

    steps:
      - name: Run compatibility tests
        env:
          CIVI_VERSION: ${{ matrix.civicrm-version }}
        run: pytest tests/compat/ -v

Deprecation Policy
------------------

When CiviCRM deprecates or removes API features:

1. **Detection**: Drift detection identifies the change
2. **Documentation**: Add deprecation warnings to affected code
3. **Transition Period**: Support both old and new behavior for one release cycle
4. **Removal**: Remove deprecated code when the old version is no longer supported

Example deprecation handling:

.. code-block:: python

    import warnings

    class Contact(BaseEntity):
        @property
        def email(self) -> str | None:
            warnings.warn(
                "Contact.email is deprecated in CiviCRM 5.75. "
                "Use Contact.email_primary.email instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            return getattr(self, "_email", None)

Handling API Changes
--------------------

When a new CiviCRM version introduces API changes:

1. Run drift detection against the new version
2. Review the changelog for breaking changes
3. Update entity models as needed
4. Record new cassettes for the version
5. Update schema snapshots
6. Add version specific tests if behavior differs

.. code-block:: bash

    # Step 1: Detect drift
    CIVI_VERSION=5.75 python -c "
    from tests.compat.drift_detector import DriftDetector
    from tests.compat.schema_validator import SchemaCache

    cache = SchemaCache()
    detector = DriftDetector(cache)
    report = detector.check_all_cached()

    if report.has_changes:
        print(report.format_changelog())
    "

    # Step 2: Update schemas if changes are expected
    # Step 3: Record new cassettes
    CIVI_VERSION=5.75 CIVI_CASSETTE_MODE=record pytest tests/compat/ -v

    # Step 4: Update snapshots
    # Step 5: Commit changes with version note


See Also
========

- :doc:`/api/index` for API reference
- :doc:`/concepts/entities` for entity model documentation
- `CiviCRM API v4 Documentation <https://docs.civicrm.org/dev/en/latest/api/v4/>`_
- `pytest-recording <https://github.com/kiwicom/pytest-recording>`_ for VCR concepts
