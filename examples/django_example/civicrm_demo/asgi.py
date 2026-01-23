"""ASGI config for CiviCRM demo project.

Django 5+ ASGI support enables:
- Native async views (async def view(request))
- Async ORM operations (await Model.objects.aget())
- Async middleware
- Full compatibility with civi-py's async CiviClient

Run with:
    uvicorn civicrm_demo.asgi:application --reload --port 8000
    # or
    granian --interface asgi civicrm_demo.asgi:application
"""

from __future__ import annotations

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "civicrm_demo.settings")

application = get_asgi_application()
