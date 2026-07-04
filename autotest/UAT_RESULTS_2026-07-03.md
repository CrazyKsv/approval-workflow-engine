# UAT Results — Fresh-Data Full Regression (2026-07-03)

**Run type:** Full UAT regression from a wiped database (`docker compose down -v` → `up`;
migration + seed on boot, **no user data**).
**Driver:** Claude-in-Chrome browser automation (real SPA at http://localhost:3000), not Playwright.
**Branch under test:** `feature/role-flow-clarifications`
**Screenshots:** `autotest/2026-07-03-screenshot/<case>.png` (one per case).

## Environment / clean-state verification

| Item | Value |
|---|---|
| Backend / DB | FastAPI + PostgreSQL (Docker), Alembic migration + seed on boot |
| Agent | Kimi `kimi-k2.6` via `https://api.moonshot.ai/v1` (`KIMI_API_KEY` set) |
| Seeded on boot | 7 users, 1 group, 3 templates (all manager→finance→vp chain) |
| Business data at start | **0** requests, **0** delegations, **0** conversations (true clean state) |

Demo accounts (password `password123`): `admin@acme.com` (Alice Admin), `manager@acme.com`
(Mark Manager), `finance1@acme.com` (Fiona Finance), `finance2@acme.com` (Frank Finance),
`vp@acme.com` (Victoria VP), `sarah@acme.com` (Sarah Employee), `mike@acme.com` (Mike Employee).

## Result summary — 10/10 UAT scenarios PASS (+ A1 regression)

| ID | Scenario | Result | Evidence / screenshot |
|---|---|---|---|
| A1 | Invalid login rejected | ✅ PASS* | Shows "Invalid email or password" on `/login`. `A1-invalid-login.png` |
| U1 | Per-role sidebar | ✅ PASS | `U1-{admin,employee,manager,finance,vp}-menu.png` |
| U2 | Deep-link route guards | ✅ PASS | `U2-admin-deeplink-guard.png`, `U2-employee-deeplink-guard.png` |
| U3 | Employee inbox = status feed only | ✅ PASS | `U3-employee-inbox-feed-only.png` |
| U4 | Employee request → manager→finance→vp via UI | ✅ PASS | `U4-request-chain-submitted.png`, `U4-request-approved-full-chain.png` |
| U5 | Status feed message format | ✅ PASS | `U5-status-feed-message.png` |
| U6 | Delegation picker filtering | ✅ PASS | `U6-delegation-picker-manager.png` |
| U7 | Manager request skips manager step | ✅ PASS | `U7-manager-request-skips-manager.png` |
| U8 | Admin lands on /templates + builder | ✅ PASS | `U8-admin-template-builder.png` |
| U9 | Agent (live) reports request status | ✅ PASS | `U9-agent-request-status.png` |
| U10 | Agent (live) refuses employee delegation | ✅ PASS | `U10-agent-delegation-refusal.png` |

\* A1 passes on its acceptance criterion (bad credentials are rejected with a visible
error). Pre-existing minor UX quirk unchanged by this work — see Deviations.

## Detailed evidence

### U1 — Per-role sidebar (access-control matrix)

Observed menus after login (landing route in parentheses):

| Role | Menu items | Landing |
|---|---|---|
| admin | AI Assistant, Workflow Templates, Sign out | `/templates` |
| employee | Approval Inbox, My Requests, AI Assistant, Sign out | `/inbox` |
| manager | Approval Inbox, My Requests, AI Assistant, Delegations, Sign out | `/inbox` |
| finance | Approval Inbox, My Requests, AI Assistant, Delegations, Sign out | `/inbox` |
| vp | Approval Inbox, My Requests, AI Assistant, Delegations, Sign out | `/inbox` |

Matches the matrix: admin = Templates + Assistant only; employee = Inbox/Requests/Assistant
(no Delegations); manager/finance/vp = + Delegations; Templates never shown to non-admin.

### U2 — Deep-link route guards

- Admin → `/inbox` **redirected to `/templates`**.
- Employee → `/delegations` **redirected to `/inbox`**.
- Employee → `/templates` **redirected to `/inbox`**.

### U3 — Employee inbox

Employee `/inbox` renders only the **"My request status"** feed card; the approver
**"Waiting for your decision"** table is absent. On the clean DB the feed reads
"You have not submitted any requests yet."

### U4 — Employee request through the full chain (UI-driven)

Sarah submitted **#1 "Q3 Conference Travel" ($2,500)** via the New Request form.
- Initial chain: Manager approval **active** (Mark Manager), Finance & VP waiting — none skipped.
- Approved in turn through the UI inbox: **Mark Manager → Fiona Finance → Victoria VP**.
- Final state: status **approved**; all three steps `finish`; decisions logged with actors
  and timestamps. Finance step used `any`-approver mode (one finance approval sufficed).

### U5 — Status feed message format

Sarah's feed after **#3 "Team Lunch Reimbursement"** received only the manager approval:

> **Approved by Mark Manager; waiting for finance approval** — (status: pending)

and the completed **#1** shows:

> **Fully approved (by Mark Manager, Fiona Finance, Victoria VP)** — (status: approved)

Exactly matches the U5 acceptance criterion.

### U6 — Delegation picker filtering (manager)

Modal helper text: **"As manager, you can delegate to: manager, finance, vp"**.
Picker options: Fiona Finance (finance), Frank Finance (finance), Victoria VP (vp).
No employees/admin listed; the only other manager slot is self (excluded).

### U7 — Manager request skips the manager step

Manager submitted **#2 "Standing Desk for Manager" ($800)**. Detail page:
- Manager approval → **"skipped by routing rule"**
- Finance review → **active** (Fiona & Frank pending, any-approver)
- VP sign-off → waiting

Confirms the requester-role skip.

### U8 — Admin templates + builder

Admin default landing is `/templates`. "New Template" opens the **"Create workflow template"**
builder (Name / Category / Description + step editor).

### U9 — Agent (live) request status

As Sarah, asked "Show me the status of my requests." Agent replied (1 tool call):

> "You have one request: **Request #1 "Q3 Conference Travel"** — fully approved
> (by Mark Manager, Fiona Finance, Victoria VP)."

Matches real DB state and the status-message format.

### U10 — Agent (live) refuses employee delegation

As Sarah, asked "Delegate my approvals to Mike for next week." Agent refused immediately,
without executing a delegation tool:

> "You can't delegate approvals because you're an employee. Only managers, finance staff,
> and VPs have approval authority that can be delegated…"

## Deviations / notes

- **A1 (pre-existing, unchanged):** the very first login attempt initiated from the root
  path `/` can briefly swallow the inline error before the app settles on `/login`; the
  error "Invalid email or password" then renders correctly. Cosmetic timing quirk in the
  login redirect, not a regression from this branch, and it does not affect authentication
  (bad credentials are always rejected).
- No functional deviations. All clarified behaviors (chain routing + requester-role skip,
  UI access matrix, delegation matrix, agent role-awareness and status feed) verified
  end-to-end from a clean database through the real UI and the live agent.
