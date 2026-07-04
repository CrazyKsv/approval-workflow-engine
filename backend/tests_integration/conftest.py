"""Integration tests: the real FastAPI app against a real PostgreSQL database.

Run via autotest/integration/run_integration.sh, which starts a disposable Postgres
container and sets DATABASE_URL before pytest imports the app. Every session starts
from a completely empty database (fresh-data requirement): schema is created by the
Alembic migration, then seeded once.
"""
import os

import pytest

if not os.environ.get("DATABASE_URL", "").startswith("postgresql"):
    pytest.skip(
        "integration tests need DATABASE_URL pointing at PostgreSQL "
        "(use autotest/integration/run_integration.sh)",
        allow_module_level=True,
    )

os.environ.setdefault("SEED_ON_STARTUP", "false")
os.environ.setdefault("ENABLE_ESCALATION_SWEEP", "false")
os.environ.setdefault("KIMI_API_KEY", "integration-test-key")

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import User
from app.security import create_access_token
from app.seed import seed as seed_db
from app.services.template_loader import load_templates_from_yaml


@pytest.fixture(scope="session")
def migrated_db():
    """Start from an empty database, then create the schema via the real migration."""
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()
    command.upgrade(Config("alembic.ini"), "head")
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session")
def seeded(migrated_db):
    with SessionLocal() as db:
        seed_db(db)
    with SessionLocal() as db:
        load_templates_from_yaml(db)
    yield


@pytest.fixture(scope="session")
def client(seeded):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def tokens(seeded):
    """JWTs for every seeded demo user, keyed by short name."""
    emails = {
        "admin": "admin@acme.com",
        "manager": "manager@acme.com",
        "finance1": "finance1@acme.com",
        "finance2": "finance2@acme.com",
        "vp": "vp@acme.com",
        "sarah": "sarah@acme.com",
        "mike": "mike@acme.com",
    }
    with SessionLocal() as db:
        users = {key: db.query(User).filter_by(email=email).one() for key, email in emails.items()}
        return {key: create_access_token(user.id) for key, user in users.items()}


def auth(tokens, key):
    return {"Authorization": f"Bearer {tokens[key]}"}
