# Example Agent Conversations

Real transcripts captured against the running system (model: `kimi-k2.6`).
Tool traces shown are persisted per conversation and visible in the chat UI and via
`GET /api/agent/conversations/{id}`.

## 1. Submit a request (multi-turn, confirmation gate)

**User (Sarah, employee):**
> I need approval for a $5,000 laptop purchase from Apple. Justification: new hire equipment.

*Tool calls:* `list_workflow_templates` → `submit_request` (without `confirmed`) →
server returns `confirmation_required`.

**Assistant:**
> Please confirm the following submission:
>
> **Request:** Laptop purchase from Apple
> **Template:** Purchase Order
> **Amount:** $5,000.00
> **Requester:** Sarah Employee
> **Details:** Vendor: Apple | Justification: new hire equipment
>
> Do you want to submit this request? Please reply **yes** to confirm.

**User:**
> yes, please submit it

*Tool calls:* `submit_request` with `confirmed: true` → `status: submitted`.

**Assistant:**
> Your request has been submitted successfully.
>
> - **Request ID:** 1
> - **Title:** Laptop purchase from Apple
> - **Amount:** $5,000.00
> - **Status:** Pending
> - **Current step:** Manager approval
> - **Next approver:** Mark Manager (manager@acme.com)

Note: the server-side gate means nothing was written on the first turn — the request
only exists after the explicit confirmation.

## 2. Review pending approvals

**User (Mark, manager):**
> What requests are waiting for my approval?

*Tool calls:* `get_pending_approvals` (includes delegated items with `on_behalf_of`).

**Assistant:**
> You have **1** request waiting for your approval:
>
> 1. **Laptop purchase from Apple** — Requested by **Sarah Employee**
>    - Amount: **$5,000.00**
>    - Current step: **Manager approval**
>    - Waiting time: **less than a minute**
>    - Status: Directly assigned to you (not delegated)
>
> Would you like to review the details of this request or approve/reject it?

## 3. Make an approval decision (context + confirmation)

**User (Mark, manager):**
> Approve Sarah's laptop purchase request.

*Tool calls:* `get_request_details` → `decide_request` (without `confirmed`) →
`confirmation_required`.

**Assistant:**
> Here is the context for the request:
>
> **Request #1: Laptop purchase from Apple**
> - Requester: Sarah Employee
> - Amount: **$5,000.00**
> - Vendor: Apple
> - Justification: new hire equipment
> - Current step: Manager approval
> - Prior decisions: None
>
> Do you confirm you want to approve this request? (Reply "yes" to confirm.)

**User:**
> yes

*Tool calls:* `decide_request` with `confirmed: true` → `decision_recorded`.

**Assistant:**
> Done. You have approved **Laptop purchase from Apple** (request #1) for **$5,000.00**
> requested by Sarah Employee. The request status is now **approved**.

Resulting audit trail (`GET /api/audit?request_id=1`):
`request_submitted → step_skipped ×2 (conditions) → step_activated → decision_approved →
step_completed → request_approved`

## 4. Create a workflow template (admin)

**User (Alice, admin):**
> Create a workflow where purchases over $10,000 require Finance approval followed by VP approval.

*Expected tool flow:* `list_users_and_groups` → `create_workflow_template` (without
`confirmed`) → the assistant presents the generated definition (steps, conditions) →
user confirms → template created. Non-admin users receive a permission error from the
tool, which the assistant relays.

## Authorization behaviors worth noting

- Tools always execute as the authenticated user; the same RBAC as the REST API applies.
  An employee asking the agent to create a template gets a clear "admins only" answer.
- A user asking to approve a request they are not an approver for receives the
  engine's `PermissionDeniedError` relayed in plain language.
- Every executed action lands in the audit trail with the real actor recorded.
