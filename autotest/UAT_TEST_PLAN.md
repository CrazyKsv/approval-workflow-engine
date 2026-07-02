# UAT Test Plan — Approval Workflow Engine

**Date:** 2026-07-02
**System under test:** http://localhost:3000 (Docker Compose stack: React SPA → nginx → FastAPI → PostgreSQL, agent on Kimi `kimi-k2.6`)
**Method:** Manual-equivalent UI acceptance testing executed via browser automation (Playwright). Results recorded in `UAT_RESULTS.md`, screenshots in `screenshots/`.

## Test accounts (password: `password123`)

| Account | Role | Used for |
|---|---|---|
| sarah@acme.com | employee | requester scenarios |
| mike@acme.com | employee | delegate / negative RBAC scenarios |
| manager@acme.com | manager | first-line approvals, delegations |
| finance1@acme.com | finance | second-line approvals |
| admin@acme.com | admin | template administration |

## Seeded workflows relevant to the tests

- **Expense Report**: 1) Manager approval (role: manager, SLA 48h → VP) → 2) Finance review (group, `any`, only if `amount > 1000`)
- **Purchase Order**: 1) Manager → 2) Finance (`all`, if `amount > 5000`) → 3) VP (if `amount > 10000`)
- **Time Off Request**: 1) Manager approval

## Conventions

- Each run uses titles prefixed `UAT-<id>` so accumulated data from prior runs never causes ambiguity.
- Every scenario states: preconditions, steps, expected result. Pass = expected result observed on the UI.
- Data builds up across runs (no teardown); scenarios must not depend on absolute row counts, only on rows they created.

---

## Suite A — Authentication & access control

### A1 — Invalid login is rejected
1. Open http://localhost:3000 (logged out).
2. Enter `sarah@acme.com` / `wrongpassword`, click **Sign in**.
- **Expected:** error alert "Invalid email or password"; user remains on login page.

### A2 — Valid login lands on Approval Inbox
1. Login as `sarah@acme.com` / `password123`.
- **Expected:** redirected to **Approval Inbox**; header shows "Sarah Employee" with green `employee` role tag; sidebar shows Inbox / My Requests / AI Assistant / Delegations (no Workflow Templates).

### A3 — Admin sees template administration
1. Login as `admin@acme.com`.
- **Expected:** sidebar additionally shows **Workflow Templates**.

### A4 — Sign out
1. As any logged-in user click **Sign out** in the sidebar.
- **Expected:** returned to the login page; revisiting `/inbox` does not restore the session without logging in.

## Suite B — Request submission (employee)

### B1 — Small expense routes past Finance (conditional routing)
1. Login as Sarah → **My Requests** → **New Request**.
2. Workflow: Expense Report; Title: `UAT-B1 team lunch`; Amount: `500`; Expense category: `meals`. Submit.
- **Expected:** success toast; request appears in My Requests with status `pending`.
3. Open the request detail page.
- **Expected:** step "Manager approval" is in-progress; step "Finance review" is tagged **skipped by condition**; audit trail shows `request submitted` (Sarah) and `step activated`.

### B2 — Required-field validation blocks submission
1. Sarah → New Request → Workflow: Expense Report; Title: `UAT-B2 no category`; Amount: `100`; leave **Expense category** empty. Submit.
- **Expected:** form blocks submission with a required-field message on Expense category; no request created.

### B3 — Large expense includes Finance step
1. Sarah submits Expense Report: Title `UAT-B3 conference travel`, Amount `2500`, Category `travel`.
- **Expected:** request pending; detail shows Manager approval active AND Finance review pending (not skipped).

## Suite C — Approval inbox & decisions

### C1 — Manager inbox shows correct context
1. Login as `manager@acme.com` → Approval Inbox.
- **Expected:** rows for `UAT-B1` and `UAT-B3` showing requester "Sarah Employee", amounts, step "Manager approval", authority tag `own`, and an "any approver" mode tag.

### C2 — Approve with comment (single-step completion)
1. Manager clicks **Approve** on `UAT-B1`, enters comment `Looks good`, confirms.
- **Expected:** success toast; row disappears from inbox. Request detail (or Sarah's My Requests) shows `UAT-B1` status `approved`.

### C3 — Multi-step progression to Finance
1. Manager approves `UAT-B3`.
2. Login as `finance1@acme.com` → Inbox.
- **Expected:** `UAT-B3` now waits on "Finance review" for finance1; approving it moves the request to status `approved` (mode `any`: one finance member suffices).

### C4 — Reject is terminal
1. Sarah submits Expense Report `UAT-C4 gadget`, amount `1200`, category `hardware`.
2. Manager rejects it with comment `No budget this quarter`.
- **Expected:** request status `rejected`; it appears in no one's inbox afterwards (finance1 inbox does not contain it).

### C5 — Request changes
1. Sarah submits Expense Report `UAT-C5 software`, amount `800`, category `software`.
2. Manager clicks **Request changes**, comment `Please attach a quote`.
- **Expected:** request status `changes requested` visible to Sarah; item leaves the manager's inbox.

## Suite D — Request detail & audit

### D1 — Step timeline reflects outcomes
1. Open `UAT-B3` detail (as Sarah).
- **Expected:** Manager approval `finish` with Mark Manager tagged approved; Finance review shows finance approver approved; decisions table lists both decisions with comments.

### D2 — Audit trail completeness
1. On the same detail page inspect **Audit trail**.
- **Expected:** chronological entries covering `request submitted`, `step activated` (×2), `decision approved` (×2), `step completed` (×2), `request approved`, each with timestamp; decision entries name the actor.

### D3 — Cancel a pending request
1. Sarah submits Expense Report `UAT-D3 cancel me`, amount `200`, category `misc`.
2. Open detail → **Cancel request** → confirm.
- **Expected:** status changes to `cancelled`; manager's inbox no longer lists it.

## Suite E — Delegation

### E1 — Create a delegation
1. Login as manager → **Delegations** → **Delegate my approvals**.
2. Delegate to: Mike Employee; Period: now − 1h → now + 7 days; Reason: `UAT-E1 vacation`. Save.
- **Expected:** row appears with delegator Mark Manager, delegate Mike Employee, status `active now`.

### E2 — Delegated items appear in delegate's inbox
1. Sarah submits Expense Report `UAT-E2 monitor`, amount `900`, category `hardware`.
2. Login as `mike@acme.com` → Inbox.
- **Expected:** `UAT-E2` row present with authority tag **for Mark Manager** (orange).

### E3 — Delegate decides on behalf of delegator
1. Mike approves `UAT-E2` (modal shows "acting on behalf of Mark Manager").
- **Expected:** request `approved`; detail page decisions table shows the decision **by Mike Employee (for Mark Manager)**.

### E4 — Revoked delegation removes authority
1. Manager revokes the delegation (Delegations → Revoke).
2. Sarah submits Expense Report `UAT-E4 keyboard`, amount `300`, category `hardware`.
3. Mike's inbox.
- **Expected:** delegation row shows `revoked`; `UAT-E4` does NOT appear in Mike's inbox (manager still sees it).

## Suite F — Workflow template administration (admin)

### F1 — Seeded templates visible with routing detail
1. Login as admin → Workflow Templates.
- **Expected:** Expense Report / Purchase Order / Time Off Request listed; expanding Purchase Order shows 3 steps with condition tags (`if amount > 5000`, `if amount > 10000`) and SLA tags.

### F2 — Create a new template via the builder
1. **New Template**: Name `UAT-F2 Contract Approval`, category `legal`;
   field: name `contract_value`, label `Contract value`, type number, required;
   Step 1 `Manager review` (role: manager, any);
   Step 2 `VP sign-off` (role: vp, any, condition `contract_value > 50000`, SLA 24h, escalate to admin). Create.
- **Expected:** success toast; template listed with 2 steps and active toggle on.
2. Login as Sarah → New Request.
- **Expected:** `UAT-F2 Contract Approval` selectable; choosing it renders the `Contract value` field.

### F3 — Deactivated template not offered for submission
1. Admin toggles `UAT-F2 Contract Approval` inactive.
2. Sarah → New Request → workflow dropdown.
- **Expected:** `UAT-F2 Contract Approval` no longer offered.

## Suite G — AI Assistant (live model)

> These scenarios call the real Kimi API; allow 10–60s per assistant turn.

### G1 — Submit a request via chat with confirmation gate
1. Login as Sarah → **AI Assistant**.
2. Send: `I need approval for a $5,000 laptop purchase from Apple, justification: UAT-G1 new hire equipment.`
- **Expected:** assistant replies with a summary and asks for confirmation (no request created yet). Tool trace shows `submit_request` with `confirmation_required`.
3. Send: `yes, please submit it`.
- **Expected:** assistant confirms submission with a request id; **My Requests** now contains the laptop request, status `pending`; tool trace shows `submit_request` → `submitted`.

### G2 — Review pending approvals via chat
1. Login as manager → AI Assistant → `What requests are waiting for my approval?`
- **Expected:** reply lists the UAT-G1 laptop request (requester Sarah, $5,000, Manager approval step); tool trace shows `get_pending_approvals`.

### G3 — Approve via chat with confirmation
1. Continue as manager: `Approve Sarah's laptop purchase request.`
- **Expected:** assistant presents request context and asks for confirmation.
2. Send `yes`.
- **Expected:** assistant reports the approval; request status becomes `approved` (amount $5,000 is not > $5,000, so Finance is skipped).

### G4 — Assistant respects RBAC
1. Login as Sarah → AI Assistant → `Create a workflow template where all requests go straight to the VP.`
- **Expected:** assistant explains this needs admin permission (server returns PermissionDenied on the tool); no template is created (verify admin's template list unchanged).

## Suite H — Security / deep-link RBAC

### H1 — Non-admin deep link to /templates
1. As Sarah, navigate directly to http://localhost:3000/templates.
- **Expected:** no admin capability: creating a template must fail server-side (403). UI ideally hides the page; if it renders, attempting to create must show a permission error. Record actual behavior.

---

## Out of scope for UI UAT (covered elsewhere)

- SLA escalation (needs a 24–48h overdue step; engine behavior covered by unit test `test_overdue_step_escalates_and_escalation_overrides_quorum`).
- Parallel `all`-quorum finance approval via UI (covered by unit/API tests; UI path identical to C3).
- API-level pagination limits (covered by `test_pagination`).

## Exit criteria

All scenarios executed; failures and deviations documented in `UAT_RESULTS.md` with severity and reproduction notes. Blocking = data corruption, auth bypass, or a broken core flow (submit → approve).
