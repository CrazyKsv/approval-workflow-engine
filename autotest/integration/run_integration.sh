#!/bin/sh
# Integration test runner: real PostgreSQL, always from a completely fresh database.
# Usage: ./autotest/integration/run_integration.sh [python-bin]
set -e

PYTHON_BIN="${1:-python3}"
PG_CONTAINER=approval-int-pg
PG_PORT=5544
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

cleanup() { docker rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

echo "Starting disposable PostgreSQL (port $PG_PORT)..."
docker run -d --name "$PG_CONTAINER" \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=approvals_test \
  -p "$PG_PORT":5432 postgres:16-alpine >/dev/null

echo "Waiting for PostgreSQL to accept connections..."
for i in $(seq 1 30); do
  if docker exec "$PG_CONTAINER" pg_isready -U postgres -d approvals_test >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

cd "$ROOT/backend"
echo "Running integration suite against fresh database..."
DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:$PG_PORT/approvals_test" \
  SEED_ON_STARTUP=false ENABLE_ESCALATION_SWEEP=false \
  "$PYTHON_BIN" -m pytest tests_integration -v --tb=short
echo "Integration tests passed."
