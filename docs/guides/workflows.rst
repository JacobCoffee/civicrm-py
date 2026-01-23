Workflow Automation
===================

Automate multi-step CiviCRM operations with human approval workflows using litestar-workflows.

The workflows integration provides:

- **Step primitives**: Reusable CiviCRM operation steps
- **Workflow templates**: Pre-built workflows for common scenarios
- **Human approval**: Pause workflows for manual review
- **Litestar integration**: REST API for workflow management

Installation
------------

Install with the workflows extra:

.. code-block:: bash

   pip install civi-py[workflows]

This installs litestar-workflows and its dependencies.


Workflow Concepts
-----------------

Workflows are defined as a series of steps connected by edges (transitions).

**Machine Steps**
    Automated steps that execute CiviCRM operations without human intervention.

**Human Steps**
    Steps that pause the workflow for manual review or approval.

**Workflow Context**
    Shared state passed between steps during execution.

**Edges**
    Define transitions between steps, optionally with conditions.


Step Primitives
---------------

civi-py provides four CiviCRM-specific step types.

CiviFetchStep
^^^^^^^^^^^^^

Fetch data from CiviCRM and store it in the workflow context:

.. code-block:: python

   from civi_py.contrib.workflows import CiviFetchStep

   fetch_contacts = CiviFetchStep(
       name="fetch_contacts",
       description="Fetch active contacts for review",
       entity="Contact",
       filters={
           "is_deleted": False,
           "contact_type": "Individual",
       },
       select=["id", "display_name", "email_primary.email"],
       order_by={"display_name": "ASC"},
       limit=100,
       context_key="contacts_to_review",
   )

After execution, ``context.get("contacts_to_review")`` contains the fetched records.

Parameters:

- ``name``: Unique step identifier
- ``entity``: CiviCRM entity name
- ``filters``: Dictionary of filter conditions
- ``select``: Fields to include in response
- ``order_by``: Sort order (field: "ASC" or "DESC")
- ``limit``: Maximum records to fetch
- ``offset``: Pagination offset
- ``context_key``: Key for storing results in context

CiviMutateStep
^^^^^^^^^^^^^^

Create, update, or delete CiviCRM records:

.. code-block:: python

   from civi_py.contrib.workflows import CiviMutateStep

   # Create new contacts
   create_contacts = CiviMutateStep(
       name="create_contacts",
       description="Create contacts from import data",
       entity="Contact",
       action="create",
       data_context_key="contacts_to_create",
       result_context_key="created_contacts",
       batch_size=50,
   )

   # Update existing contacts
   update_contacts = CiviMutateStep(
       name="update_contacts",
       description="Apply approved changes",
       entity="Contact",
       action="update",
       data_context_key="contacts_to_update",
       result_context_key="update_results",
   )

   # Delete contacts
   delete_contacts = CiviMutateStep(
       name="delete_contacts",
       entity="Contact",
       action="delete",
       data_context_key="contacts_to_delete",
       result_context_key="delete_results",
   )

Parameters:

- ``action``: Operation type (``create``, ``update``, ``delete``)
- ``data_context_key``: Key containing data to mutate
- ``result_context_key``: Key for storing operation results
- ``batch_size``: Records per API call for batch operations

CiviApprovalStep
^^^^^^^^^^^^^^^^

Pause workflow for human review and approval:

.. code-block:: python

   from civi_py.contrib.workflows import CiviApprovalStep

   review_step = CiviApprovalStep(
       name="review_contacts",
       title="Review Contact Updates",
       description="Review and approve the proposed changes",
       data_context_key="contacts_to_review",
       show_fields=["display_name", "email_primary.email"],
       require_comments_on_reject=True,
   )

The step generates a form with:

- ``approved`` (boolean): Approval decision
- ``comments`` (string): Optional reviewer notes
- ``reviewer_id`` (integer): Optional CiviCRM contact ID

Parameters:

- ``title``: Human-readable title for the task
- ``data_context_key``: Key containing data to display
- ``show_fields``: Fields to display for review
- ``require_comments_on_reject``: Require comments when rejecting

CiviSyncStep
^^^^^^^^^^^^

Sync data between CiviCRM and local database cache:

.. code-block:: python

   from civi_py.contrib.workflows import CiviSyncStep

   # Sync from CiviCRM to local cache
   sync_from_civi = CiviSyncStep(
       name="sync_contacts",
       description="Sync contacts to local database",
       entity="Contact",
       direction="from_civi",
       filters={"is_deleted": False},
       select=["id", "display_name", "email_primary.email"],
       batch_size=500,
       sync_result_key="sync_results",
       repository_key="contact_repository",
   )

   # Sync from local cache to CiviCRM
   sync_to_civi = CiviSyncStep(
       name="push_changes",
       description="Push local changes to CiviCRM",
       entity="Contact",
       direction="to_civi",
       sync_result_key="push_results",
   )

This step requires both workflows and sqlspec:

.. code-block:: bash

   pip install 'civi-py[workflows,sqlspec]'


Workflow Templates
------------------

Pre-built workflows for common CiviCRM automation scenarios.

ContactSyncWorkflow
^^^^^^^^^^^^^^^^^^^

Fetch contacts, human review, sync to local database:

.. code-block:: python

   from civi_py.contrib.workflows import WORKFLOWS_AVAILABLE
   from civi_py.contrib.workflows.templates import ContactSyncWorkflow

   if WORKFLOWS_AVAILABLE:
       definition = ContactSyncWorkflow.get_definition(
           filters={"contact_type": "Individual", "is_deleted": False},
           select=["id", "display_name", "email_primary.email"],
           limit=100,
           show_fields=["display_name", "email_primary.email"],
       )

Workflow flow::

    [fetch_contacts] --> [review_contacts] --> [sync_approved]
                                |
                                +--> (rejected: end)

BulkUpdateWorkflow
^^^^^^^^^^^^^^^^^^

Select entities, approve changes, execute bulk update:

.. code-block:: python

   from civi_py.contrib.workflows.templates import BulkUpdateWorkflow

   definition = BulkUpdateWorkflow.get_definition(
       entity="Contact",
       select_filters={"do_not_email": True},
       select_fields=["id", "display_name", "email_primary.email"],
       update_fields={"do_not_mail": True},
       limit=500,
   )

Workflow flow::

    [select_entities] --> [approve_changes] --> [execute_update] --> [log_results]
                                 |
                                 +--> (rejected: end)

MembershipRenewalWorkflow
^^^^^^^^^^^^^^^^^^^^^^^^^

Check expiring memberships, notify, process renewals:

.. code-block:: python

   from civi_py.contrib.workflows.templates import MembershipRenewalWorkflow

   definition = MembershipRenewalWorkflow.get_definition(
       days_until_expiry=30,
       membership_types=[1, 2],  # Specific membership type IDs
       membership_status=["Current", "Grace"],
       renewal_period_months=12,
   )

Workflow flow::

    [check_expiring] --> [send_notifications] --> [process_renewals] --> [update_memberships]
                                                          |
                                                          +--> (no renewals: end)

DonationProcessingWorkflow
^^^^^^^^^^^^^^^^^^^^^^^^^^

Validate donation, approve large amounts, create contribution:

.. code-block:: python

   from civi_py.contrib.workflows.templates import DonationProcessingWorkflow

   definition = DonationProcessingWorkflow.get_definition(
       approval_threshold=1000.0,  # Require approval for $1000+
       default_financial_type_id=1,  # Donation type
       default_payment_instrument_id=4,  # Credit card
       auto_receipt=True,
   )

Workflow flow::

    [validate_donation] --> [approve_donation] --> [create_contribution] --> [generate_receipt]
                                  |
                                  +--> (small amount: skip to create_contribution)


Creating Custom Workflows
-------------------------

Build custom workflows using step primitives and edges.

Basic Workflow
^^^^^^^^^^^^^^

.. code-block:: python

   from civi_py.contrib.workflows import (
       WORKFLOWS_AVAILABLE,
       require_workflows,
       WorkflowDefinition,
       Edge,
       CiviFetchStep,
       CiviApprovalStep,
       CiviMutateStep,
   )

   def create_contact_update_workflow():
       require_workflows()  # Raises ImportError if not available

       # Step 1: Fetch contacts to update
       fetch_step = CiviFetchStep(
           name="fetch_contacts",
           entity="Contact",
           filters={"contact_sub_type": "Volunteer", "is_deleted": False},
           select=["id", "display_name", "email_primary.email"],
           limit=50,
           context_key="volunteers",
       )

       # Step 2: Human reviews the list
       review_step = CiviApprovalStep(
           name="review_volunteers",
           title="Review Volunteer Contact Updates",
           description="Review volunteers and approve mass communication settings",
           data_context_key="volunteers",
           show_fields=["display_name", "email_primary.email"],
       )

       # Step 3: Apply updates
       update_step = CiviMutateStep(
           name="update_volunteers",
           entity="Contact",
           action="update",
           data_context_key="prepared_updates",
           result_context_key="update_results",
       )

       # Condition for approval
       def is_approved(context):
           if not context.get("approved", False):
               return False
           # Prepare update data
           volunteers = context.get("volunteers", [])
           updates = [
               {"id": v["id"], "do_not_email": False}
               for v in volunteers if "id" in v
           ]
           context.set("prepared_updates", updates)
           return True

       return WorkflowDefinition(
           name="volunteer_contact_update",
           version="1.0.0",
           description="Update volunteer contact preferences with approval",
           steps={
               "fetch_contacts": fetch_step,
               "review_volunteers": review_step,
               "update_volunteers": update_step,
           },
           edges=[
               Edge("fetch_contacts", "review_volunteers"),
               Edge("review_volunteers", "update_volunteers", condition=is_approved),
           ],
           initial_step="fetch_contacts",
           terminal_steps={"update_volunteers", "review_volunteers"},
       )

Registering Workflows
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from litestar_workflows import WorkflowRegistry, LocalExecutionEngine

   # Create registry
   registry = WorkflowRegistry()

   # Register workflow
   definition = create_contact_update_workflow()
   registry.register(definition.name, definition)

   # Create execution engine
   engine = LocalExecutionEngine(registry=registry)


Executing Workflows
-------------------

Run workflows with the execution engine.

Starting a Workflow
^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from civi_py import CiviClient

   async def start_workflow():
       async with CiviClient() as client:
           # Prepare initial context
           context = {
               "civi_client": client,
               # Add any additional initial data
           }

           # Start workflow
           instance = await engine.start(
               "volunteer_contact_update",
               instance_id="wf-001",
               context=context,
           )

           print(f"Started: {instance.id}")
           print(f"Status: {instance.status}")

The workflow runs until it completes, fails, or reaches a human step.

Completing Human Tasks
^^^^^^^^^^^^^^^^^^^^^^

When a workflow pauses at a human step:

.. code-block:: python

   # Get pending task info
   task = await engine.get_pending_task("wf-001")

   print(f"Task: {task.title}")
   print(f"Form: {task.form_schema}")
   print(f"Data: {task.review_data}")

   # Submit form data to complete
   await engine.complete_human_step(
       instance_id="wf-001",
       step_name="review_volunteers",
       form_data={
           "approved": True,
           "comments": "Looks good, proceed with updates",
           "reviewer_id": 42,
       },
   )

Monitoring Progress
^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   # Get instance status
   instance = await engine.get_instance("wf-001")

   print(f"Status: {instance.status}")
   print(f"Current step: {instance.current_step}")
   print(f"Started: {instance.started_at}")
   print(f"Completed: {instance.completed_at}")


Litestar Integration
--------------------

Expose workflows through a REST API with the Litestar plugin.

Plugin Configuration
^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from litestar import Litestar
   from civi_py.contrib.litestar import CiviPlugin, CiviPluginConfig
   from civi_py.contrib.litestar.workflows_integration import WorkflowPluginConfig

   config = CiviPluginConfig(
       workflows=WorkflowPluginConfig(
           enabled=True,
           api_prefix="/api/civi/workflows",
           register_builtins=True,  # Register built-in templates
           custom_workflows=[],  # Add custom workflow classes
           execution_timeout=300,  # 5 minute timeout
       ),
   )

   app = Litestar(plugins=[CiviPlugin(config)])

REST API Endpoints
^^^^^^^^^^^^^^^^^^

The plugin generates these endpoints:

.. list-table::
   :header-rows: 1
   :widths: 15 40 45

   * - Method
     - Path
     - Description
   * - GET
     - ``/api/civi/workflows/``
     - List available workflow definitions
   * - POST
     - ``/api/civi/workflows/{name}/start``
     - Start a new workflow instance
   * - GET
     - ``/api/civi/workflows/instances``
     - List workflow instances
   * - GET
     - ``/api/civi/workflows/instances/{id}``
     - Get instance details and history
   * - POST
     - ``/api/civi/workflows/instances/{id}/complete``
     - Complete a pending human task
   * - GET
     - ``/api/civi/workflows/tasks``
     - List all pending human tasks

Example API Usage
^^^^^^^^^^^^^^^^^

List available workflows:

.. code-block:: bash

   curl http://localhost:8000/api/civi/workflows/

Response:

.. code-block:: json

   {
     "workflows": [
       {
         "name": "contact_sync",
         "description": "Fetch contacts from CiviCRM, review, and sync to local database",
         "steps": ["fetch_contacts", "review_contacts", "sync_approved"],
         "human_steps": ["review_contacts"]
       }
     ],
     "count": 1
   }

Start a workflow:

.. code-block:: bash

   curl -X POST http://localhost:8000/api/civi/workflows/contact_sync/start \
     -H "Content-Type: application/json" \
     -d '{"initial_context": {"filters": {"contact_type": "Individual"}}}'

Response:

.. code-block:: json

   {
     "instance_id": "550e8400-e29b-41d4-a716-446655440000",
     "workflow_name": "contact_sync",
     "status": "running"
   }

Complete a human task:

.. code-block:: bash

   curl -X POST http://localhost:8000/api/civi/workflows/instances/550e8400.../complete \
     -H "Content-Type: application/json" \
     -d '{"form_data": {"approved": true, "comments": "Approved"}}'


Error Handling
--------------

Handle workflow errors gracefully.

CiviWorkflowError
^^^^^^^^^^^^^^^^^

All workflow step errors are wrapped in ``CiviWorkflowError``:

.. code-block:: python

   from civi_py.contrib.workflows import CiviWorkflowError

   try:
       await engine.start("my_workflow", context=context)
   except CiviWorkflowError as e:
       print(f"Step '{e.step_name}' failed: {e.message}")
       print(f"Details: {e.details}")

Graceful Degradation
^^^^^^^^^^^^^^^^^^^^

Check if workflows are available before using:

.. code-block:: python

   from civi_py.contrib.workflows import WORKFLOWS_AVAILABLE, require_workflows

   # Check availability
   if WORKFLOWS_AVAILABLE:
       # Use workflow features
       pass
   else:
       # Fall back to direct API calls
       pass

   # Or raise helpful error
   def my_workflow_function():
       require_workflows()  # Raises ImportError with install instructions
       # ... workflow code


Complete Example
----------------

Full example combining custom workflow with Litestar:

.. code-block:: python

   from litestar import Litestar, get, post
   from litestar.params import Parameter

   from civi_py.contrib.litestar import CiviPlugin, CiviPluginConfig
   from civi_py.contrib.litestar.workflows_integration import WorkflowPluginConfig
   from civi_py.contrib.workflows import (
       WORKFLOWS_AVAILABLE,
       CiviFetchStep,
       CiviApprovalStep,
       CiviMutateStep,
       WorkflowDefinition,
       Edge,
   )


   # Custom workflow definition
   def create_donation_acknowledgment_workflow():
       """Workflow to acknowledge donations with human review for large amounts."""

       fetch_step = CiviFetchStep(
           name="fetch_donations",
           entity="Contribution",
           filters={
               "receive_date": {">=": "2025-01-01"},
               "is_test": False,
           },
           select=[
               "id",
               "contact_id.display_name",
               "total_amount",
               "receive_date",
               "contribution_status_id:label",
           ],
           order_by={"total_amount": "DESC"},
           limit=50,
           context_key="donations",
       )

       review_step = CiviApprovalStep(
           name="review_donations",
           title="Review Donation Acknowledgments",
           description="Review donations and approve for acknowledgment letters",
           data_context_key="donations",
           show_fields=[
               "contact_id.display_name",
               "total_amount",
               "receive_date",
           ],
           require_comments_on_reject=True,
       )

       # Prepare acknowledgment activities
       acknowledge_step = CiviMutateStep(
           name="create_acknowledgments",
           entity="Activity",
           action="create",
           data_context_key="acknowledgment_activities",
           result_context_key="created_activities",
       )

       def prepare_acknowledgments(context):
           if not context.get("approved", False):
               return False

           donations = context.get("donations", [])
           activities = []

           for donation in donations:
               activities.append({
                   "activity_type_id": 5,  # Letter
                   "subject": f"Donation Acknowledgment - ${donation.get('total_amount', 0)}",
                   "source_contact_id": donation.get("contact_id"),
                   "target_contact_id": donation.get("contact_id"),
                   "status_id": 1,  # Scheduled
               })

           context.set("acknowledgment_activities", activities)
           return True

       return WorkflowDefinition(
           name="donation_acknowledgment",
           version="1.0.0",
           description="Create acknowledgment activities for donations",
           steps={
               "fetch_donations": fetch_step,
               "review_donations": review_step,
               "create_acknowledgments": acknowledge_step,
           },
           edges=[
               Edge("fetch_donations", "review_donations"),
               Edge("review_donations", "create_acknowledgments", condition=prepare_acknowledgments),
           ],
           initial_step="fetch_donations",
           terminal_steps={"create_acknowledgments", "review_donations"},
       )


   # Custom endpoint to check workflow health
   @get("/workflow-status")
   async def workflow_status() -> dict:
       return {
           "workflows_available": WORKFLOWS_AVAILABLE,
           "status": "operational" if WORKFLOWS_AVAILABLE else "unavailable",
       }


   # Application setup
   if WORKFLOWS_AVAILABLE:
       custom_workflows = [create_donation_acknowledgment_workflow()]
   else:
       custom_workflows = []

   config = CiviPluginConfig(
       workflows=WorkflowPluginConfig(
           enabled=WORKFLOWS_AVAILABLE,
           api_prefix="/api/workflows",
           register_builtins=True,
           custom_workflows=custom_workflows,
       ),
   )

   app = Litestar(
       route_handlers=[workflow_status],
       plugins=[CiviPlugin(config)],
   )
