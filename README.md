# civi-py

[![CI](https://github.com/JacobCoffee/civi-py/actions/workflows/ci.yml/badge.svg)](https://github.com/JacobCoffee/civi-py/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/civi-py.svg)](https://badge.fury.io/py/civi-py)
[![Python Version](https://img.shields.io/pypi/pyversions/civi-py.svg)](https://pypi.org/project/civi-py/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Documentation](https://img.shields.io/badge/docs-available-brightgreen.svg)](https://civi-py.readthedocs.io)

Modern Python client for CiviCRM API v4.

## Features

- **Async-First**: Built on httpx for modern async/await support
- **Type-Safe**: Full type hints with Pydantic models
- **Django-ORM-like Queries**: Familiar chainable query interface
- **Framework Integrations**: Django, Litestar, and FastAPI support
- **Comprehensive Testing**: High test coverage with pytest

## Installation

```bash
pip install civi-py
```

With framework integrations:

```bash
pip install civi-py[django]    # Django integration
pip install civi-py[litestar]  # Litestar integration
pip install civi-py[fastapi]   # FastAPI integration
```

## Quick Start

### Configuration

Set environment variables:

```bash
export CIVI_BASE_URL=https://your-site.org/civicrm/ajax/api4
export CIVI_API_KEY=your-api-key
export CIVI_SITE_KEY=your-site-key
```

### Basic Usage

```python
import asyncio
from civi import CiviClient

async def main():
    async with CiviClient() as client:
        # List contacts
        contacts = await client.Contact.filter(is_deleted=False).all()

        # Get specific contact
        contact = await client.Contact.get(id=123)

        # Create contact
        new_contact = await client.Contact.create(
            first_name="John",
            last_name="Doe",
            contact_type="Individual",
        )

        # Update contact
        await client.Contact.update(id=123, first_name="Jane")

        # Delete contact
        await client.Contact.delete(id=123)

asyncio.run(main())
```

### Query Building

```python
# Chain filters
contacts = await (
    client.Contact
    .select("id", "display_name", "email_primary.email")
    .filter(is_deleted=False, contact_type="Individual")
    .order_by("-created_date")
    .limit(25)
    .all()
)

# Custom operators
contacts = await (
    client.Contact
    .filter_by("created_date", ">=", "2024-01-01")
    .filter_by("display_name", "LIKE", "%Smith%")
    .all()
)

# Pagination
page1 = await client.Contact.limit(25).offset(0).all()
page2 = await client.Contact.limit(25).offset(25).all()

# Aggregates
total = await client.Contact.filter(is_deleted=False).count()
exists = await client.Contact.filter(id=123).exists()
```

### Framework Integration

#### Litestar

```python
from litestar import Litestar, get
from civi import CiviClient
from civi.contrib.litestar import CiviPlugin

@get("/contacts")
async def get_contacts(civi: CiviClient) -> list[dict]:
    return await civi.Contact.filter(is_deleted=False).all()

app = Litestar(
    route_handlers=[get_contacts],
    plugins=[CiviPlugin()],
)
```

#### Django

```python
# settings.py
CIVI_SETTINGS = {
    "BASE_URL": "https://example.org/civicrm/ajax/api4",
    "API_KEY": env("CIVI_API_KEY"),
    "SITE_KEY": env("CIVI_SITE_KEY"),
}

# views.py
from civi.contrib.django import get_civi_client

async def contact_list(request):
    async with get_civi_client() as client:
        contacts = await client.Contact.all()
        return JsonResponse({"contacts": contacts})
```

## Development

```bash
# Clone repository
git clone https://github.com/JacobCoffee/civi-py.git
cd civi-py

# Install dependencies
make install

# Run tests
make test

# Run linting
make check
```

## Documentation

Full documentation available at [civi-py.readthedocs.io](https://civi-py.readthedocs.io).

## License

MIT License - see [LICENSE](LICENSE) for details.
