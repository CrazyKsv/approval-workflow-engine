# SOLUTION.md

What was built, why it was built that way, and what I'd change for production.
Companion to [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (full design) and
[README.md](README.md) (setup).

## What was delivered

| Case study part | Delivered |
|---|---|
| Part 1 — Data model | 14-table schema (templates → steps → instances → resolved approvers → decisions, plus delegations, audit log, agent conversations). Alembic migration + rendered DDL in `docs/schema.sql`. Supports conditional routing, parallel `any`/`all` group approvals, role-based approvers, SLA escalation. |
| Part 2 — APIs | JWT-authenticated REST API: workflow admin, request submission, approval inbox (incl. delegated authority), decisions, delegation management, audit, directory. Pagination on all lists, uniform error shape, OpenAPI docs at `/docs`. |
| Part 3 — Agent | `POST /api/agent/chat`: multi-turn assistant on Kimi `kimi-k2.6` with 10 tools, server-enforced confirmation for mutating actions, per-invocation tracing, retry with backoff. React chat UI shows the tool trace inline. |
| Tests | 43 pytest tests: engine unit tests, API/RBAC tests, agent tests incl. a full multi-turn conversation with the confirmation gate (scripted fake LLM for determinism). |
| Frontend (bonus) | React + AntD SPA: inbox, request submission/detail with step timeline + audit, template builder, delegations, chat. |

## Architecture decisions

1. **Custom mini-engine instead of Temporal/Camunda.** Part 1 asks for the schema design
   itself; an external BPM engine would outsource the core of the exercise, split the
   audit trail, and add heavy infrastructure. The routing logic is ~250 lines and fully
   unit-tested.
2. **PostgreSQL.** Approval data is relational and needs transactional integrity for
   concurrent decisions; JSONB gives flexibility for per-template fields and conditions.
3. **Single choke point for state changes.** REST routers and agent tools both call the
   same service layer, which does authorization and writes audit entries. The agent
   cannot do anything a user couldn't do with curl — prompt injection cannot escalate
   privileges because the model never touches the DB.
4. **Approvers snapshotted at activation; delegation resolved at decision time.**
   Snapshotting makes "who could approve and why" auditable even if groups change later;
   decision-time delegation means a delegation created after a step activates still
   works. Decisions record both the authority (`approver_id`) and the actual actor
   (`acting_user_id`).
5. **Server-enforced confirmation for irreversible actions.** Mutating tools called
   without `confirmed: true` return a summary and instruction instead of executing.
   Safety does not depend on the model "remembering" to ask — the first call physically
   cannot write.
6. **Conditions evaluated at submission.** Routing is deterministic and auditable
   (skipped steps appear in the trail with the condition that skipped them). Re-routing
   happens only on explicit resubmission after "changes requested".

## Third-party leverage

- **`openai` SDK against Moonshot's OpenAI-compatible endpoint** — chat + native tool
  calling with zero custom HTTP code; the single biggest code saver.
- **FastAPI** — validation (Pydantic) and OpenAPI documentation for free.
- **SQLAlchemy + Alembic** — portable models (Postgres in prod, SQLite in tests) and
  migrations.
- **tenacity** — declarative retry/backoff for model calls.
- **Ant Design** — inbox tables, dynamic forms, timelines, chat UI mostly from
  components.
- Deliberately avoided: LangChain/LangGraph (a transparent ~150-line loop beats a
  framework here, and observability/authz stay explicit), fastapi-users (auth scope
  larger than needed).

## AI usage

- **In the product**: Kimi `kimi-k2.6` with function calling. System prompt carries the
  user's identity/role and safety rules; tools are strict JSON schemas; every model step
  and tool invocation is persisted (`agent_messages`) with args, result, latency, error.
- **In development**: built with Claude Code (AI pair). The end-to-end agent flows in
  `docs/example_conversations.md` are real transcripts from the running system, verified
  during development (including a real model quirk discovered by testing: `kimi-k2.6`
  rejects non-default `temperature`, so none is sent).

## Tradeoffs (accepted for the case study)

- **Escalation via in-process asyncio sweep** (60s interval) — production: a scheduler
  (Celery beat, pg_cron, k8s CronJob); the sweep is one isolated function so the swap is local.
- **Sync SQLAlchemy in FastAPI's threadpool** — simpler than async ORM; fine at this
  scale; endpoints are thin so migration later is mechanical.
- **JWT + seeded users** — production: SSO/OIDC, refresh tokens, secret rotation. RBAC
  checks are centralized in the service layer already.
- **Baseline migration materializes the models** (`create_all`) with `docs/schema.sql`
  as the reviewable DDL — subsequent migrations would be autogenerated diffs.
- **Template versioning is minimal** (a `version` column, deactivate-and-replace):
  instances denormalize step name/mode so history stays correct if a template changes.
- **In-memory pagination for the inbox** (result sets are small per user); other lists
  paginate in SQL.

## Production-readiness checklist (what I'd do next)

1. **Concurrency**: row-level locking (`SELECT … FOR UPDATE`) on step instances so two
   simultaneous decisions on the same step serialize cleanly (SQLite tests can't express
   this; Postgres supports it directly).
2. **Observability**: OpenTelemetry traces around model/tool calls, metrics
   (decision latency, escalation counts, token usage), structured JSON logs; the
   conversation trace tables already provide the data model.
3. **Security hardening**: rate limiting on `/agent/chat`, token budget per
   conversation, prompt-injection red-teaming (mitigated structurally by service-layer
   authz), secret management (Vault/SSM), HTTPS everywhere.
4. **Notifications**: email/Slack on step activation, escalation and decisions
   (audit log is already the event source to hook into).
5. **Streaming agent responses** (SSE) for perceived latency; the loop is already
   iteration-based so streaming slots in at the completion call.
6. **Group/org management APIs**, template edit-as-new-version flow, and soft-delete
   with retention policies for compliance.

## Lessons learned

- **Test against the real model early.** The `temperature` rejection by `kimi-k2.6`
  surfaced only in live testing; everything else had been green under the fake client.
- **Confirmation as a server contract, not a prompt guideline**, made agent safety
  testable: there is a unit test proving nothing is written before the user confirms.
- **Letting REST and the agent share one service layer** meant the agent got
  authorization, validation and audit "for free" — the agent layer stayed ~500 lines
  including all tool schemas.
- Resolving delegation at decision time (rather than copying approver rows at
  activation) removed a whole class of quorum edge cases in `all` mode.
