# Approval Workflow Engine

A generic, reusable approval workflow engine with an **agentic AI assistant** (Kimi
`kimi-k2.6`), built for the [backend engineering case study](docs/Approval_Workflow_Case_Study_Agentic.pdf).

- **Backend**: FastAPI + SQLAlchemy + PostgreSQL (Alembic migrations)
- **Frontend**: React + Vite + Ant Design
- **AI**: Moonshot Kimi via the OpenAI-compatible API, native tool calling
- **Orchestration**: Docker Compose

Key features: dynamic multi-step workflow templates with conditional routing,
group/role/parallel (`any`/`all`) approvals, SLA-based escalation, temporary delegation
of approval authority, a complete audit trail, and a natural-language assistant that
drives everything through authorized, confirmed tool calls.

## Quick start

```bash
cp .env.example .env       # put your Moonshot API key in KIMI_API_KEY
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend (SPA) | http://localhost:3000 |
| API | http://localhost:8000/api |
| Interactive API docs (OpenAPI) | http://localhost:8000/docs |

### Demo accounts (password: `password123`)

| Email | Role |
|---|---|
| admin@acme.com | admin (manages workflow templates) |
| manager@acme.com | manager |
| finance1@acme.com / finance2@acme.com | finance (members of "Finance Team" group) |
| vp@acme.com | vp |
| sarah@acme.com / mike@acme.com | employee |

Three workflows are seeded (**Expense Report**, **Purchase Order**, **Time Off
Request**), all using the standard chain **manager → finance → VP**. The step matching
the requester's own role is skipped automatically (a manager's request starts at
finance). Requesters can never approve their own requests — including via delegation.

**Access control:** admin manages workflow templates only (plus AI assistant);
employees get Inbox/My Requests/Assistant; manager/finance/vp additionally get
Delegations. Delegation follows a role matrix: manager → manager/finance/vp,
finance → finance/vp, vp → finance.

### Try the demo flow

1. Sign in as `sarah@acme.com` → **AI Assistant** → "I need approval for a $5,000
   laptop purchase" → confirm when asked.
2. Sign in as `manager@acme.com` → "What requests are waiting for my approval?" →
   "Approve Sarah's laptop purchase" → confirm. (Or use the **Approval Inbox** UI.)
3. Repeat as `finance1@acme.com`, then `vp@acme.com` to walk the full chain.
4. Back as Sarah, the Inbox status feed reads e.g. "Approved by Mark Manager; waiting
   for finance approval"; the request detail page shows the step timeline and audit
   trail.

## Local development (without Docker)

```bash
# Backend — Python 3.12+
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=sqlite:///dev.db KIMI_API_KEY=sk-...   # or point at a local Postgres
uvicorn app.main:app --reload          # tables + seed data are created on startup

# Frontend
cd frontend
npm install
npm run dev                             # proxies /api to http://localhost:8000
```

### Tests

```bash
cd backend && python -m pytest tests -v      # unit tests (also run in CI)
./autotest/integration/run_integration.sh    # integration: fresh disposable PostgreSQL
./autotest/e2e/run_e2e.sh [--with-agent]     # e2e: rebuilds the stack from an empty DB
```

Unit tests cover the workflow engine (chain routing with requester-role skip,
conditions, quorum, delegation matrix, self-approval block, escalation), the REST API
(auth, RBAC, lifecycle, pagination, audit, status feed), and the agent (multi-turn
confirmation gate, tool authorization, failure handling) with a scripted fake LLM.
Integration tests run the real Alembic migration and API against PostgreSQL; E2E
drives the composed stack through the nginx proxy from a fresh database. Test plans
and UAT results live in `autotest/`.

### Migrations & schema

```bash
cd backend && DATABASE_URL=... alembic upgrade head
```

The rendered PostgreSQL DDL lives in [docs/schema.sql](docs/schema.sql)
(regenerate with `python scripts/dump_schema.py`).

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system design, data model, engine
  semantics, agent design, tradeoffs
- [SOLUTION.md](SOLUTION.md) — architecture decisions, AI usage, tradeoffs,
  production-readiness, lessons learned
- [docs/example_conversations.md](docs/example_conversations.md) — real agent
  transcripts (submission, review, decision, template creation)

## Repository structure

```
├── docker-compose.yml        # db + backend + frontend
├── backend/
│   ├── app/
│   │   ├── models.py         # SQLAlchemy schema (templates, instances, decisions, audit…)
│   │   ├── services/         # workflow engine, templates, delegations, audit
│   │   ├── api/              # REST routers (auth, requests, inbox, agent…)
│   │   ├── agent/            # Kimi orchestrator, tool schemas/executors, prompts
│   │   └── seed.py           # demo users/groups/templates
│   ├── alembic/              # migrations
│   ├── scripts/dump_schema.py
│   └── tests/                # engine / API / agent test suites
├── frontend/src/pages/       # Inbox, Requests, Templates, Delegations, Chat…
└── docs/                     # architecture, schema.sql, example conversations
```
