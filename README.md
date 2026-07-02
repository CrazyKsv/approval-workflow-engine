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

Three workflows are seeded: **Expense Report** (manager → finance if > $1,000),
**Purchase Order** (manager → whole finance team if > $5,000 → VP if > $10,000, with
SLAs/escalation), and **Time Off Request**.

### Try the demo flow

1. Sign in as `sarah@acme.com` → **AI Assistant** → "I need approval for a $5,000
   laptop purchase" → confirm when asked.
2. Sign in as `manager@acme.com` → "What requests are waiting for my approval?" →
   "Approve Sarah's laptop purchase" → confirm. (Or use the **Approval Inbox** UI.)
3. Check the request detail page for the step timeline and audit trail.

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
cd backend && python -m pytest tests -v
```

43 tests cover the workflow engine (conditions, sequential/parallel routing, quorum,
delegation, escalation), the REST API (auth, RBAC, lifecycle, pagination, audit), and
the agent (multi-turn conversation with the confirmation gate, tool authorization,
failure handling) using a scripted fake LLM.

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
