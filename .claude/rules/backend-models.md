---
description: Rules for SQLAlchemy models, enums, and migrations
globs: backend/app/models/**, alembic/**
---

# Backend Models & Migrations

## Creating a Model

1. Use `UUIDMixin`, `TimestampMixin`, `Base`
2. Import in `app/models/__init__.py`
3. For enums: use `values_callable` on SAEnum with lowercase values
4. Create migration: `docker compose exec api alembic revision --autogenerate -m "add_tablename"`
5. Verify enum values in the generated migration match the model

## Enum Rules

All SQLAlchemy enum columns MUST use `values_callable`:

```python
SAEnum(RoleName, name="rolename", values_callable=lambda e: [x.value for x in e])
```

To modify an enum:
1. Update the Python enum class
2. Update the SAEnum column (keep `values_callable`)
3. Create a migration with `op.execute("ALTER TYPE ... ADD VALUE ...")`
4. Run `test_model_enum_values_are_lowercase` to verify

## Relationships

Use `lazy="selectin"` for all relationships accessed in API responses to avoid async lazy-load errors.

## Embedding Columns

Question and Answer models have optional `embedding` columns (`Vector(1024)`) backed by pgvector with hnsw indexes.
