"""Render the canonical PostgreSQL DDL (tables + indexes) from app.models.

Usage: python scripts/dump_schema.py > ../docs/schema.sql
"""
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db import Base
from app import models  # noqa: F401 — register all tables on Base.metadata

dialect = postgresql.dialect()

print("-- Approval Workflow Engine — PostgreSQL schema")
print("-- Generated from app/models.py (single source of truth); do not edit by hand.\n")
for table in Base.metadata.sorted_tables:
    print(str(CreateTable(table).compile(dialect=dialect)).strip() + ";\n")
    for index in sorted(table.indexes, key=lambda i: i.name):
        print(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";")
    if table.indexes:
        print()
