# UAT Results V2 — Role/Flow Clarifications

**Date executed:** 2026-07-03
**Branch:** `feature/role-flow-clarifications`
**Environment:** Docker Compose stack rebuilt **from scratch (empty database)** before the
session (`docker compose down -v && up --build`); Playwright against http://localhost:3000;
agent scenarios ran against the live Kimi `kimi-k2.6` model.
**Plan:** `TEST_PLAN_V2.md` (UAT section, U1–U10). Evidence in `screenshots/`.

## Summary — 10/10 scenarios PASS

| ID | Scenario | Result |
|---|---|---|
| U1 | Role menus (all 5 roles, real logins) | PASS |
| U2 | Deep-link route guards | PASS |
| U3 | Employee inbox = status feed only | PASS |
| U4 | Full chain approval via UI (manager → finance → vp) | PASS |
| U5 | Status feed message format | PASS |
| U6 | Delegation picker role filtering | PASS |
| U7 | Manager request skips manager step | PASS (cosmetic label fixed during UAT) |
| U8 | Admin default landing = /templates | PASS |
| U9 | Agent (live): status question in message format | PASS |
| U10 | Agent (live): early refusal of disallowed action | PASS |

## Details

- **U1 — menus.** admin: `AI Assistant, Workflow Templates, Sign out`; employee (Sarah):
  `Approval Inbox, My Requests, AI Assistant, Sign out`; manager/finance/vp:
  `Approval Inbox, My Requests, AI Assistant, Delegations, Sign out`. Exactly the
  clarified access matrix; no Templates entry for any non-admin.
- **U2 — deep links.** Admin loading `/inbox` → redirected to `/templates`. Sarah loading
  `/templates` (full page load) → redirected to `/inbox`; same for `/delegations`.
- **U3 — employee inbox.** Only the "My request status" card renders (empty-state text
  "You have not submitted any requests yet"); no "Waiting for your decision" table for
  employees. Approver roles see both cards. `screenshots/U5-employee-status-feed.png`.
- **U4 — chain via UI.** Sarah submitted "UAT2-U4 team offsite" ($2,200); Mark, Fiona and
  Victoria each saw it in their inbox in turn and approved through the decision modal.
  Final state `approved` with three decisions recorded in order.
- **U5 — status feed.** After Mark's approval, Sarah's feed read exactly
  **"Approved by Mark Manager; waiting for finance approval"**; after completion,
  "fully approved (by Mark Manager, Fiona Finance, Victoria VP)".
- **U6 — delegation picker.** As manager, the picker offered only
  `Fiona Finance (finance)`, `Frank Finance (finance)`, `Victoria VP (vp)` — no
  employees, no admin, no self — with helper text "As manager, you can delegate to:
  manager, finance, vp". `screenshots/U6-delegation-picker-filtered.png`.
- **U7 — manager request.** Mark's own request showed step 1 "Manager approval" skipped,
  Finance review active (Fiona + Frank pending), audit `submitted → step skipped → step
  activated`. *Finding fixed during UAT:* the skip tag was hardcoded "skipped by
  condition", misleading for role-based skips — relabeled to "skipped by routing rule"
  and the frontend image was rebuilt before completing the session.
- **U8 — admin landing.** Admin login lands directly on `/templates`.
- **U9 — agent status (live model).** Sarah asked "What is the status of my requests?";
  reply: `Request #2 "UAT2-U4 team offsite" — fully approved (by Mark Manager, Fiona
  Finance, Victoria VP).` — single `get_request_status` tool call.
- **U10 — agent refusal (live model).** Sarah asked to delegate approvals to Mike. The
  assistant declined immediately — "you have the 'employee' role… only manager, finance,
  or VP roles can delegate" — with **zero tool calls** for the turn (closes V1
  observation UAT-005: no more detail-gathering before hitting the permission wall).
  `screenshots/U10-agent-early-refusal.png`.

## Automation notes (not product defects)

- Two antd interactions (modal submit, select-dropdown open) needed a retried event —
  same first-synthetic-event flakiness noted in V1; every retry succeeded.
- Session switches between accounts used token injection after each role's real
  login/menu was verified through the actual login form.

## Companion runs on the same fresh-data basis

- Unit: 67/67 pass (SQLite in-memory, also the CI suite).
- Integration: 8/8 pass (`autotest/integration/run_integration.sh`, disposable Postgres,
  Alembic migration from empty schema).
- E2E: 21/21 checks pass (`autotest/e2e/run_e2e.sh --with-agent`, stack rebuilt with
  empty DB, live agent smoke included).
