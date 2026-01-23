# CiviCRM API Schema Cache

This directory contains cached JSON schema files from CiviCRM API v4 `getFields()` responses.

## Purpose

These schema files are used to validate that our Python entity models match the CiviCRM API field definitions. This helps catch:

- Missing fields in our models
- Type mismatches between API and Python types
- Required field discrepancies
- Field naming inconsistencies

## Schema Format

Each JSON file follows this structure:

```json
{
  "entity_name": "Contact",
  "fields": [
    {
      "name": "id",
      "title": "Contact ID",
      "description": "Unique Contact ID",
      "data_type": "Integer",
      "input_type": "Number",
      "required": false,
      "readonly": true,
      "serialize": null,
      "fk_entity": null,
      "options": null,
      "default_value": null
    }
  ],
  "cached_at": "2025-01-22T00:00:00",
  "metadata": {
    "source": "civicrm_api4_getfields",
    "civicrm_version": "5.74"
  }
}
```

## Updating Schemas

To refresh schemas from a live CiviCRM instance:

```python
from tests.compat.schema_validator import SchemaCache
from civi_py import CiviClient

async def refresh_schemas():
    cache = SchemaCache()
    async with CiviClient() as client:
        await cache.refresh_from_api(client)
```

Or for specific entities:

```python
await cache.refresh_from_api(client, entity_names=["Contact", "Activity"])
```

## CiviCRM Data Types

Common CiviCRM data types and their Python equivalents:

| CiviCRM Type | Python Type(s) | Notes |
|--------------|----------------|-------|
| String | `str` | Basic text |
| Text | `str` | Longer text |
| Memo | `str` | Rich text (HTML) |
| Integer | `int` | Whole numbers |
| Boolean | `bool` | True/False |
| Float | `float` | Decimal numbers |
| Money | `float`, `str` | Currency amounts |
| Date | `str` | ISO date format |
| Datetime | `str` | ISO datetime format |
| Timestamp | `int`, `str` | Unix timestamp |
| Array | `list` | Lists of values |
| Object | `dict` | JSON objects |
| Json | `dict`, `str` | JSON data |
| Blob | `bytes`, `str` | Binary data |

## Files

- `Contact.json` - Contact entity fields
- `Activity.json` - Activity entity fields
- Additional entities as needed

## Notes

- Schemas are versioned by CiviCRM version in metadata
- Files starting with `_` are ignored by the validator
- Run tests with `pytest tests/compat/` to validate schemas
