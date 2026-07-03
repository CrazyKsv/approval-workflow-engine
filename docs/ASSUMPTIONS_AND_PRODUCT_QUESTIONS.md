# Project Assumptions & Open Product Questions

**Purpose:** The current system was built from the case study PDF only; where the PDF was
silent we made judgment calls. This doc lists, per area, exactly what we assumed and built,
and the questions product needs to answer before we invest in the next iteration.

**How to read priorities:**

- **[P1]** — answer changes the data model or a core flow; blocking for next steps
- **[P2]** — answer changes behavior/UX but is locally contained
- **[P3]** — nice to clarify; we can proceed on the current assumption

A one-page shortlist for the meeting is at the [bottom](#meeting-shortlist-if-time-is-tight).

---

## 1. Roles & permissions

### As built (assumptions)

- Flat, fixed role set: `admin`, `manager`, `finance`, `vp`, `employee`. **One role per
  user**, no hierarchy, no departments, no reporting lines.
- A "role" approver step resolves to **every active user with that role company-wide**
  (e.g. "Manager approval" = _any_ manager, not _the requester's_ manager).
- Any user can submit a request against any active template.
- The requester is excluded from approving their own request — **unless they are the only
  resolvable approver, in which case they are allowed** (fallback to avoid dead ends).
- Visibility: requester sees own requests; approvers (incl. delegates) see requests
  assigned to them; admin sees everything. Per-request audit follows the same rule;
  the global audit feed is admin-only.
- Only `admin` creates/deactivates workflow templates.
- Every authenticated user can list the full user/group directory (names, emails, roles) —
  needed for delegation and template pickers.
- Auth is local email/password + JWT with seeded users (SSO assumed to come later).

### Questions

1. **[P1] Approver semantics for roles:** is "Manager approval" _any_ manager, or the
   requester's _own_ manager? If the latter, we need org structure (reporting lines) in
   the data model — biggest potential schema change on the list. Same question for
   department-scoped finance teams.
2. **[P1] Role model:** single role per user enough, or do people hold multiple roles
   (e.g. a VP who is also a people manager)? Do we need custom/tenant-defined roles, or
   is a fixed set fine for v1?
3. **[P2] Self-approval:** is the "requester may approve if they're the only possible
   approver" fallback acceptable, or should the request instead escalate / go to admin /
   fail loudly?
4. **[P2] Visibility:** should a manager see all of their reports' requests (not just
   ones they approve)? Should finance see all requests with an amount? Who besides admin
   needs the global audit view (compliance/auditor role)?
5. **[P2] Template administration:** admin-only today. Should department heads or a
   dedicated "workflow designer" role manage their own templates?
6. **[P3] Directory exposure:** is it OK that every employee can enumerate all users'
   names/emails/roles, or should the directory be scoped?
7. **[P3] Submitter restrictions:** should templates restrict who can submit (e.g. only
   managers can raise Purchase Orders)? Today anyone can submit anything.

## 2. Requests & routing lifecycle

### As built (assumptions)

- Request = title, description, optional first-class `amount`, plus arbitrary
  template-defined fields. Single implicit currency (USD). No attachments.
- **Routing is decided once, at submission**: each step's condition is evaluated against
  the request data; non-matching steps are recorded as `skipped by condition`. Changing
  data later never re-routes (except via explicit resubmission).
- Decisions: `approve` / `reject` / `request changes`.
  - **Reject is terminal** — no appeal, no resubmit; requester must file a new request.
  - **Request changes** → requester edits and resubmits → **routing restarts from step 1
    and all prior approvals are discarded**.
- Requester (or admin) can cancel while `pending` or `changes_requested` — including
  after some steps were already approved.
- A pending request cannot be edited (only cancel, or wait for changes-requested).
- Thresholds in the seeded templates use **strict `>`** (a $5,000 request does _not_
  trigger the "over $5,000" finance step). Engine supports `>=`; it's a template choice.
- No duplicate detection; identical requests can be submitted repeatedly.

### Questions

8. **[P1] Resubmission semantics:** after "request changes", should routing restart from
   step 1 (current), resume at the step that requested changes, or keep prior approvals
   if the data changes are "minor"? If approvals survive, what invalidates them (e.g.
   amount increased)?
9. **[P2] Boundary amounts:** should "over $X" thresholds be inclusive (`>=`)? Found in
   UAT: a request of exactly $5,000 skips finance review — boundary-priced requests are a
   classic dodge. One-line change per template once product decides.
10. **[P2] Reject flow:** is terminal-reject right, or should rejected requests be
    resubmittable like changes-requested ones? What's the intended difference between
    "reject" and "request changes" from the approver's point of view?
11. **[P2] Cancel rules:** may a requester cancel after partial approvals without any
    approver acknowledgment? Should cancel require a reason?
12. **[P2] Re-routing on data change:** if a template is only conditionally routed at
    submission, is it acceptable that a request whose _data_ is edited on resubmit gets
    fully re-evaluated (current), and that nothing else ever re-evaluates routing?
13. **[P3] Attachments:** are receipts/quotes/documents required for expense/PO flows
    (storage + virus scanning implications)?
14. **[P3] Currency:** single currency OK for v1, or multi-currency with conversion for
    threshold evaluation?

## 3. Workflow templates

### As built (assumptions)

- Templates are a **linear ordered list of steps**. Parallelism exists only _within_ a
  step (multiple resolved approvers with `any` / `all` quorum). No branching
  ("if X then step A else step B"), no parallel step groups, no loops.
- Step condition = single `field op value` clause (`==`, `!=`, `>`, `>=`, `<`, `<=`,
  `in`, `not_in`, `contains`). **No AND/OR composition.**
- Quorum is `any` (one approval completes step) or `all` (everyone must approve).
  No "2 of 5".
- Approver targets: specific user, group, or role. **Groups exist but have no management
  UI/API — membership is seed-data only.**
- Approvers are resolved (snapshot) when a step activates, so role/group changes apply to
  future activations, not active steps.
- Template editing = deactivate + create new. A `version` column exists but there is no
  version-bump flow. In-flight requests keep their original step definitions.
- **Escalation:** each step may have `sla_hours` + an escalation target (user or role).
  On breach, the target is **added as an extra approver** (originals keep authority), and
  an escalation approver's approval **overrides `all` quorum**. One escalation level; a
  60s in-process sweep checks breaches. No notifications of any kind.

### Questions

15. **[P1] Routing expressiveness:** are linear steps with per-step conditions enough for
    the target use cases, or do real customers need branching / parallel step groups /
    compound (AND/OR) conditions? This decides whether the step model needs redesign now
    or later.
16. **[P1] Escalation semantics:** on SLA breach, should we (a) add the escalation target
    as an extra approver (current), (b) _reassign_ away from the original approvers,
    (c) notify only, or (d) auto-approve/auto-reject after a grace period? Is multi-level
    escalation (manager → VP → CFO) needed? Should escalation approval really override an
    `all` quorum (current)?
17. **[P2] Quorum:** is "any / all" sufficient, or is "N of M" required?
18. **[P2] Group management:** who owns approver groups and where are they managed —
    admin UI in our product (needs new CRUD APIs), or synced from an IdP/HR system
    (SCIM/HRIS integration)?
19. **[P2] Template versioning:** what should editing a live template do — new version
    with in-flight requests finishing on the old one (current behavior, implicit)?
    Migrate in-flight requests? Block edits while requests are in flight?
20. **[P3] Template lifecycle:** deactivate is our only lifecycle control. Need
    draft/published states, testing/sandbox mode, or approval-of-templates
    (who reviews a new workflow before it goes live)?

## 4. Delegation

### As built (assumptions)

- Delegation = **whole authority**: the delegate can act on _everything_ the delegator
  can approve during the window. No scoping by template, amount, or category.
- Time-boxed (start/end), revocable by delegator or admin; any user may delegate to any
  other active user (even users with nothing to delegate).
- Resolved at **decision time**, so a delegation created after a step activates still
  applies. Delegator keeps their own authority in parallel.
- Decisions record both the authority (`approver`) and the actual actor (`acting user`);
  inbox and decision UI label items "for <delegator>".
- **No chaining:** if A delegates to B and B delegates to C, C does _not_ get A's
  authority.
- Overlapping/multiple simultaneous delegations allowed; no notification to the delegate.

### Questions

21. **[P1] Known gap — self-approval via delegation:** we found that if a manager
    delegates to an employee, that employee **can approve their own request** using the
    delegated authority (the self-approval exclusion only applies to directly-assigned
    approvers). We assume this must be blocked — confirm, and confirm the broader rule:
    can an _acting user_ ever equal the requester?
22. **[P1] Delegation scope:** is whole-authority delegation acceptable, or does product
    need scoping (only Expense Reports, only up to $10k, only specific templates)? This
    changes the delegation data model.
23. **[P2] Who may receive delegation:** any employee (current), same-role-or-above only,
    or an allowlist? E.g. is a manager delegating approvals to a junior employee OK?
24. **[P2] Chaining & coverage:** is no-chaining correct? And should the _delegator_ stop
    receiving items while a delegation is active (true out-of-office), or keep parallel
    authority (current)?
25. **[P3] Approval-required delegation:** does creating a delegation itself need
    approval (e.g. by the delegator's manager) or notification to anyone?

## 5. AI agent

### As built (assumptions)

- Assistant = Kimi `kimi-k2.6` via OpenAI-compatible tool calling; 10 tools that hit the
  **same service layer as the REST API under the authenticated user** — the agent can
  never do more than the user could via the UI.
- **Server-enforced confirmation** for the four mutating tools (submit, decide, create
  delegation, create template): the first call physically cannot write; the model must
  present a summary and the user must confirm in chat ("yes") before the tool executes.
- Read tools (inbox, request details, audit, directory, templates) execute freely without
  confirmation.
- The agent has **no tool** for: resubmit, cancel, revoking delegations, or
  activating/deactivating templates — those are UI-only today (resubmit is API-only).
- Full tool trace (tool name, arguments, results, latency, errors) is stored per
  conversation and **shown to the end user in the chat UI**; admins can view any user's
  conversation via API. Conversations are retained indefinitely.
- Failure handling: 3 retries with backoff on model errors, then a graceful "service
  unavailable, nothing changed" reply. No per-user rate limits or token/cost budgets.
- English-only, non-streaming responses, ~40-message context window per conversation.

### Questions

26. **[P1] Confirmation policy:** is a chat "yes" sufficient authorization for an
    approval decision (compliance/SOX view)? Do high-value actions need a stronger
    ceremony — explicit in-UI confirm button, re-auth, or amount thresholds above which
    the agent must hand off to the UI instead of executing?
27. **[P1] Agent action surface:** which actions _should_ the agent be able to perform
    vs. read-only assist? Specifically: should it decide requests at all, should admins
    be able to create templates through chat (works today), and should we add the missing
    resubmit/cancel/revoke tools?
28. **[P2] Privacy & retention:** admins can read every user's conversations (built for
    observability). Is that acceptable? What's the retention policy for conversations and
    tool traces (they can contain request data/PII)?
29. **[P2] Cost & abuse controls:** what are acceptable per-user/per-day limits on agent
    usage (rate limits, token budgets)? None exist today.
30. **[P2] Wrong-narrative risk:** the model occasionally narrates routing slightly wrong
    (e.g. claimed a $5,000 request would go to finance when the engine correctly skipped
    it). Engine behavior is always authoritative, but is that error rate acceptable, or
    should replies embed only engine-computed routing facts (more templated, less
    fluent)?
31. **[P3] Model strategy:** is Kimi fixed (procurement/data-residency), or should the
    model layer stay swappable? Any requirement that request data must not leave certain
    regions (Moonshot API is external)?
32. **[P3] Channels & languages:** is in-app chat the only surface, or is Slack/Teams/
    email integration expected? English-only OK for v1?

## 6. Cross-cutting (quick answers welcome)

33. **[P1] Notifications:** there are none — no email/Slack on assignment, escalation, or
    decision; approvers must poll their inbox. What events must notify, on which
    channels? (The audit log is already the event source we'd hook into.)
34. **[P2] Tenancy:** single organization assumed everywhere. Is multi-tenant SaaS on the
    roadmap (affects every table and every query)?
35. **[P2] Compliance:** audit log is append-only rows in the app DB. Any requirement for
    tamper-evidence, export (SIEM), or retention duration?
36. **[P3] Identity:** confirm SSO/OIDC provider for production and where roles/groups
    come from (IdP claims vs. managed in-app).

---

## Known gaps already found (need a product decision, then we fix)

| #   | Item                                                                                                          | Severity | Related question |
| --- | ------------------------------------------------------------------------------------------------------------- | -------- | ---------------- |
| 1   | Self-approval possible via delegation (employee approves own request on delegated authority)                  | High     | Q21              |
| 2   | `changes_requested` loop can't be closed in UI or agent (resubmit is API-only) — UAT-004                      | Medium   | Q8, Q27          |
| 3   | Strict `>` thresholds let boundary amounts ($5,000 exactly) skip review                                       | Medium   | Q9               |
| 4   | No group management (seed-only membership)                                                                    | Medium   | Q18              |
| 5   | No notifications of any kind                                                                                  | Medium   | Q33              |
| 6   | `/templates` page reachable by non-admins via deep link (server blocks all mutations; cosmetic) — UAT-002/003 | Low      | Q5               |
| 7   | Login error message swallowed on first attempt from `/` — UAT-001                                             | Low      | —                |

## Meeting shortlist (if time is tight)

The seven answers that most change what we build next. Each comes with a concrete
scenario using the demo cast (**Sarah** = employee, **Mark** = manager, **Fiona &
Frank** = Finance Team, **Victoria** = VP; **Dana** stands in for a second manager the
moment one is hired — the demo seed has only Mark).

### 1. Who is "the manager" in a Manager approval step? (Q1)

**Today:** Sarah submits a $500 expense. The "Manager approval" step assigns **every
manager in the company** — Dana, who has never met Sarah and runs an unrelated team, can
approve it. First one to act wins.

**Ask:** Is "any manager" acceptable, or must it be _Sarah's_ manager?

- Org structure (no needed, )

- **A. Any manager (current)** — no change.
- **B. Requester's manager** — we must add reporting lines (`manager_id` on users, HR
  sync question). Biggest schema change on the table; want this answered first.
- **C. Manager within the requester's department** — needs departments + membership.

### 2. What does resubmission do to approvals already given? (Q8)

**Today:** Sarah's $2,500 travel expense: Mark approves (step 1) → Fiona requests changes
at Finance review ("attach a quote"). Sarah attaches it and resubmits → **routing
restarts from step 1, Mark's approval is discarded, and Mark must approve the same
request a second time** before Fiona even sees the quote.

**Ask:** Is re-approving intended, or annoying overhead?

- **A. Restart from step 1 (current)** — safest, most redundant.
- **B. Resume at the step that requested changes** — Mark's approval survives; small
  engine change.
- **C. Keep approvals unless "material" fields changed** (e.g. amount ↑) — needs a
  definition of _material_ per template; medium effort.

### 3. Is linear routing expressive enough? (Q15)

**Today we can express:** Manager → Finance (only if amount > $5,000) → VP (only if
amount > $10,000) — a straight line where steps can be skipped.

**We cannot express:** "if amount > $10k **AND** category = software → add CISO review",
"Legal **and** Finance review **in parallel**, then VP", or "2 of the 5 directors".

**Ask:** Do any near-term customer workflows need branching, parallel step groups,
compound (AND/OR) conditions, or N-of-M quorum? A yes on any of these means redesigning
the step model _now_ rather than retrofitting later.

### 4. What should an SLA breach actually do? (Q16)

**Today:** A $6,000 PO sits at "Finance review — all must approve" for 24h. Escalation
**adds Victoria (VP) as an extra approver**, and **her single approval completes the
step even though Fiona and Frank were both required**. Fiona and Frank keep their
authority; nobody is notified at any point.

**Ask:** Which behavior is intended on breach?

- **A. Add escalation approver whose approval overrides quorum (current).**
- **B. Reassign** — original approvers lose the item.
- **C. Notify/remind only** — no authority change (requires notifications, see #7).
- **D. Auto-decide** after a grace period. Also: is one escalation level enough, or is a
  chain (manager → VP → CFO) needed?

### 5. Delegation: block self-approval, and how wide is the grant? (Q21/Q22)

**Today (confirmed bug-level gap):** Mark delegates to Sarah for his vacation. Sarah
submits a $5,000 laptop request → **Sarah can approve her own request** "on behalf of
Mark". The self-approval guard only covers directly-assigned approvers, not delegates.
We assume this must be blocked — please confirm the rule.

**Also:** delegation is all-or-nothing. Mark's delegation to Mike (a junior employee)
hands over **everything** Mark can approve — including a $50,000 PO — with no template,
amount, or role restriction.

**Ask:** (a) Can an acting user ever equal the requester? (b) Do we need scoped
delegation (per template / amount cap) and rules on who may receive it? Scoping changes
the delegation data model.

### 6. Is typing "yes" in chat enough to approve money? (Q26/Q27)

**Today:** Mark tells the assistant "Approve Sarah's laptop purchase", the assistant
shows the context, Mark types **"yes"**, and a $5,000 decision is executed — same
server-side authority as the UI, fully audited, but the entire ceremony is two words in
a chat box. There is no amount limit: "yes" would equally approve a $500,000 PO.

**Ask:** For compliance, what must "confirmation" mean?

- **A. Chat confirmation is fine (current)** at any amount.
- **B. Threshold** — above $X the agent presents a deep link and the decision must be
  clicked in the UI.
- **C. Agent is read-only for decisions** — it summarizes and links, never executes.
  Also: should the agent get the missing resubmit/cancel tools, and should admins be
  able to create workflow templates via chat (works today)?

### 7. Which events must notify people, and where? (Q33)

**Today:** zero notifications. Fiona only discovers a pending Finance review if she opens
her inbox; Sarah only learns her request was approved by checking its page; an SLA breach
silently adds an approver (see #4). A request can sit for days with no one aware.

**Ask:** For v1, which of these events need email and/or Slack: step assigned to you /
decision made on your request / changes requested / SLA breach & escalation / delegation
granted to you? (The audit log already emits all of these as rows, so this is
integration work, not engine work — but channel and event list decide its size.)
