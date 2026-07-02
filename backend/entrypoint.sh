#!/bin/sh
set -e

echo "Waiting for database..."
python - <<'EOF'
import time
import sys
from sqlalchemy import create_engine, text
from app.config import get_settings

engine = create_engine(get_settings().database_url)
for attempt in range(30):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        sys.exit(0)
    except Exception:
        time.sleep(1)
print("Database not reachable after 30s", file=sys.stderr)
sys.exit(1)
EOF

echo "Running migrations..."
alembic upgrade head

echo "Starting API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
