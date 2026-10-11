# Cassette Storage

This directory contains recorded HTTP interactions (cassettes) for testing
civi-py against different CiviCRM API versions without a live instance.

## Directory Structure

```
cassettes/
    v5.63/            # CiviCRM 5.63.x
        entities/     # Entity-specific cassettes
            Contact_get.json
            Contact_create.json
    v5.74/            # CiviCRM 5.74.x
        entities/
            ...
    default/          # Default version (fallback)
        entities/
            ...
```

## Cassette Format

Each cassette is a JSON file containing recorded HTTP interactions:

```json
{
  "name": "Contact_get",
  "version": "5.74",
  "metadata": {
    "recorded_at": "2024-01-20T10:00:00Z",
    "civicrm_version": "5.74"
  },
  "interactions": [
    {
      "request": {
        "method": "POST",
        "url": "https://example.org/civicrm/ajax/api4/Contact/get",
        "headers": {...},
        "body": {...}
      },
      "response": {
        "status_code": 200,
        "headers": {...},
        "body": {...}
      },
      "recorded_at": "2024-01-20T10:00:00Z"
    }
  ]
}
```

## Usage

### Recording New Cassettes

```bash
# Record against a live CiviCRM instance
CIVI_CASSETTE_MODE=record \
CIVI_VERSION=5.74 \
CIVI_BASE_URL=https://your-instance.org/civicrm/ajax/api4 \
CIVI_API_KEY=your-key \
pytest tests/compat/ -k test_name
```

### Replaying Cassettes

```bash
# Replay-only mode (default in CI)
CIVI_CASSETTE_MODE=replay pytest tests/compat/

# Auto mode: replay if exists, record if missing
CIVI_CASSETTE_MODE=auto pytest tests/compat/
```

### Test Markers

```python
# Use a specific cassette
@pytest.mark.cassette("Contact_get")
def test_contact_get(cassette_client):
    ...

# Force recording
@pytest.mark.record
def test_record_new(cassette_client):
    ...

# Force replay (fails if cassette missing)
@pytest.mark.replay
def test_replay_only(cassette_client):
    ...
```

## CI Configuration

In CI environments, cassette mode defaults to `replay` to ensure:
- No network requests are made
- Tests are deterministic and fast
- Missing cassettes cause test failures

Set `CI=true` or `CIVI_CASSETTE_MODE=replay` in your CI config.

## Adding New Cassettes

1. Record against a live instance:
   ```bash
   CIVI_CASSETTE_MODE=record CIVI_VERSION=5.74 pytest tests/compat/ -k new_test
   ```

2. Review the recorded cassette for sensitive data
3. Commit the cassette file to version control

## Sensitive Data

Cassettes automatically redact sensitive headers:
- `Authorization`
- `X-Civi-Api-Key`
- `X-Civi-Site-Key` / `X-Civi-Key`
- `Cookie` / `Set-Cookie`

Review cassettes before committing to ensure no other sensitive data is present.
