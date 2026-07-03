"""Load workflow templates from the declarative YAML catalog on startup.

The YAML file (see ``settings.templates_file``) is the source of truth for baseline
templates. Loading is **create-if-missing by name**: every template declared in the file
that does not already exist is created; existing templates (including ones created by an
admin or the AI assistant) are never mutated or duplicated. This makes onboarding a
template by PR (edit the YAML) a first-class path alongside the admin UI and the assistant.

Each entry is validated with the same ``TemplateCreate`` schema and persisted through the
same ``create_template`` service the API/assistant use, so RBAC-equivalent validation and
audit logging apply. A single malformed entry is logged and skipped rather than taking down
startup; CI validates the shipped catalog strictly (see tests).
"""
import logging
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User, WorkflowTemplate
from app.schemas import TemplateCreate
from app.services import templates as template_service

logger = logging.getLogger("template_loader")


def load_templates_from_yaml(db: Session, path: str | None = None) -> dict:
    """Create any catalog templates that don't already exist (matched by name).

    Returns a summary dict: ``{created, skipped, errors, created_names}``.
    Idempotent — safe to run on every startup.
    """
    settings = get_settings()
    file_path = Path(path or settings.templates_file)
    if not file_path.exists():
        logger.warning("Template catalog not found at %s — skipping template load", file_path)
        return {"created": 0, "skipped": 0, "errors": [], "created_names": []}

    try:
        raw = yaml.safe_load(file_path.read_text()) or {}
    except yaml.YAMLError as exc:
        logger.error("Template catalog %s is not valid YAML: %s", file_path, exc)
        return {"created": 0, "skipped": 0, "errors": [{"name": None, "error": str(exc)}], "created_names": []}

    entries = raw.get("templates") or []
    if not entries:
        logger.info("Template catalog %s declares no templates", file_path)
        return {"created": 0, "skipped": 0, "errors": [], "created_names": []}

    # Templates are attributed to an admin so audit + ownership are consistent with the
    # admin-UI / assistant paths. Seeding runs before this, so an admin normally exists.
    actor = db.scalar(select(User).where(User.role == "admin").order_by(User.id).limit(1))
    if actor is None:
        logger.warning("No admin user present — cannot load templates from catalog; skipping")
        return {"created": 0, "skipped": len(entries), "errors": [], "created_names": []}

    existing = set(db.scalars(select(WorkflowTemplate.name)).all())
    created_names: list[str] = []
    errors: list[dict] = []
    skipped = 0

    for entry in entries:
        name = entry.get("name") if isinstance(entry, dict) else None
        if not name:
            logger.error("Skipping template entry without a name: %r", entry)
            errors.append({"name": None, "error": "template entry has no 'name'"})
            continue
        if name in existing:
            skipped += 1
            continue
        try:
            payload = TemplateCreate(**entry)
            template_service.create_template(db, actor, payload)
            db.commit()
        except Exception as exc:  # isolate a bad entry — don't abort the whole load/startup
            db.rollback()
            logger.error("Failed to load template %r from catalog: %s", name, exc)
            errors.append({"name": name, "error": str(exc)})
            continue
        existing.add(name)
        created_names.append(name)

    logger.info(
        "Template catalog load complete: created %d, skipped %d (already present), errors %d",
        len(created_names), skipped, len(errors),
    )
    return {"created": len(created_names), "skipped": skipped, "errors": errors, "created_names": created_names}
