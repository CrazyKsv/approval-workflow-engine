# UAT Results — Approval Workflow Engine

**Date executed:** 2026-07-02
**Environment:** Docker Compose stack at http://localhost:3000 (fresh seeded PostgreSQL; agent on live Kimi `kimi-k2.6`)
**Method:** Scenarios from `UAT_TEST_PLAN.md` driven through the real UI with Playwright. Setup-only data (C4/C5/D3/E2 request rows, session switches between accounts) was seeded/performed via the public REST API; every behavior under test was exercised and verified in the UI. Evidence screenshots in `screenshots/`.

## Summary

| Suite | Scenarios | Pass | Fail | Findings raised |
|---|---|---|---|---|
| A — Authentication & access | A1–A4 | 4 | 0 | UAT-001 |
| B — Request submission | B1–B3 | 3 | 0 | — |
| C — Inbox & decisions | C1–C5 | 5 | 0 | — |
| D — Detail & audit | D1–D3 | 3 | 0 | UAT-004 |
| E — Delegation | E1–E4 | 4 | 0 | — |
| F — Template admin | F1–F3 | 3 | 0 | — |
| G — AI assistant (live model) | G1–G4 | 4 | 0 | UAT-005 (obs.) |
| H — Deep-link RBAC | H1 | 1 | 0 | UAT-002, UAT-003 |
| **Total** | **20** | **20** | **0** | 3 defects, 2 observations |

**Verdict:** All core flows accepted. No blocking or major defects. Three low/medium findings and two observations logged below — none corrupt data or bypass authorization; server-side enforcement held in every negative test.

## Scenario results

### Suite A — Authentication & access control
- **A1 PASS (with defect UAT-001).** Wrong password on `/login` correctly shows "Invalid email or password" (screenshot `A1-invalid-login-error.png`). However, the *first* attempt — made from `/` — hard-redirected to `/login` and lost the error message (see UAT-001).
- **A2 PASS.** Sarah lands on Approval Inbox; header shows "Sarah Employee" + `employee` tag; sidebar has no "Workflow Templates" item.
- **A3 PASS.** Admin's sidebar includes "Workflow Templates" (verified as Alice Admin).
- **A4 PASS.** Sign out returns to the login page; `/inbox` unreachable without re-login.

### Suite B — Request submission
- **B1 PASS.** Expense $500 → request #1 pending; detail shows "Finance review — skipped by condition", Manager approval active with SLA due date (+48h); audit shows `request submitted (Sarah) → step skipped → step activated`. Screenshot `B1-request-detail-conditional-skip.png`.
- **B2 PASS.** Submitting without the required "Expense category" blocked client-side with "Please enter Expense category"; no request created.
- **B3 PASS.** Expense $2,500 → request #2 with Manager approval active AND Finance review pending (not skipped) — conditional routing correct on both sides of the threshold.

### Suite C — Approval inbox & decisions
- **C1 PASS.** Manager inbox listed both requests with requester, amount, step, "any approver" mode tag, waiting-since, authority `own`. Screenshot `C1-manager-inbox.png`.
- **C2 PASS.** Approve with comment "Looks good" → toast, row left inbox, request #1 `approved`, decision row shows approver + comment.
- **C3 PASS.** After manager approval, #2 appeared in finance1's inbox at "Finance review"; Fiona's single approval completed the request (`any` quorum — Frank still `pending` in the step snapshot).
- **C4 PASS.** Reject with comment → #3 `rejected`; afterwards absent from finance inbox (terminal).
- **C5 PASS.** Request changes with comment → #4 `changes requested`; item left the manager's inbox; comment visible on the detail page.

### Suite D — Request detail & audit
- **D1 PASS.** Step timeline reflects outcomes (Manager ✓, Finance: Fiona approved / Frank pending). Screenshot `D1-D2-request2-approved-audit.png`.
- **D2 PASS.** Audit trail for #2 complete and ordered: `request submitted → step activated → decision approved (Mark) → step completed → step activated → decision approved (Fiona) → step completed → request approved`, all timestamped with actors.
- **D3 PASS.** Cancel via detail page confirm dialog → #5 `cancelled`, removed from manager's inbox.

### Suite E — Delegation
- **E1 PASS.** Delegation created via UI form (Mark → Mike, Jul 1–9, reason "UAT-E1 vacation"), status "active now".
- **E2 PASS.** Mike's inbox showed the delegated items tagged **for Mark Manager**. Screenshot `E2-mike-delegated-inbox.png`.
- **E3 PASS.** Decision modal warned "You are acting on behalf of Mark Manager (delegated)"; after approval, #6 `approved` and the decision row reads **"Mike Employee (for Mark Manager)"** — actor vs. authority provenance preserved.
- **E4 PASS.** After revocation (status `revoked`), Mike's inbox emptied while the manager still saw the remaining pending item. *Deviation:* the still-pending `UAT-D3` request was used as the probe instead of submitting a new `UAT-E4` request — equivalent coverage.

### Suite F — Workflow template administration
- **F1 PASS.** Seeded templates listed; Purchase Order expands to `Manager (role, any, SLA 48h) → Finance Team (group, all, if amount > 5000) → VP (role, any, if amount > 10000, SLA 72h)`.
- **F2 PASS.** Created "UAT-F2 Contract Approval" through the builder (number field `contract_value` required; step 2 with condition `contract_value > 50000`, SLA 24h, escalate to admin). Persisted definition verified via API — matches input exactly. Sarah's New Request dropdown offered it and rendered the "Contract value" field.
- **F3 PASS.** Toggled inactive → no longer offered to employees for new requests.

### Suite G — AI assistant (live Kimi `kimi-k2.6`)
- **G1 PASS.** "$5,000 laptop purchase from Apple" → assistant picked Purchase Order, presented a summary, and asked to confirm. **Server-side gate verified:** no request existed in the DB at that point. After "yes" → request #7 created, pending at Manager approval. Tool trace visible in chat (`list_workflow_templates`, `submit_request` with `confirmation_required`, then `submitted`). Screenshots `G1-agent-confirmation-gate.png`, `G1-agent-submitted.png`.
- **G2 PASS.** Manager asked "What requests are waiting for my approval?" → accurate summary (requester, $5,000, current step, waiting time).
- **G3 PASS.** "Approve Sarah's laptop purchase request." → assistant fetched details, presented context, required confirmation; after "yes" the request became `approved`. Audit shows `request_submitted — Sarah Employee` and `decision_approved — Mark Manager`: agent actions are attributed to the real users.
- **G4 PASS.** Sarah asking to create a template was blocked by server-side RBAC (`PermissionDeniedError` visible as an error-tagged tool call); the assistant explained only admins can do this. No template was created (verified against the full template list).

### Suite H — Deep-link RBAC
- **H1 PASS on enforcement, with findings.** As Sarah, `/templates` renders via deep link (menu correctly hides it). Read access to templates is by design (employees need them to submit). All mutation attempts fail server-side: the active-toggle PATCH returned **403** and state was unchanged. UI hardening gaps recorded as UAT-002/UAT-003.

## Findings

| ID | Severity | Area | Description | Recommendation |
|---|---|---|---|---|
| UAT-001 | Minor (UX) | Login | Submitting invalid credentials from any path other than `/login` (e.g. first load at `/`) triggers the axios 401 interceptor's hard redirect to `/login`, wiping the "Invalid email or password" alert. Retry on `/login` shows it correctly. | Exclude the login request (or all `/auth/login` responses) from the 401-redirect interceptor. |
| UAT-002 | Low (hardening) | RBAC / routing | `/templates` route is not role-gated client-side: non-admins reaching it by deep link see admin controls ("New Template", active toggles). Server rejects every mutation with 403, so it is cosmetic, but it invites confusion. | Add a route guard (redirect non-admins) or render read-only without admin controls. |
| UAT-003 | Low (UX) | Templates page | The template active/inactive toggle has no error handling — when the PATCH fails (e.g. 403, network), the user gets no toast; the failure is visible only in the console and the switch state silently reverts on reload. | Add `.catch` with `message.error` (same pattern as other pages). |
| UAT-004 | **Medium (feature gap)** | Changes-requested loop | A requester cannot resubmit a `changes_requested` request from the UI: the detail page offers only "Cancel request", and the assistant has no resubmit tool. Backend `POST /api/requests/{id}/resubmit` exists and is unit-tested, so the loop is closeable only via raw API. | Add a "Edit & resubmit" action on the detail page for the requester (pre-filled form → resubmit), and optionally a `resubmit_request` agent tool. |
| UAT-005 | Observation | Agent UX | In G4 the assistant gathered template details across two turns before the tool's RBAC check rejected the action. Enforcement is server-side and held; but the assistant already knows the user's role from its system prompt and could decline admin-only requests immediately. | Strengthen the system prompt: "if the user asks for an admin-only action and is not admin, say so before gathering details." |

### Automation notes (not product defects)

- antd Select/Modal interactions occasionally ignored the first synthetic event; real pointer clicks (or a retried click) always succeeded. Two decision-modal opens needed a retry.
- Session switches between test accounts were done by token injection after Suite A validated the real login/logout flows end-to-end.

## Coverage vs. plan

All 20 planned scenarios executed. Items declared out of scope in the plan (SLA escalation timing, `all`-quorum via UI, API pagination limits) remain covered by the backend test suite (43 tests, all passing).

## Data left in the system

Requests #1–#7 (`UAT-B1/B3/C4/C5/D3/E2` + agent-created "Apple Laptop Purchase"), one revoked delegation, one inactive template "UAT-F2 Contract Approval", and several agent conversations. Reset with `docker compose down -v && docker compose up -d` if a clean slate is needed.
