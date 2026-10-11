Django Integration
==================

Full integration with Django including middleware, template tags, management commands, and admin interface.

Installation
------------

Install with the Django extra:

.. code-block:: bash

   pip install civicrm-py[django]


Settings Configuration
----------------------

Add your CiviCRM credentials to Django settings:

.. code-block:: python

   # settings.py

   CIVICRM_URL = "https://example.org/civicrm/ajax/api4"
   CIVICRM_API_KEY = "your-api-key"

   # Optional settings
   CIVICRM_SITE_KEY = "your-site-key"          # For some auth modes
   CIVICRM_AUTH_TYPE = "api_key"               # api_key, jwt, or basic
   CIVICRM_AUTH_FLOW = "header"                # header (Authorization) or xheader (X-Civi-Auth)
   CIVICRM_TIMEOUT = 30                        # Request timeout in seconds
   CIVICRM_VERIFY_SSL = True                   # SSL certificate verification
   CIVICRM_DEBUG = False                       # Enable debug logging
   CIVICRM_MAX_RETRIES = 3                     # Maximum retry attempts

For JWT authentication:

.. code-block:: python

   CIVICRM_AUTH_TYPE = "jwt"
   CIVICRM_JWT_TOKEN = "your-jwt-token"

For basic authentication:

.. code-block:: python

   CIVICRM_AUTH_TYPE = "basic"
   CIVICRM_USERNAME = "admin"
   CIVICRM_PASSWORD = "secret"


Adding to INSTALLED_APPS
------------------------

Add the Django app to enable template tags and management commands:

.. code-block:: python

   INSTALLED_APPS = [
       # ...
       "civicrm_py.contrib.django",
   ]


Middleware Setup
----------------

Add the middleware to attach a CiviCRM client to each request:

.. code-block:: python

   MIDDLEWARE = [
       "django.middleware.security.SecurityMiddleware",
       "django.contrib.sessions.middleware.SessionMiddleware",
       # ...
       "civicrm_py.contrib.django.middleware.CiviMiddleware",
   ]

The middleware automatically detects sync vs async mode:

* WSGI deployments get ``SyncCiviClient`` via thread-local storage
* ASGI deployments get async ``CiviClient`` shared across coroutines

Once configured, access the client via ``request.civi_client`` in any view.


Using in Views
--------------

Sync Views
^^^^^^^^^^

.. code-block:: python

   from django.http import JsonResponse


   def contact_list(request):
       client = request.civi_client
       response = client.get("Contact", limit=10)
       return JsonResponse({"contacts": response.values})


   def contact_detail(request, contact_id):
       client = request.civi_client
       response = client.get(
           "Contact",
           where=[["id", "=", contact_id]],
           limit=1,
       )
       if not response.values:
           return JsonResponse({"error": "Not found"}, status=404)
       return JsonResponse({"contact": response.values[0]})


   def contact_create(request):
       if request.method != "POST":
           return JsonResponse({"error": "POST required"}, status=405)

       import json
       data = json.loads(request.body)

       client = request.civi_client
       response = client.create("Contact", data)
       return JsonResponse({"contact": response.values[0]}, status=201)

Async Views (Django 4.1+)
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from django.http import JsonResponse


   async def contact_list(request):
       client = request.civi_client
       response = await client.get("Contact", limit=10)
       return JsonResponse({"contacts": response.values})


   async def search_contacts(request):
       query = request.GET.get("q", "")
       client = request.civi_client

       response = await client.get(
           "Contact",
           where=[["display_name", "CONTAINS", query]],
           select=["id", "display_name", "email_primary.email"],
           limit=25,
       )
       return JsonResponse({"results": response.values})


Class-Based Views
^^^^^^^^^^^^^^^^^

.. code-block:: python

   from django.views import View
   from django.http import JsonResponse


   class ContactListView(View):
       def get(self, request):
           client = request.civi_client
           response = client.get("Contact", limit=10)
           return JsonResponse({"contacts": response.values})


Helper Function
^^^^^^^^^^^^^^^

For explicit error handling, use the helper function:

.. code-block:: python

   from civicrm_py.contrib.django.middleware import get_client_from_request


   def my_view(request):
       try:
           client = get_client_from_request(request)
       except AttributeError:
           return JsonResponse({"error": "CiviCRM not available"}, status=503)

       response = client.get("Contact", limit=10)
       return JsonResponse({"contacts": response.values})


Template Tags
-------------

Load the template tags in your templates:

.. code-block:: html+django

   {% load civi_tags %}

Fetching Data
^^^^^^^^^^^^^

Fetch a single contact by ID:

.. code-block:: html+django

   {% civi_contact id=1 as contact %}
   <h1>{{ contact.display_name }}</h1>

Fetch multiple contacts with filtering:

.. code-block:: html+django

   {% civi_contacts filter="contact_type=Individual" limit=5 as contacts %}
   <ul>
   {% for contact in contacts %}
       <li>{{ contact.display_name }}</li>
   {% endfor %}
   </ul>

Fetch any entity type:

.. code-block:: html+django

   {% civi_entity "Activity" id=5 as activity %}
   <p>{{ activity.subject }}</p>

   {% civi_entities "Activity" filter="status_id=1" as activities %}

Filters
^^^^^^^

Access nested fields:

.. code-block:: html+django

   {{ contact|civi_field:"email_primary.email" }}
   {{ contact|civi_field:"address_primary.city" }}

Format dates:

.. code-block:: html+django

   {{ activity.activity_date_time|civi_format_date:"%B %d, %Y" }}

Format currency:

.. code-block:: html+django

   {{ contribution.total_amount|civi_format_currency:"USD" }}

Display human-readable labels:

.. code-block:: html+django

   {{ contact.contact_type|civi_contact_type_label }}

Boolean icons:

.. code-block:: html+django

   {{ contact.do_not_email|civi_bool_icon }}

Truncate text:

.. code-block:: html+django

   {{ activity.details|civi_truncate:100 }}

Inclusion Tags
^^^^^^^^^^^^^^

Render a contact card:

.. code-block:: html+django

   {% civi_contact_card contact %}

Render a contact list:

.. code-block:: html+django

   {% civi_contact_list contacts %}

Block Tags
^^^^^^^^^^

Access client in template:

.. code-block:: html+django

   {% civi_with_client as client %}
       {# client is available here #}
   {% endcivi_with_client %}


Context Processor
-----------------

Add the context processor for automatic ``civi_client`` availability in all templates:

.. code-block:: python

   TEMPLATES = [{
       "OPTIONS": {
           "context_processors": [
               # ...
               "civicrm_py.contrib.django.templatetags.civi_tags.civi_context_processor",
           ],
       },
   }]


Management Commands
-------------------

Interactive Shell
^^^^^^^^^^^^^^^^^

Launch an interactive shell with CiviCRM client pre-configured:

.. code-block:: bash

   python manage.py civi_shell

The shell provides:

* Pre-imported ``client`` instance
* Auto-completion for entities
* History support

Example session:

.. code-block:: python

   >>> response = client.get("Contact", limit=5)
   >>> for contact in response.values:
   ...     print(contact["display_name"])


Admin Integration
-----------------

The admin integration allows browsing and editing CiviCRM entities through Django admin without Django models.

Setup
^^^^^

Create a ``civiadmin.py`` file in your app:

.. code-block:: python

   # myapp/civiadmin.py

   from civicrm_py.contrib.django.admin import (
       CiviModelAdmin,
       register_entity,
       civi_admin_site,
   )
   from civicrm_py.entities import Contact


   @register_entity(Contact, site=civi_admin_site)
   class ContactAdmin(CiviModelAdmin):
       list_display = ["id", "display_name", "email_primary", "contact_type"]
       search_fields = ["display_name", "first_name", "last_name"]
       list_filter = ["contact_type", "is_deleted"]

Register the admin site in your URLs:

.. code-block:: python

   # urls.py

   from django.contrib import admin
   from django.urls import path
   from civicrm_py.contrib.django.admin import civi_admin_site

   urlpatterns = [
       path("admin/", admin.site.urls),
       path("civiadmin/", civi_admin_site.urls),
   ]

Admin Components
^^^^^^^^^^^^^^^^

``CiviModelAdmin``
   Base admin class for CiviCRM entities. Supports list_display, search_fields, list_filter, and pagination.

``CiviAdminSite``
   Custom admin site for CiviCRM data. Separate from Django's main admin.

``CiviInlineAdmin``
   Inline editing for related entities (e.g., activities on a contact).

``CiviQuerySet``
   Django QuerySet-like wrapper for CiviCRM API queries. Supports filtering, ordering, and pagination.

``register_entity``
   Decorator to register entity admin classes.

``autodiscover_entities``
   Auto-discover ``civiadmin.py`` modules in installed apps.

Example with Inline Admin
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from civicrm_py.contrib.django.admin import (
       CiviModelAdmin,
       CiviInlineAdmin,
       register_entity,
       civi_admin_site,
   )
   from civicrm_py.entities import Contact, Activity


   class ActivityInline(CiviInlineAdmin):
       model = Activity
       fk_field = "source_contact_id"
       extra = 0


   @register_entity(Contact, site=civi_admin_site)
   class ContactAdmin(CiviModelAdmin):
       list_display = ["id", "display_name", "contact_type"]
       inlines = [ActivityInline]


Complete Example
----------------

Here is a complete example combining middleware, views, and templates.

.. code-block:: python

   # settings.py

   INSTALLED_APPS = [
       # ...
       "civicrm_py.contrib.django",
   ]

   MIDDLEWARE = [
       # ...
       "civicrm_py.contrib.django.middleware.CiviMiddleware",
   ]

   CIVICRM_URL = "https://example.org/civicrm/ajax/api4"
   CIVICRM_API_KEY = "your-api-key"

.. code-block:: python

   # views.py

   from django.shortcuts import render
   from django.http import JsonResponse


   def contact_list(request):
       client = request.civi_client
       response = client.get("Contact", limit=25)
       return render(request, "contacts/list.html", {
           "contacts": response.values,
       })


   def api_contacts(request):
       client = request.civi_client
       response = client.get("Contact", limit=10)
       return JsonResponse({"contacts": response.values})

.. code-block:: html+django

   {# templates/contacts/list.html #}

   {% load civi_tags %}

   <h1>Contacts</h1>

   <table>
       <thead>
           <tr>
               <th>Name</th>
               <th>Email</th>
               <th>Type</th>
           </tr>
       </thead>
       <tbody>
           {% for contact in contacts %}
           <tr>
               <td>{{ contact.display_name }}</td>
               <td>{{ contact|civi_field:"email_primary.email" }}</td>
               <td>{{ contact.contact_type|civi_contact_type_label }}</td>
           </tr>
           {% endfor %}
       </tbody>
   </table>


Cleanup
-------

Client cleanup is handled automatically:

* Thread-local clients are cleaned up when threads terminate
* Async client is cleaned up when the ASGI application shuts down

For explicit cleanup (useful in tests), use:

.. code-block:: python

   from civicrm_py.contrib.django.middleware import close_clients, close_clients_async

   # In sync code
   close_clients()

   # In async code
   await close_clients_async()
