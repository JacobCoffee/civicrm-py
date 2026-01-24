# Schema Snapshots for Drift Detection

This directory contains versioned schema snapshots used by the API drift detection system.

## Purpose

Schema snapshots allow detection of changes between CiviCRM API versions. When the API schema changes, the drift detector compares current fields against these stored snapshots to identify:

- **Added fields**: New fields in the API not present in the snapshot
- **Removed fields**: Fields in the snapshot that no longer exist (BREAKING)
- **Type changes**: Field data types that have changed (BREAKING)
- **Required changes**: Fields that became required (BREAKING if newly required)
- **Default changes**: Default value modifications
- **FK changes**: Foreign key entity references that changed

## Snapshot Format

Each snapshot file follows the same format as the main schema cache:

```json
{
  "entity_name": "Contact",
  "fields": [...],
  "cached_at": "2025-01-22T00:00:00",
  "metadata": {
    "civicrm_version": "5.74",
    "source": "snapshot"
  }
}
```

## Updating Snapshots

### Manual Update

```python
from tests.compat.drift_detector import DriftDetector, SchemaSnapshot
from tests.compat.schema_validator import SchemaCache

# Load current fields from cache or API
cache = SchemaCache()
fields = cache.load_schema("Contact")

# Create and save snapshot
snapshot = SchemaSnapshot.from_api_fields(
    entity_name="Contact",
    fields=fields,
    version="5.74",
)
snapshot.save()
```

### Programmatic Update from API

```python
from tests.compat.drift_detector import DriftDetector
from tests.compat.schema_validator import SchemaCache
from civicrm_py import CiviClient

async def update_all_snapshots():
    cache = SchemaCache()
    detector = DriftDetector(cache)

    async with CiviClient() as client:
        # Check for drift first
        report = await detector.check_all_from_api(client)

        if report.has_changes:
            # Generate changelog
            changelog = detector.generate_changelog(report)
            print(changelog)

            # Update snapshots with new fields
            entities = {}
            for entity_name in cache.list_cached_entities():
                response = await client.get_fields(entity_name)
                entities[entity_name] = response.values

            detector.update_snapshots(entities, version="5.75")
```

## Drift Detection in Tests

Use pytest markers to automatically detect drift:

```python
import pytest

@pytest.mark.detect_drift
async def test_contact_schema():
    """This test will report any schema drift."""
    pass

@pytest.mark.detect_drift_strict
async def test_contact_schema_strict():
    """This test will FAIL on any schema change."""
    pass

@pytest.mark.detect_drift_breaking
async def test_contact_schema_breaking():
    """This test will FAIL only on breaking changes."""
    pass
```

## Detection Modes

| Mode | Fails On | Use Case |
|------|----------|----------|
| `REPORT` | Never | Informational, logs changes |
| `STRICT` | Any change | Maximum compatibility guarantee |
| `BREAKING` | Breaking changes only | Semantic versioning compliance |

## Breaking Changes

The following changes are considered breaking:

1. **Field Removal**: Existing code may reference the field
2. **Type Change**: Type coercion may fail at runtime
3. **Required Status**: If a field becomes required, existing records may fail validation
4. **FK Entity Change**: Joins and references may break

## Files

Snapshot files are named `{EntityName}.json` or `{EntityName}_{version}.json` for versioned snapshots.

## Workflow

1. **Before Release**: Run drift detection against new CiviCRM version
2. **Review Changes**: Check changelog for breaking changes
3. **Update Models**: Modify Python entity classes as needed
4. **Update Snapshots**: Save new snapshots after model updates
5. **Version Tag**: Associate snapshots with CiviCRM version
