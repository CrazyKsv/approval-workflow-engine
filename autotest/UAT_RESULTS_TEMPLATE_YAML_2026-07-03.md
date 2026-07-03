# UAT Results — YAML-Configurable Workflow Templates (2026-07-03)

**Branch:** `feature/agent-conversation-history`
**Driver:** Claude-in-Chrome against the real SPA + a freshly rebuilt Docker stack.
**Screenshots:** `autotest/2026-07-03-template-yaml-screenshot/<case>.png`.

## What changed

Previously the three demo templates were created in Python inside `seed.py`. They are now
declared in **`backend/app/workflow_templates.yaml`** and **auto-loaded on startup** by
`app/services/template_loader.py` (create-if-missing by name). This makes the catalog
configurable and adds a **PR-based onboarding path** alongside the existing admin-UI and
AI-assistant paths. `seed.py` now seeds only users + the Finance group.

- Config: `TEMPLATES_FILE` (path) and `LOAD_TEMPLATES_ON_STARTUP` (default on).
- `PyYAML` added to `backend/requirements.txt`.
- Startup wiring: `main.py` runs the loader after seeding; the integration `seeded`
  fixture does the same.

## Automated tests

| Suite | Result |
|---|---|
| Backend unit (`pytest tests`) | **78 passed** (incl. 7 new `test_template_loader.py`, with a bundled-catalog validity guard) |
| Integration (`tests_integration`, real Postgres + Alembic) | **8 passed** (INT-2 now loads via the catalog loader) |
| Frontend build (`tsc -b && vite build`) | green (unchanged; no frontend change for this feature) |

## UAT — 5/5 PASS (three onboarding paths coexist)

| ID | Scenario | Result | Evidence |
|---|---|---|---|
| YT1 | Fresh boot auto-loads the catalog | ✅ log "created 3, skipped 0, errors 0"; 3 templates in the admin UI | `YT1-autoloaded-templates.png` |
| YT2 | PR-path: add a template + restart | ✅ log "created 1, skipped 3"; "Travel Reimbursement" appears; existing/users untouched; conditional VP step (`amount >= 5000`) loaded | `YT2-pr-path-new-template.png` |
| YT3 | Idempotency: restart again | ✅ log "created 0, skipped 4"; 4 templates / 4 distinct names (no duplicates) | (startup log + DB count) |
| YT4 | Admin UI onboarding | ✅ "Contract Approval (UI)" created via "New Template"; coexists | `YT4-admin-ui-create.png` |
| YT5 | Assistant onboarding | ✅ "Budget Approval" created via the assistant (confirmation gate); coexists | `YT5-assistant-onboard.png` |

Final catalog after the run (all attributed to the admin), showing all three paths side by
side (`YT-all-paths-coexist.png`):

```
1  Expense Report          finance      (YAML catalog)
2  Purchase Order          procurement  (YAML catalog)
3  Time Off Request        hr           (YAML catalog)
4  Travel Reimbursement    travel       (YAML catalog — added via the PR-path demo)
5  Contract Approval (UI)  legal        (admin UI "New Template")
6  Budget Approval         finance      (AI assistant)
```

## Startup log excerpts (real Docker boot)

```
INFO seed Seeded 7 users and 1 group (templates load from the YAML catalog)
INFO template_loader Template catalog load complete: created 3, skipped 0 (already present), errors 0
...after adding Travel Reimbursement to the catalog + restart:
INFO seed Seed skipped: users already exist
INFO template_loader Template catalog load complete: created 1, skipped 3 (already present), errors 0
...after a no-change restart:
INFO template_loader Template catalog load complete: created 0, skipped 4 (already present), errors 0
```

## Notes

- **PR-path demo mechanics:** to demonstrate YT2/YT3 without changing the committed
  baseline (which would shift the unit/integration assertions), the modified 4-template
  catalog was applied to the running container and the backend restarted; the committed
  `workflow_templates.yaml` remains the 3-template baseline, and the container's file was
  restored afterward. A real PR is simply an edit to that committed file.
- **Safety:** the loader never mutates or deletes existing templates. Changing a live
  template is done via the admin UI/assistant or by adding a new named/versioned entry —
  create-if-missing avoids clobbering templates that already have live requests.
- **CI fail-fast:** `test_bundled_catalog_is_valid` loads the shipped YAML and asserts it
  parses and produces the expected chain templates, so a malformed catalog PR fails CI.
