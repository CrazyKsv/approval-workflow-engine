# Test Plan — YAML-Configurable Workflow Templates

**Date:** 2026-07-03
**Branch:** `feature/agent-conversation-history`
**Feature:** Workflow templates are declared in a YAML catalog
(`backend/app/workflow_templates.yaml`) and auto-loaded on startup, so a template can be
onboarded three ways — **(1) by PR** (add to the YAML), **(2) admin UI** ("New Template"),
or **(3) the AI assistant** (`create_workflow_template`).

## Design

- **Source of truth:** `backend/app/workflow_templates.yaml` (path is configurable via
  `TEMPLATES_FILE`; loading toggled by `LOAD_TEMPLATES_ON_STARTUP`).
- **Loader:** `app/services/template_loader.py` runs on startup after user seeding.
  Semantics = **create-if-missing by name**: it creates any catalog template that doesn't
  already exist and never mutates or duplicates existing ones (idempotent). Each entry is
  validated with the same `TemplateCreate` schema and persisted through the same
  `create_template` service the API/assistant use (audit + validation). A malformed entry
  is logged and skipped rather than aborting startup; CI validates the shipped catalog.
- `seed.py` now seeds only users + the Finance group; templates come from the catalog.

## Test levels

### Unit — `backend/tests/test_template_loader.py`
| Case | Assertion |
|---|---|
| Load into empty DB | all catalog templates created with correct fields/steps, attributed to admin |
| Idempotent | second load creates 0, skips all; no duplicates |
| Add-only-new (PR path) | adding an entry creates only the new template |
| Pre-existing name skipped | a template already created (UI/assistant) is left untouched |
| Missing file | graceful no-op |
| Malformed entry isolated | valid entries load; bad entry recorded in `errors`, not created |
| Bundled catalog valid | the shipped YAML loads cleanly → 3 chain templates (CI fail-fast on bad PRs) |

### Integration — `backend/tests_integration/` (real Postgres + Alembic migration)
The `seeded` fixture now runs the loader; INT-2 asserts the loaded templates use the
manager→finance→vp chain. Full suite must stay green.

### UAT — Claude-in-Chrome, fresh stack (`down -v && up --build`)
| ID | Scenario | Expected |
|---|---|---|
| YT1 | Fresh boot | Catalog's templates auto-load; visible in the admin Templates page; startup log "created N" |
| YT2 | PR-path onboarding | Add a template to the catalog + restart → only the new one is created; existing untouched; conditional step loads |
| YT3 | Idempotency | Restart again with no change → "created 0, skipped N"; no duplicates |
| YT4 | Admin UI onboarding | Admin creates a template via "New Template" → coexists |
| YT5 | Assistant onboarding | Admin asks the assistant to create a template → coexists |

## Exit criteria

Unit + integration suites green (incl. new loader tests and INT-2 via the loader); the
frontend build stays green; UAT YT1–YT5 pass with the three onboarding paths coexisting.
Results in `UAT_RESULTS_TEMPLATE_YAML_2026-07-03.md`; screenshots in
`autotest/2026-07-03-template-yaml-screenshot/`.
