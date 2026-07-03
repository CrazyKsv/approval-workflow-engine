# Test Plan V2 — Role/Flow Clarifications

**Date:** 2026-07-03
**Branch:** `feature/role-flow-clarifications`
**Scope:** Product clarifications applied to backend + frontend:

1. Standard approval chain **manager → finance → vp**; the step matching the
   requester's own role is skipped (manager's request starts at finance).
2. UI access control — admin: Templates + Assistant only; employee: Inbox/My
   Requests/Assistant; manager/finance/vp: those + Delegations.
3. Delegation role matrix — manager→{manager,finance,vp}, finance→{finance,vp},
   vp→{finance}; employee/admin cannot delegate. Self-approval fully blocked
   (including via delegation).
4. Agent parity — role-aware capabilities, request-status feed messages
   ("approved by X; waiting for <role> approval"), guided template creation for admin.

**Fresh-data requirement:** integration, E2E and UAT all start from a completely empty
database. Unit tests use throwaway in-memory SQLite per test.

## Levels

### 1. Unit tests — `backend/tests/` (also run in CI)

Runner: `cd backend && python -m pytest tests`. In-memory SQLite, fixtures per test.

| Area | Cases |
|---|---|
| Chain routing | employee full chain; manager/finance/vp own-role skip; admin submit blocked |
| Conditions (custom templates) | operator matrix; conditional routing; `any`/`all` quorum |
| Decisions | reject terminal; changes-requested + resubmit restarts chain; non-approver 403 |
| Delegation | matrix (10 combinations); employee/admin blocked; delegated decision provenance; expired window; self-approval blocked even with delegated authority |
| Status feed | message progression (waiting → approved-by → rejected-by); personal scope |
| Escalation | SLA breach adds escalation approver; override of `all` quorum; within-SLA no-op |
| API | auth, RBAC (admin request/delegation 403), lifecycle over HTTP, pagination, audit, `/inbox/status` |
| Agent | multi-turn confirmation gate; delegated approvals in inbox tool; status tool format; delegation matrix + admin RBAC through tools; model-failure handling |

### 2. Integration tests — `backend/tests_integration/` (real PostgreSQL)

Runner: `./autotest/integration/run_integration.sh` — starts a **disposable Postgres
container**, drops/creates the schema, runs the **Alembic migration**, seeds once, then
exercises the API against the real database. Verifies what SQLite can't: migration DDL,
JSONB round-trips, timestamptz handling, seeded chain templates.

| ID | Case |
|---|---|
| INT-1 | Migration on empty DB creates all 14 tables |
| INT-2 | Seeded templates all use the manager→finance→vp chain |
| INT-3 | Employee chain lifecycle over HTTP with audit counts |
| INT-4 | Manager request skips manager step |
| INT-5 | Status feed message exact-match |
| INT-6 | Delegation matrix + delegated decision provenance |
| INT-7 | Admin RBAC (requests/delegations 403, template create 201) |
| INT-8 | JSONB condition routing (>= threshold in/out) |

### 3. End-to-end — `autotest/e2e/`

Runner: `./autotest/e2e/run_e2e.sh [--with-agent]` — `docker compose down -v` then
`up --build` (**fresh empty DB**, migration + seed on boot), waits for health, then runs
`e2e_scenarios.py` through the **nginx proxy** exactly like the SPA. `--with-agent` adds
a live-model agent smoke (needs `KIMI_API_KEY`).

| ID | Scenario |
|---|---|
| E2E-1 | Employee request approved through the full chain by manager, finance, vp |
| E2E-2 | Manager request: manager step skipped, finance active |
| E2E-3 | Status feed message "approved by Mark Manager; waiting for finance approval" |
| E2E-4 | Delegation: manager→employee 422, manager→vp 201; VP decides on manager's authority (provenance recorded) |
| E2E-5 | Requester cannot decide their own request (403) |
| E2E-6 | Admin: submit 403, delegate 403, create template 201 |
| E2E-7 | Employee cannot delegate (403) |
| E2E-8 | (optional) Agent answers a status question using the status tool, live model |

### 4. UAT — browser-driven, `autotest/UAT_RESULTS_V2.md`

Fresh stack (`docker compose down -v && up`), Playwright against http://localhost:3000.

| ID | Scenario | Expected |
|---|---|---|
| U1 | Login as each role, inspect sidebar | admin: Templates+Assistant only; employee: Inbox/Requests/Assistant; manager/finance/vp: + Delegations; no Templates for non-admin |
| U2 | Deep-link enforcement | admin →/inbox redirected to /templates; employee →/delegations redirected to /inbox; sarah →/templates redirected |
| U3 | Employee inbox | No "Waiting for your decision" table; "My request status" feed present |
| U4 | Employee submits; approve as manager → finance → vp via inbox UI | Request reaches `approved`; each approver sees it in turn |
| U5 | Status feed updates | After manager approval, Sarah's inbox feed shows "Approved by Mark Manager; waiting for finance approval" |
| U6 | Delegation picker | Manager sees only manager/finance/vp options (no employees); helper text lists allowed roles |
| U7 | Manager-submitted request | Detail page shows Manager approval "skipped by condition/rule", Finance active |
| U8 | Admin templates page | Admin lands on /templates by default and can open the builder |
| U9 | Agent (live): employee asks request status | Reply uses the status-message format |
| U10 | Agent (live): employee asks to delegate | Assistant declines immediately (employee cannot delegate) without executing tools |

## Exit criteria

All four levels green; CI (build + unit tests) green on the PR. Deviations recorded in
`UAT_RESULTS_V2.md` / PR description.
