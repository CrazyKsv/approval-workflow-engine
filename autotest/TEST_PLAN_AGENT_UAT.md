# Test Plan — AI-Assistant-Only UAT + Conversation History

**Date:** 2026-07-03
**Branch:** `feature/agent-conversation-history`
**Driver:** Claude-in-Chrome against http://localhost:3000 (real SPA + live Kimi agent).
**Screenshots:** `autotest/2026-07-03-agent-screenshot/<case>.png`.

## Objective

Prove that **every role can perform its allowed actions entirely through the AI Assistant**
(no manual UI forms) — the assistant is a full peer of the manual UI — and that a user's
**conversation history is retrievable for the record**.

## Scope of this change

- **Finding:** the backend already persists every conversation + tool trace
  (`agent_conversations` / `agent_messages`) and exposes `GET /agent/conversations`
  (list, owner-scoped) and `GET /agent/conversations/{id}` (full transcript; owner or admin).
  The **frontend did not surface it** — the Assistant page could only continue the
  in-progress chat.
- **Implementation (this branch):** added a **Conversation History** drawer to the Assistant
  page. It lists a user's past conversations (title + last-updated) and reopens any of them
  as a full read-only transcript (messages + tool traces), with the option to continue it.
  Added `api.ts` types and backend tests for the list endpoint + RBAC scoping.

## Fresh-data requirement

`docker compose down -v && up --build` → empty DB, migration + seed on boot (7 users,
3 templates, **0** business data). Every UAT action below is issued through the assistant chat.

## Accounts (password `password123`)

admin@acme.com (Alice Admin), manager@acme.com (Mark Manager), finance1@acme.com
(Fiona Finance), vp@acme.com (Victoria VP), sarah@acme.com (Sarah Employee), mike@acme.com
(Mike Employee).

## Scenarios

| ID | Role | Ask the assistant to… | Expected |
|---|---|---|---|
| AG1 | admin | Create a workflow template "AI Travel Reimbursement" (amount + destination fields; manager→finance→vp chain) | Confirmation gate shown → after "yes", `create_workflow_template` runs; template created and listed |
| AG2 | employee (Sarah) | Submit a $1,200 "AI Travel Reimbursement" request | Confirmation gate → confirm → request created; chain starts at Manager (no skip) |
| AG3 | manager (Mark) | List what's waiting, then approve Sarah's request | `get_pending_approvals` lists it; confirm → approved; advances to Finance |
| AG4 | manager (Mark) | Delegate approval authority to Fiona Finance for a date window | Confirmation → confirm → `create_delegation` succeeds (allowed by matrix) |
| AG5 | finance (Fiona) | Approve Sarah's request | Confirm → approved; advances to VP |
| AG6 | vp (Victoria) | Approve Sarah's request | Confirm → request **fully approved** |
| AG7 | employee (Sarah) | Report the status of my requests | Status-feed message: fully approved by Mark, Fiona, Victoria |
| AG8 | any (Sarah/admin) | Open **History** drawer and reopen a past conversation | Saved conversations listed; reopening shows the full transcript incl. tool traces |
| AG9 | admin (negative) | Submit an expense request | Refused — admins cannot submit requests (no tool executed) |
| AG10 | employee (negative) | Delegate approvals to someone | Refused — employees have no approval authority to delegate |

## Notes on the confirmation contract

Mutating tools (`submit_request`, `decide_request`, `create_delegation`,
`create_workflow_template`) enforce a **server-side** confirmation gate: the first call
returns `confirmation_required` with a summary; the action only executes after the user
confirms and the model re-calls with `confirmed=true`. UAT verifies the gate appears and the
action lands only after explicit confirmation.

## Exit criteria

AG1–AG8 pass (each role's action completes through the assistant; history is retrievable);
AG9–AG10 correctly refuse. Backend unit tests green (incl. new conversation-history tests);
frontend build green. Results + screenshots recorded in `UAT_RESULTS_AGENT_2026-07-03.md`.
