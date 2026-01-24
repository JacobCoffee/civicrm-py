# civicrm-py

[![CI](https://github.com/JacobCoffee/civicrm-py/actions/workflows/ci.yml/badge.svg)](https://github.com/JacobCoffee/civicrm-py/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/civicrm-py.svg)](https://badge.fury.io/py/civicrm-py)
[![Python Version](https://img.shields.io/pypi/pyversions/civicrm-py.svg)](https://pypi.org/project/civicrm-py/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python client for CiviCRM's API v4. Async by default, with a query interface that'll feel familiar if you've used Django's ORM.

## What it does

- Async HTTP via httpx (sync wrappers available)
- Type-safe models using msgspec
- Chainable queries: `client.Contact.filter(is_deleted=False).limit(10).all()`
- Integrations for Django, Litestar, FastAPI, Flask, and others

## Install

```bash
pip install civicrm-py
```

With a framework:

```bash
pip install civicrm-py[django]
pip install civicrm-py[litestar]
pip install civicrm-py[fastapi]
```

Optional extras:

```bash
pip install civicrm-py[sqlspec]    # Local database caching
pip install civicrm-py[workflows]  # Workflow automation
```

See docs for [sqlspec](https://civi.scriptr.dev/guides/sqlspec.html), [workflows](https://civi.scriptr.dev/guides/workflows.html), and [pytest-databases](https://civi.scriptr.dev/guides/pytest-databases.html).

## Setup

```bash
export CIVI_BASE_URL=https://your-site.org/civicrm/ajax/api4
export CIVI_API_KEY=your-api-key
export CIVI_SITE_KEY=your-site-key
```

## Usage

```python
import asyncio
from civicrm_py import CiviClient

async def main():
    async with CiviClient() as client:
        # Get all active contacts
        contacts = await client.Contact.filter(is_deleted=False).all()

        # Single contact by ID
        contact = await client.Contact.get(id=123)

        # Create
        new_contact = await client.Contact.create(
            first_name="John",
            last_name="Doe",
            contact_type="Individual",
        )

        # Update
        await client.Contact.update(id=123, first_name="Jane")

        # Delete
        await client.Contact.delete(id=123)

asyncio.run(main())
```

### Queries

```python
# Select specific fields, filter, sort, paginate
contacts = await (
    client.Contact
    .select("id", "display_name", "email_primary.email")
    .filter(is_deleted=False, contact_type="Individual")
    .order_by("-created_date")
    .limit(25)
    .all()
)

# Operators
contacts = await (
    client.Contact
    .filter_by("created_date", ">=", "2024-01-01")
    .filter_by("display_name", "LIKE", "%Smith%")
    .all()
)

# Count and exists
total = await client.Contact.filter(is_deleted=False).count()
exists = await client.Contact.filter(id=123).exists()
```

### Litestar

```python
from litestar import Litestar, get
from civicrm_py import CiviClient
from civicrm_py.contrib.litestar import CiviPlugin

@get("/contacts")
async def get_contacts(civi: CiviClient) -> list[dict]:
    return await civi.Contact.filter(is_deleted=False).all()

app = Litestar(
    route_handlers=[get_contacts],
    plugins=[CiviPlugin()],
)
```

### Django

```python
# settings.py
CIVI_SETTINGS = {
    "BASE_URL": "https://example.org/civicrm/ajax/api4",
    "API_KEY": env("CIVI_API_KEY"),
    "SITE_KEY": env("CIVI_SITE_KEY"),
}

# views.py
from civicrm_py.contrib.django import get_civi_client

async def contact_list(request):
    async with get_civi_client() as client:
        contacts = await client.Contact.all()
        return JsonResponse({"contacts": contacts})
```

## Development

```bash
git clone https://github.com/JacobCoffee/civicrm-py.git
cd civicrm-py

make install  # dependencies
make test     # tests
make check    # lint + typecheck
```

## Docs

[civi.scriptr.dev](https://civi.scriptr.dev)

## Alternatives

- [civipy](https://github.com/indepndnt/civipy) - Another Python client for CiviCRM. No built-in web framework integrations.

## License

MIT
