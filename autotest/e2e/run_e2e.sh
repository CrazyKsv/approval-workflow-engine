#!/bin/sh
# End-to-end runner: rebuild the whole stack from scratch (EMPTY database), wait for
# health, then run the scenario suite through the nginx proxy like the SPA does.
# Usage: ./autotest/e2e/run_e2e.sh [--with-agent]   (agent smoke needs KIMI_API_KEY in .env)
set -e

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo "Recreating stack from scratch (fresh empty database)..."
docker compose down -v --remove-orphans >/dev/null 2>&1 || true
docker compose up --build -d

echo "Waiting for backend health..."
for i in $(seq 1 60); do
  if curl -sf http://localhost:8000/healthz >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -sf http://localhost:8000/healthz >/dev/null || { echo "backend did not become healthy"; exit 1; }

echo "Running E2E scenarios..."
python3 autotest/e2e/e2e_scenarios.py "$@"
