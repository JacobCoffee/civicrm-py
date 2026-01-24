Flask Integration
=================

Extension for Flask with automatic client lifecycle, request context integration, and CLI commands.

Installation
------------

Install with the Flask extra:

.. code-block:: bash

   pip install civicrm-py[flask]


Basic Setup
-----------

Initialize the extension with your Flask app:

.. code-block:: python

   from flask import Flask, g
   from civicrm_py.contrib.flask import CiviFlask

   app = Flask(__name__)
   app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"
   app.config["CIVI_API_KEY"] = "your-api-key"

   civi = CiviFlask(app)


   @app.route("/contacts")
   def list_contacts():
       response = g.civi_client.get("Contact", limit=10)
       return {"contacts": response.values}


Application Factory Pattern
---------------------------

For larger applications using the factory pattern:

.. code-block:: python

   from flask import Flask
   from civicrm_py.contrib.flask import CiviFlask

   civi = CiviFlask()


   def create_app():
       app = Flask(__name__)
       app.config.from_prefixed_env()  # Loads CIVI_* from environment
       civi.init_app(app)
       return app


Configuration Options
---------------------

Set configuration in ``app.config``:

.. code-block:: python

   # Required
   app.config["CIVI_BASE_URL"] = "https://example.org/civicrm/ajax/api4"

   # Authentication (choose one)
   app.config["CIVI_API_KEY"] = "your-api-key"        # API key auth
   app.config["CIVI_AUTH_TYPE"] = "api_key"           # api_key, jwt, or basic

   # For JWT authentication
   app.config["CIVI_AUTH_TYPE"] = "jwt"
   app.config["CIVI_JWT_TOKEN"] = "your-jwt-token"

   # For basic authentication
   app.config["CIVI_AUTH_TYPE"] = "basic"
   app.config["CIVI_USERNAME"] = "admin"
   app.config["CIVI_PASSWORD"] = "secret"

   # Optional settings
   app.config["CIVI_SITE_KEY"] = "your-site-key"
   app.config["CIVI_TIMEOUT"] = 30                    # Request timeout
   app.config["CIVI_VERIFY_SSL"] = True               # SSL verification
   app.config["CIVI_DEBUG"] = False                   # Debug logging
   app.config["CIVI_MAX_RETRIES"] = 3                 # Retry attempts
   app.config["CIVI_USE_THREAD_LOCAL"] = True         # Thread-local clients

Or use environment variables with ``app.config.from_prefixed_env()``:

.. code-block:: bash

   export CIVI_BASE_URL=https://example.org/civicrm/ajax/api4
   export CIVI_API_KEY=your-api-key


Using in Views
--------------

The client is attached to Flask's ``g`` object before each request.

Basic Usage
^^^^^^^^^^^

.. code-block:: python

   from flask import Flask, g, jsonify, request
   from civicrm_py.contrib.flask import CiviFlask

   app = Flask(__name__)
   CiviFlask(app)


   @app.route("/contacts")
   def list_contacts():
       response = g.civi_client.get("Contact", limit=25)
       return jsonify({"contacts": response.values})


   @app.route("/contacts/<int:contact_id>")
   def get_contact(contact_id):
       response = g.civi_client.get(
           "Contact",
           where=[["id", "=", contact_id]],
           limit=1,
       )
       if not response.values:
           return jsonify({"error": "Not found"}), 404
       return jsonify(response.values[0])


   @app.route("/contacts", methods=["POST"])
   def create_contact():
       data = request.get_json()
       response = g.civi_client.create("Contact", data)
       return jsonify(response.values[0]), 201

Using the Helper Function
^^^^^^^^^^^^^^^^^^^^^^^^^

For explicit error handling:

.. code-block:: python

   from civicrm_py.contrib.flask import get_civi_client


   @app.route("/contacts")
   def list_contacts():
       try:
           client = get_civi_client()
       except RuntimeError:
           return jsonify({"error": "CiviCRM not available"}), 503

       response = client.get("Contact", limit=10)
       return jsonify({"contacts": response.values})


With Explicit Settings
^^^^^^^^^^^^^^^^^^^^^^

Pass settings directly to the extension:

.. code-block:: python

   from civicrm_py.core.config import CiviSettings
   from civicrm_py.contrib.flask import CiviFlask

   settings = CiviSettings(
       base_url="https://example.org/civicrm/ajax/api4",
       api_key="your-api-key",
       timeout=60,
   )

   civi = CiviFlask(app, settings=settings)


Extension Configuration
-----------------------

Customize extension behavior with ``CiviFlaskConfig``:

.. code-block:: python

   from civicrm_py.contrib.flask import CiviFlask, CiviFlaskConfig

   config = CiviFlaskConfig(
       use_thread_local=True,   # Thread-local clients (recommended)
       register_cli=True,       # Register CLI commands
       debug=False,             # Debug logging
   )

   civi = CiviFlask(app, config=config)


CLI Commands
------------

The extension registers two CLI commands.

Connection Check
^^^^^^^^^^^^^^^^

Verify CiviCRM connectivity:

.. code-block:: bash

   $ flask civi-check

   CiviCRM API Status:
     URL: https://example.org/civicrm/ajax/api4
     Status: Connected
     Response Time: 45ms

Interactive Shell
^^^^^^^^^^^^^^^^^

Launch an interactive shell with the client pre-configured:

.. code-block:: bash

   $ flask civi-shell

   CiviCRM Interactive Shell
   Client available as 'client'

   >>> response = client.get("Contact", limit=5)
   >>> for contact in response.values:
   ...     print(contact["display_name"])
   Jane Doe
   John Smith


Thread Safety
-------------

The extension supports two modes for multi-threaded WSGI servers.

Thread-Local Mode (Default)
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Each thread gets its own client instance. Safe for Gunicorn with sync workers:

.. code-block:: python

   config = CiviFlaskConfig(use_thread_local=True)

Shared Client Mode
^^^^^^^^^^^^^^^^^^

A single client shared across threads. Uses double-checked locking:

.. code-block:: python

   config = CiviFlaskConfig(use_thread_local=False)


Accessing the Extension
-----------------------

Access the extension instance from the app:

.. code-block:: python

   from flask import current_app


   @app.route("/status")
   def status():
       civi = current_app.extensions["civi"]
       return {
           "url": civi.settings.base_url,
           "timeout": civi.settings.timeout,
       }


Complete Example
----------------

.. code-block:: python

   from flask import Flask, g, jsonify, request
   from civicrm_py.contrib.flask import CiviFlask


   def create_app():
       app = Flask(__name__)

       # Configuration from environment
       app.config.from_prefixed_env()

       # Initialize extension
       CiviFlask(app)

       # Register routes
       register_routes(app)

       return app


   def register_routes(app):
       @app.route("/api/contacts")
       def list_contacts():
           limit = request.args.get("limit", 25, type=int)
           offset = request.args.get("offset", 0, type=int)

           response = g.civi_client.get(
               "Contact",
               select=["id", "display_name", "email_primary.email"],
               where=[["is_deleted", "=", False]],
               limit=limit,
               offset=offset,
           )

           return jsonify({
               "contacts": response.values,
               "count": response.count,
           })

       @app.route("/api/contacts/<int:contact_id>")
       def get_contact(contact_id):
           response = g.civi_client.get(
               "Contact",
               where=[["id", "=", contact_id]],
               limit=1,
           )

           if not response.values:
               return jsonify({"error": "Contact not found"}), 404

           return jsonify(response.values[0])

       @app.route("/api/contacts", methods=["POST"])
       def create_contact():
           data = request.get_json()

           if not data:
               return jsonify({"error": "No data provided"}), 400

           response = g.civi_client.create("Contact", data)
           return jsonify(response.values[0]), 201

       @app.route("/api/contacts/<int:contact_id>", methods=["PUT"])
       def update_contact(contact_id):
           data = request.get_json()

           response = g.civi_client.update(
               "Contact",
               values=data,
               where=[["id", "=", contact_id]],
           )

           if not response.values:
               return jsonify({"error": "Contact not found"}), 404

           return jsonify(response.values[0])

       @app.route("/api/contacts/<int:contact_id>", methods=["DELETE"])
       def delete_contact(contact_id):
           response = g.civi_client.delete(
               "Contact",
               where=[["id", "=", contact_id]],
           )

           if response.count == 0:
               return jsonify({"error": "Contact not found"}), 404

           return "", 204


   if __name__ == "__main__":
       app = create_app()
       app.run(debug=True)


Cleanup
-------

Client cleanup happens automatically via ``atexit``. For explicit cleanup:

.. code-block:: python

   # Access the extension and close
   civi = app.extensions["civi"]
   # Cleanup happens automatically at process exit
