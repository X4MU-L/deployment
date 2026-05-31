---
name: python-sqlalchemy-model-migration
description: Use when adding or changing SQLAlchemy models in a Python application, including relationships, indexes, soft-delete/status fields, timestamps, Alembic migrations, and model-level integration tests.
---

# Python SQLAlchemy Model Migration

## Purpose

Introduce durable state safely and keep ORM models, migrations, repositories, and tests aligned.

Use this when:

- A new service needs persisted state.
- A new field/index/constraint is needed.
- A relationship between domain objects is introduced.
- Soft-delete, status transitions, or retention behavior is added.

## First Questions

- What domain concept is being persisted?
- Is this a new table or a change to an existing table?
- What is the primary key strategy?
- Which fields are required, unique, indexed, or nullable?
- Does the table need `created_at`, `updated_at`, `deleted_at`, `status`, `owner_id`, or tenant fields?
- What relationships should exist?
- What data migration or backfill is required?

## Model Pattern

Prefer SQLAlchemy 2 typed mappings when the project supports them:

```python
class Thing(Base):
    __tablename__ = "things"

    thing_id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

Add relationships only when code uses them. Avoid relationship sprawl.

## Constraints and Indexes

- Add unique constraints for names, slugs, external IDs, or one-active-record rules.
- Add indexes for lookup paths used by repositories.
- Prefer composite indexes for common filtered queries.
- Keep nullable fields intentional.
- Avoid storing derived values unless query performance or auditability requires it.

## Migration Workflow

- Add/update the model.
- Ensure migration discovery imports the model through the project’s metadata path.
- Create an Alembic migration.
- Review generated migrations manually.
- Include both upgrade and downgrade when the project expects downgrade support.
- For non-null additions to populated tables, use a staged migration: nullable column, backfill, then non-null constraint.

## Repository and Service Follow-Through

After model changes:

- Update repository record mapping.
- Update create/update methods.
- Update service response mapping.
- Update schemas if the field is part of the API contract.
- Update factories and tests.

## Tests

Add or update integration tests for:

- Insert/fetch behavior.
- Constraints.
- Relationship loading if used.
- Soft-delete/status filtering.
- Migration-sensitive defaults such as timestamps.

Run:

```bash
pytest
alembic upgrade head
```

Use the project’s actual database test strategy when available.
