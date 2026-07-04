# UAT Results — AI-Assistant-Only Full Run (2026-07-03)

**Run type:** Fresh-DB UAT where **every role performs its actions solely through the AI
Assistant** (no manual UI forms), plus verification that **conversation history is
retrievable for the record**.
**Driver:** Claude-in-Chrome against the real SPA at http://localhost:3000 with the live
Kimi `kimi-k2.6` agent.
**Branch:** `feature/agent-conversation-history`
**Screenshots:** `autotest/2026-07-03-agent-screenshot/<case>.png`.

## What changed on this branch

- **Investigation:** the backend **already** persisted every conversation and tool trace
  (`agent_conversations` / `agent_messages`) and exposed `GET /agent/conversations` and
  `GET /agent/conversations/{id}` (owner-scoped; admins may read any). The **frontend did
  not surface it** — the Assistant page could only continue the live chat.
- **Implementation:** added a **Conversation History** drawer to the Assistant page
  (`frontend/src/pages/ChatPage.tsx` + `api.ts` types). It lists a user's past
  conversations and reopens any as a full transcript (messages + tool traces), with the
  option to continue it. Added backend tests for the list endpoint and RBAC scoping
  (`backend/tests/test_agent.py`).
- **Tests:** backend unit suite green (**11** agent tests incl. 3 new; 70 total in the
  container after copying the updated file — see note); frontend `tsc -b && vite build`
  green.

## Clean-state verification

`docker compose down -v && up --build` → empty DB, migration + seed on boot. Before the run:
7 users, 3 templates, **0** requests / delegations / conversations.

## Result summary — 10/10 PASS

| ID | Role | Action via assistant | Result | Screenshot |
|---|---|---|---|---|
| AG1 | admin | Create workflow template (confirm gate) | ✅ Template #4 "AI Travel Reimbursement" created (manager→finance→vp) | `AG1-admin-create-template.png` |
| AG2 | employee | Submit request against the new template | ✅ Request #1 created, chain at Manager | `AG2-employee-submit-request.png` |
| AG3 | manager | List pending, then approve | ✅ Approved; advanced to Finance | `AG3-manager-approve.png` |
| AG4 | manager | Delegate authority to Fiona (Jul 5–12) | ✅ Delegation #1 created | `AG4-manager-delegate.png` |
| AG5 | finance | Approve pending request | ✅ Approved; advanced to VP | `AG5-finance-approve.png` |
| AG6 | vp | Approve request | ✅ **Fully approved** | `AG6-vp-approve-final.png` |
| AG7 | employee | Ask request status | ✅ "fully approved (by Mark Manager, Fiona Finance, Victoria VP)" | `AG7-employee-status.png` |
| AG8 | employee | Open History, reopen a past conversation | ✅ 3 conversations listed; transcript + tool traces retrieved | `AG8-history-list.png`, `AG8-history-reopened-transcript.png` |
| AG9 | admin (neg.) | Submit a request | ✅ Refused — admins only manage templates | `AG9-admin-submit-refused.png` |
| AG10 | employee (neg.) | Delegate approvals | ✅ Refused — employees cannot delegate | `AG10-employee-delegate-refused.png` |

## The whole approval lifecycle was assistant-driven

A single request went end-to-end **entirely through the assistant**, one role per turn.
DB after the run:

```
request #1 "AI Travel Reimbursement - Chicago"  status = approved
  step 1 Manager Approval  approved   (decision: Mark Manager)
  step 2 Finance Approval  approved   (decision: Fiona Finance)
  step 3 VP Approval       approved   (decision: Victoria VP)
templates = 4   (3 seeded + 1 created by admin via the assistant)
delegations = 1 (Mark Manager → Fiona Finance, created by manager via the assistant)
conversations = 9,  agent_messages = 74   (full traces persisted)
```

This demonstrates the assistant is a full peer of the manual UI for every role's permitted
actions, and blocks the actions each role may **not** perform (AG9, AG10).

## Confirmation contract

Every mutating action (create template, submit, approve, delegate) went through the
**server-side confirmation gate**: the first tool call returned `confirmation_required`
with a human-readable summary, and the action executed only after the user replied "yes"
and the model re-called with `confirmed=true`. Read-only asks (status, pending list) ran
without a gate. Verified visually and in the DB (no row created before confirmation).

## Conversation history retrievability (the explicit requirement)

- **Now supported.** Backend already stored full transcripts; this branch adds the
  **History** UI so users can retrieve them.
- AG8: Sarah's three past conversations were listed (titled by first message, newest first,
  with "Updated" timestamps). Reopening the "submit request" conversation reconstructed the
  full transcript — both user turns, both assistant replies, and the expandable tool traces
  (`list_workflow_templates`, `submit_request` with args/results/latency) — under a
  "Viewing a saved conversation" banner, with the option to continue it.
- RBAC (unit-tested): a conversation is readable by its owner and by admins (for records),
  and returns 403 to any other regular user; unknown ids return 404.

## Deviations / notes

- Screenshots are stored under `autotest/2026-07-03-agent-screenshot/` (distinct from the
  earlier manual-UI run's `2026-07-03-screenshot/`) so the two suites don't collide.
- The persisted-token convenience: because the dev JWT secret is stable, a prior admin
  token survived the DB wipe; each role was re-authenticated explicitly via the login form
  before its scenarios, and the logged-in identity was asserted from the JWT/header each
  time.
- Backend tests: the running container image is built at image time (tests dir not mounted),
  so the 3 new tests were validated by copying the updated `test_agent.py` into the
  container and running pytest (11 agent tests pass); a rebuild bakes them in for CI.
