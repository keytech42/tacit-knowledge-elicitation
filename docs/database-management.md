# Database Management

Comprehensive guide to PostgreSQL operations: backups, recovery, connection management, monitoring, migrations, and production tuning.

> **Quick reference:** Jump to the [Administrator Cheatsheet](#administrator-cheatsheet) for a single-page command and config reference.

## Overview

| Component | Technology | Notes |
|-----------|-----------|-------|
| **Engine** | PostgreSQL 16 | via `pgvector/pgvector:pg16` image |
| **Extension** | pgvector | 1024-dim embeddings with HNSW indexes |
| **ORM** | SQLAlchemy 2.0 (async) | asyncpg driver |
| **Migrations** | Alembic | Auto-run on API startup |
| **Connection pool** | QueuePool | Configurable via environment |
| **Backup** | pg_dump sidecar | Daily full + WAL archiving in production |

---

## Connection Pool

The async engine in `backend/app/database.py` creates a connection pool with configurable parameters:

| Environment Variable | Default | Purpose |
|---------------------|---------|---------|
| `DB_POOL_SIZE` | 10 | Number of persistent connections in the pool |
| `DB_MAX_OVERFLOW` | 20 | Additional connections allowed beyond pool_size under load |
| `DB_POOL_PRE_PING` | true | Test connections before checkout (detects stale connections) |
| `DB_POOL_RECYCLE` | 3600 | Recycle connections after N seconds (prevents idle timeout drops) |

**Behavior:**
- Under normal load: up to `pool_size` connections are reused
- Under burst: up to `pool_size + max_overflow` connections exist (overflow connections are discarded after use)
- `pool_pre_ping` sends a lightweight `SELECT 1` before each checkout, adding ~1ms latency but preventing "connection reset" errors
- `pool_recycle` closes and recreates connections older than 1 hour, useful when a firewall or load balancer drops idle connections

**Monitoring:** `GET /health/db` returns live pool stats:
```json
{
  "pool": {
    "pool_size": 10,
    "checked_in": 8,
    "checked_out": 2,
    "overflow": 0
  }
}
```

If `checked_out` consistently equals `pool_size + overflow`, the pool is exhausted — increase `DB_POOL_SIZE` or investigate slow queries.

---

## Backup & Recovery

### Architecture

A `backup` sidecar service runs alongside PostgreSQL in Docker Compose:

```
┌──────────┐     pg_dump      ┌──────────┐
│    db    │ ◄─────────────── │  backup  │
│ (pg16)   │                  │ (pg16)   │
└──────────┘                  └──────────┘
      │              │              │
      ▼              ▼              │
  pgdata volume   host directory ◄──┘
  (live data)     ./backups/ (backup files + WAL)
```

Both the `db` and `backup` containers mount the same host directory (`${BACKUP_DIR:-./backups}`) at `/backups`. This is a **bind mount**, not a Docker named volume — backup files survive `docker compose down -v`.

The backup container connects to `db` over Docker networking (not volume-level access) and runs `pg_dump` on a daily loop. The `db` container writes WAL archive segments to the same directory.

### Daily Backups

Backups run automatically every 24 hours. Each backup:
1. Runs `pg_dump` with `--clean --if-exists` flags (creates a restorable SQL file)
2. Compresses with gzip → `backup_YYYYMMDD_HHMMSS.sql.gz`
3. Tags Sunday backups as weekly (hard-link to `weekly_*` file — no extra storage)
4. Rotates: keeps 7 daily + 4 weekly backups

```bash
# Trigger a manual backup immediately
make backup

# List existing backups
docker compose exec backup ls -lh /backups/

# Check backup file sizes
docker compose exec backup ls -lhS /backups/backup_*.sql.gz
```

### Restore

```bash
# Restore from latest backup
make restore

# Restore from a specific backup file
docker compose exec backup /scripts/restore.sh /backups/backup_20260311_030000.sql.gz
```

The restore script:
1. Prompts for confirmation (bypass with `--yes`)
2. Drops and recreates the target database
3. Decompresses and applies the SQL dump
4. Verifies by checking table count

**Warning:** Restore replaces all data in the target database. Always verify you're targeting the correct database.

### Backup Verification

```bash
make backup-verify
```

This restores the latest backup into a temporary database, compares table counts against the live database, then drops the temporary database. Use this to confirm backups are valid without affecting production.

### WAL Archiving (Production)

The base `docker-compose.yml` mounts `backup/postgresql.conf` which enables WAL (Write-Ahead Log) archiving:

| Setting | Value | Purpose |
|---------|-------|---------|
| `wal_level` | `replica` | Enables continuous archiving |
| `archive_mode` | `on` | Copies completed WAL segments to archive |
| `archive_command` | `cp %p /backups/wal/%f` | Stores WAL files in the backups volume |
| `max_wal_senders` | 3 | Allows streaming replication connections |

WAL archiving is always enabled (the custom `postgresql.conf` is mounted in the base compose). WAL segments are archived to `/backups/wal/` on the backup volume.

With WAL archiving enabled, you can perform **point-in-time recovery (PITR)**: restore a base backup, then replay WAL files up to a specific timestamp. This allows recovering to any point between daily backups.

### Retention Policy

| Type | Retention | Storage |
|------|-----------|---------|
| Daily backups | 7 days | `backup_YYYYMMDD_HHMMSS.sql.gz` |
| Weekly backups | 4 weeks | `weekly_YYYYMMDD_HHMMSS.sql.gz` (hard-link) |
| WAL segments | Until next daily backup | `/backups/wal/` (production only) |

### Host-Persistent Storage

Backups are stored on the host filesystem at `${BACKUP_DIR:-./backups}` via a bind mount (not a Docker named volume). This means backup files **survive `docker compose down -v`** — only the live database volume (`pgdata`) is destroyed.

Configure the backup directory via the `BACKUP_DIR` environment variable:
```bash
# Default (relative to project root)
BACKUP_DIR=./backups

# Production (absolute path recommended)
BACKUP_DIR=/opt/backups/knowledge-elicitation
```

For disaster recovery (host failure), you can sync the host-side backup directory externally:
```bash
# rsync to another server
rsync -az ./backups/ backupserver:/backups/knowledge-elicitation/

# rclone to S3
rclone sync ./backups/ s3:my-bucket/knowledge-elicitation-backups/
```

---

## Migrations

### How They Run

Migrations are managed by Alembic and run automatically on API startup:

```bash
# In docker-compose.yml, the api command includes:
alembic upgrade head && uvicorn app.main:app ...
```

### Current Migrations

| # | Description | Key Changes |
|---|------------|-------------|
| 001 | Initial schema | users, roles, questions, answers, reviews, feedback, options |
| 002 | Answer version tracking | `answer_version` on reviews |
| 003 | Content deduplication | `content_hash` on answer revisions |
| 004 | Embeddings (pgvector) | `CREATE EXTENSION vector`, embedding columns, HNSW indexes |
| 005 | Resize embeddings | 1536 → 1024 dimensions |
| 006 | Respondent assignment | `assigned_respondent_id` on questions |
| 007 | Slack integration | `slack_thread_ts`, `slack_channel` on questions |
| 008 | Superseded verdict | Add `superseded` to review_verdict enum |
| 009 | Source documents | `source_documents` table, `source_type` enum, extraction columns |
| 010 | Respondent pool | `respondent_pool_version`, `question_respondents` table |
| 011 | AI task persistence | `ai_tasks` table |

### Manual Migration Commands

```bash
# Apply all pending migrations
make migrate

# Create a new auto-generated migration
docker compose exec api alembic revision --autogenerate -m "description"

# Check current revision
docker compose exec api alembic current

# View migration history
docker compose exec api alembic history

# Downgrade one step (use with caution)
docker compose exec api alembic downgrade -1
```

### Enum Migrations

PostgreSQL enums require special handling — you cannot drop or rename values, only add new ones:

```python
# In a migration file:
op.execute("ALTER TYPE reviewverdict ADD VALUE 'superseded'")
```

After modifying an enum:
1. Update the Python enum class
2. Keep `values_callable` on the SAEnum column
3. Create the migration
4. Run `test_model_enum_values_are_lowercase` to verify consistency

### Migration vs. ORM Schema Drift

Tests use `Base.metadata.create_all()` (not Alembic), so a broken migration can pass all tests. To catch drift:

```bash
# Apply migration in Docker, then run tests
make migrate && make test
```

The `test_model_enum_values_are_lowercase` parametrized test catches enum value mismatches between ORM models and migrations.

---

## Monitoring

### Health Endpoints

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /health` | None | Liveness check — returns `{"status": "ok"}` |
| `GET /health/db` | None | Extended check — pool stats, row counts, DB size |

### GET /health/db Response

```json
{
  "status": "ok",
  "pool": {
    "pool_size": 10,
    "checked_in": 8,
    "checked_out": 2,
    "overflow": 0
  },
  "row_counts": {
    "users": 12,
    "questions": 47,
    "answers": 89,
    "reviews": 34,
    "source_documents": 5
  },
  "database_size_bytes": 52428800
}
```

### What to Monitor

| Metric | Source | Alert Threshold |
|--------|--------|----------------|
| Pool exhaustion | `/health/db` → `pool.checked_out` | `checked_out >= pool_size` sustained |
| Database size growth | `/health/db` → `database_size_bytes` | Depends on capacity |
| Row counts | `/health/db` → `row_counts` | Unexpected drops (data loss) |
| Backup age | Check latest file in `/backups/` | Older than 25 hours |
| Connection errors | Application logs | Any `connection refused` or `pool timeout` |

### Useful Diagnostic Queries

```sql
-- Active connections
SELECT count(*) FROM pg_stat_activity WHERE datname = 'knowledge_elicitation';

-- Table sizes (including indexes)
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;

-- Index usage
SELECT indexrelname, idx_scan, pg_size_pretty(pg_relation_size(indexrelid))
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;

-- Long-running queries
SELECT pid, now() - pg_stat_activity.query_start AS duration, query
FROM pg_stat_activity
WHERE state != 'idle' AND query_start IS NOT NULL
ORDER BY duration DESC;

-- Embedding column storage (pgvector)
SELECT
  'questions' AS table_name,
  count(*) AS total_rows,
  count(embedding) AS with_embedding,
  pg_size_pretty(sum(pg_column_size(embedding))) AS embedding_size
FROM questions
UNION ALL
SELECT
  'answers',
  count(*),
  count(embedding),
  pg_size_pretty(sum(pg_column_size(embedding)))
FROM answers;
```

---

## Production Configuration

### Pre-Flight Validation

```bash
./scripts/check-env.sh
```

Validates before production start:
- `DB_PASSWORD` is not `devpassword`
- `JWT_SECRET` is not a default value and is >= 32 characters
- `DEV_LOGIN_ENABLED` is not `true`

### PostgreSQL Tuning

The `backup/postgresql.conf` contains production-tuned settings:

| Setting | Value | Purpose |
|---------|-------|---------|
| `shared_buffers` | 256MB | In-memory cache for table/index data |
| `wal_level` | replica | Enables WAL archiving and replication |
| `max_wal_senders` | 3 | Streaming replication slots |
| `archive_mode` | on | Copy completed WAL segments |
| `checkpoint_timeout` | 10min | Time between automatic checkpoints |
| `checkpoint_completion_target` | 0.9 | Spread writes over 90% of checkpoint interval |

Mounted in the base `docker-compose.yml`:
```yaml
db:
  volumes:
    - ./backup/postgresql.conf:/etc/postgresql/postgresql.conf:ro
  command: postgres -c config_file=/etc/postgresql/postgresql.conf
```

### Resource Limits

Recommended per-service limits for production (set via `deploy.resources.limits` in an overlay or orchestrator):

| Service | Memory | CPU |
|---------|--------|-----|
| db | 1G | 1 |
| api | 512M | 0.5 |
| worker | 512M | 0.5 |
| backup | 256M | 0.25 |

### Starting Production

```bash
# 1. Validate environment
./scripts/check-env.sh

# 2. Build and start
docker compose up -d --build

# 3. Start backup sidecar
docker compose --profile backup up -d

# 4. Verify health
curl http://localhost:8000/health/db | jq .

# 5. Verify backup service
docker compose logs backup --tail 5
```

---

## Data Storage Profile

Understanding what's in the database and how much space it uses:

### Table Purposes

| Table | Rows Growth | Large Fields | Notes |
|-------|------------|--------------|-------|
| `users` | Slow | — | Hundreds, not thousands |
| `roles` | Static | — | Fixed set (admin, author, respondent, reviewer) |
| `user_roles` | Slow | — | Association table, grows with users |
| `questions` | Moderate | `body` (text), `embedding` (4KB) | Core entity |
| `answers` | Moderate | `body` (text), `embedding` (4KB) | 1-5 per question |
| `answer_revisions` | Moderate | `body` (text) | Immutable history, grows with edits |
| `answer_options` | Low | `body` (text) | Up to 4 per question |
| `answer_collaborators` | Low | — | Grows with shared answer access grants |
| `reviews` | Moderate | `comment` (text) | 1-3 per answer |
| `review_comments` | Low | `body` (text) | Threaded discussion |
| `question_respondents` | Low | — | Grows with respondent assignments |
| `question_quality_feedback` | Low | — | One per user per question |
| `source_documents` | Low | `body` (text, 10K-100K+) | Largest individual records |
| `ai_interaction_logs` | High | `request_body` (JSONB) | Grows with every AI operation |
| `ai_tasks` | High | `result` (JSONB) | One per AI operation |

### Embedding Storage

Each embedding is a 1024-dimensional float32 vector (~4KB per row). With HNSW indexes, expect ~2x overhead:

| Scale | Questions | Answers | Embedding Storage |
|-------|-----------|---------|-------------------|
| Small | 100 | 500 | ~5 MB |
| Medium | 1,000 | 5,000 | ~50 MB |
| Large | 10,000 | 50,000 | ~500 MB |

### Growth Management

- **AI logs** grow fastest — consider periodic archival (export via `GET /api/v1/ai-logs/export` then truncate)
- **Answer revisions** are immutable — they accumulate but are essential for audit trail
- **Source documents** can be individually large — the `body` field stores full document text

---

## Data Export

Three admin-only streaming JSONL endpoints for extracting training data:

| Endpoint | Description | Use Case |
|----------|-------------|----------|
| `GET /api/v1/export/training-data` | Q&A pairs with review verdicts | RAG, fine-tuning, PEFT |
| `GET /api/v1/export/embeddings` | 1024-dim entity vectors | UMAP, clustering, similarity analysis |
| `GET /api/v1/export/review-pairs` | Answer + review verdict pairs | RLHF, reward modeling |

All support `date_from`, `date_to` filters. See [API Reference](api-reference.md#data-export-admin-only) for full query parameters.

```bash
# Export all approved Q&A pairs as JSONL
curl -H "Authorization: Bearer <admin-jwt>" \
  "http://localhost:8000/api/v1/export/training-data?question_status=published" \
  > training_data.jsonl

# Export embeddings
curl -H "Authorization: Bearer <admin-jwt>" \
  "http://localhost:8000/api/v1/export/embeddings?entity_type=both" \
  > embeddings.jsonl

# Export review pairs for reward modeling
curl -H "Authorization: Bearer <admin-jwt>" \
  "http://localhost:8000/api/v1/export/review-pairs?verdict=approved" \
  > reward_pairs.jsonl
```

---

## pgvector & Embeddings

### Column Definition

Both `questions` and `answers` tables have an optional `embedding` column:

```python
embedding = Column(Vector(1024), nullable=True)
```

Embeddings are generated automatically on question create/update and answer submit when `EMBEDDING_MODEL` is configured. See [Embeddings Setup](embeddings.md) for inference engine configuration.

### Indexes

HNSW (Hierarchical Navigable Small World) indexes for approximate nearest neighbor search:

```sql
CREATE INDEX ix_questions_embedding ON questions
  USING hnsw (embedding vector_cosine_ops);

CREATE INDEX ix_answers_embedding ON answers
  USING hnsw (embedding vector_cosine_ops);
```

HNSW provides ~95% recall at sub-millisecond latency for datasets under 100K rows.

### Dimension Changes

If switching to a model with different dimensions (e.g., OpenAI's 1536-dim `text-embedding-3-small`):

1. Create a migration to alter the column: `ALTER TABLE questions ALTER COLUMN embedding TYPE vector(1536)`
2. Rebuild HNSW indexes
3. Re-generate all existing embeddings (old ones become incompatible)

---

## Troubleshooting

### Connection Pool Exhaustion

**Symptom:** API requests hang or return 500 errors.

```bash
# Check pool status
curl http://localhost:8000/health/db | jq .pool
```

If `checked_out` equals `pool_size` and `overflow` is at max:
1. Increase `DB_POOL_SIZE` and `DB_MAX_OVERFLOW`
2. Check for long-running queries (see diagnostic queries above)
3. Verify `pool_recycle` is set (stale connections may not release)

### Backup Failures

```bash
# Check backup service logs
docker compose logs backup --tail 20

# Test database connectivity from backup container
docker compose exec backup pg_isready -h db -U app -d knowledge_elicitation
```

Common issues:
- `db` container not healthy yet → backup depends on `service_healthy`, should auto-retry
- Disk full → check `docker system df` and prune if needed
- Permission denied → verify `PGUSER`/`PGPASSWORD` match db container env

### Migration Failures

```bash
# Check current migration state
docker compose exec api alembic current

# View failed migration details
docker compose exec api alembic history --verbose

# If stuck, check for lock
docker compose exec db psql -U app -d knowledge_elicitation \
  -c "SELECT * FROM alembic_version;"
```

### Embedding Column Issues

**"column embedding does not exist"** in tests:
- Ensure `CREATE EXTENSION IF NOT EXISTS vector` runs before `create_all()` in conftest.py

**Dimension mismatch:**
- The column expects 1024 dimensions. If your model outputs different dimensions, alter the column and rebuild indexes.

---

## Administrator Cheatsheet

Everything an admin can do, at a glance.

### Daily Operations

```bash
# Start services (dev)
make up

# Start services (production — base compose is already production-safe)
docker compose up -d --build
docker compose --profile backup up -d  # start backup sidecar

# Stop everything
make down

# View logs (all services)
make logs

# View logs (specific service)
docker compose logs api --tail 50 -f
docker compose logs backup --tail 50 -f

# Open a shell in the API container
make shell

# Seed demo data (5 users, 5 questions)
make seed
```

### Health & Status

```bash
# Quick liveness check
curl http://localhost:8000/health

# Full database health (pool, row counts, DB size)
curl http://localhost:8000/health/db | jq .

# Check pool is not exhausted (checked_out < pool_size)
curl -s http://localhost:8000/health/db | jq '.pool'

# Check database size
curl -s http://localhost:8000/health/db | jq '.database_size_bytes / 1048576 | floor | tostring + " MB"'

# Check row counts
curl -s http://localhost:8000/health/db | jq '.row_counts'

# Check all containers are running and healthy
docker compose ps
```

### Backup & Restore

```bash
# Trigger a backup now
make backup

# List all backups (newest first)
docker compose exec backup ls -lht /backups/*.sql.gz

# Check latest backup age and size
docker compose exec backup stat /backups/$(docker compose exec backup ls -t /backups/backup_*.sql.gz | head -1)

# Verify latest backup (restore to temp DB, compare tables, cleanup)
make backup-verify

# Restore from latest backup (interactive confirmation)
make restore

# Restore from a specific backup file
docker compose exec backup /scripts/restore.sh /backups/backup_20260311_030000.sql.gz

# Restore without confirmation prompt
docker compose exec backup /scripts/restore.sh --yes /backups/backup_20260311_030000.sql.gz

# Check backup service logs
docker compose logs backup --tail 20
```

### Migrations

```bash
# Apply all pending migrations
make migrate

# Check current migration version
docker compose exec api alembic current

# View full migration history
docker compose exec api alembic history

# Create a new auto-generated migration
docker compose exec api alembic revision --autogenerate -m "add_new_table"

# Downgrade one step (caution: may lose data)
docker compose exec api alembic downgrade -1

# Check for stuck migration lock
docker compose exec db psql -U app -d knowledge_elicitation \
  -c "SELECT * FROM alembic_version;"
```

### Database Shell

```bash
# Open psql in the database container
docker compose exec db psql -U app -d knowledge_elicitation

# Run a one-off SQL query
docker compose exec db psql -U app -d knowledge_elicitation \
  -c "SELECT count(*) FROM questions WHERE status = 'published';"

# Table sizes
docker compose exec db psql -U app -d knowledge_elicitation \
  -c "SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
      FROM pg_catalog.pg_statio_user_tables
      ORDER BY pg_total_relation_size(relid) DESC;"

# Active connections
docker compose exec db psql -U app -d knowledge_elicitation \
  -c "SELECT count(*) AS connections FROM pg_stat_activity
      WHERE datname = 'knowledge_elicitation';"

# Long-running queries (> 5 seconds)
docker compose exec db psql -U app -d knowledge_elicitation \
  -c "SELECT pid, now() - query_start AS duration, left(query, 80)
      FROM pg_stat_activity
      WHERE state != 'idle' AND now() - query_start > interval '5 seconds'
      ORDER BY duration DESC;"

# Kill a stuck query by PID
docker compose exec db psql -U app -d knowledge_elicitation \
  -c "SELECT pg_terminate_backend(<pid>);"

# Embedding stats
docker compose exec db psql -U app -d knowledge_elicitation \
  -c "SELECT 'questions' AS t, count(*) AS total, count(embedding) AS with_emb
      FROM questions UNION ALL
      SELECT 'answers', count(*), count(embedding) FROM answers;"
```

### Data Export

```bash
# Export Q&A training data (all published questions)
curl -H "Authorization: Bearer <jwt>" \
  "http://localhost:8000/api/v1/export/training-data?question_status=published" \
  > training_data.jsonl

# Export Q&A training data (date range)
curl -H "Authorization: Bearer <jwt>" \
  "http://localhost:8000/api/v1/export/training-data?date_from=2026-01-01&date_to=2026-03-31" \
  > q1_training.jsonl

# Export Q&A training data (specific category)
curl -H "Authorization: Bearer <jwt>" \
  "http://localhost:8000/api/v1/export/training-data?category=Security" \
  > security_qa.jsonl

# Export all embeddings
curl -H "Authorization: Bearer <jwt>" \
  "http://localhost:8000/api/v1/export/embeddings" \
  > all_embeddings.jsonl

# Export only question embeddings
curl -H "Authorization: Bearer <jwt>" \
  "http://localhost:8000/api/v1/export/embeddings?entity_type=question" \
  > question_embeddings.jsonl

# Export approved review pairs (for RLHF)
curl -H "Authorization: Bearer <jwt>" \
  "http://localhost:8000/api/v1/export/review-pairs?verdict=approved" \
  > approved_pairs.jsonl

# Export rejected review pairs (negative examples)
curl -H "Authorization: Bearer <jwt>" \
  "http://localhost:8000/api/v1/export/review-pairs?verdict=rejected" \
  > rejected_pairs.jsonl

# Export AI interaction logs (JSON)
curl -H "Authorization: Bearer <jwt>" \
  "http://localhost:8000/api/v1/ai-logs/export?format=json" \
  > ai_logs.json

# Export AI interaction logs (CSV)
curl -H "Authorization: Bearer <jwt>" \
  "http://localhost:8000/api/v1/ai-logs/export?format=csv" \
  > ai_logs.csv

# Count lines in an export (= number of records)
wc -l < training_data.jsonl
```

### Testing

```bash
# Run all backend tests
make test

# Run specific test file
docker compose exec api pytest tests/test_export.py -xvs

# Run tests matching a keyword
docker compose exec api pytest -k "backup or export" -xvs

# Frontend type check
docker compose exec web npx tsc -b --noEmit

# Run worker tests
docker compose exec worker python -m pytest tests/ -xvs
```

### Production Pre-Flight

```bash
# Validate environment variables (rejects defaults)
./scripts/check-env.sh

# Dry-run: preview resolved config
docker compose config

# Check log rotation is set on all services
docker compose config | grep -A3 "logging:"
```

### Configuration Reference

All database-related environment variables:

| Variable | Default | Where | What it controls |
|----------|---------|-------|-----------------|
| `DATABASE_URL` | `postgresql+asyncpg://app:devpassword@db:5432/knowledge_elicitation` | API | Full connection string |
| `DB_PASSWORD` | `devpassword` | DB, Backup | PostgreSQL password |
| `DB_POOL_SIZE` | `10` | API | Persistent connection count |
| `DB_MAX_OVERFLOW` | `20` | API | Extra connections under burst |
| `DB_POOL_PRE_PING` | `true` | API | Test connections before use |
| `DB_POOL_RECYCLE` | `3600` | API | Recycle connections after N seconds |
| `DB_HOST_PORT` | `5432` | Docker | Host-side port binding |
| `DB_USER` | `app` | Backup | PostgreSQL user (for backup sidecar) |
| `DB_NAME` | `knowledge_elicitation` | Backup | Database name (for backup sidecar) |
| `EMBEDDING_MODEL` | `` (disabled) | API | Embedding provider (empty = disabled) |
| `EMBEDDING_API_BASE` | `` | API | Embedding server URL |
| `EMBEDDING_API_KEY` | `` | API | Embedding API auth |
| `RECOMMENDATION_STRATEGY` | `auto` | API | `auto`, `llm`, or `embedding` |

### Quick Recipes

```bash
# "How big is my database?"
curl -s localhost:8000/health/db | jq '.database_size_bytes / 1048576 | round | tostring + " MB"'

# "When was my last backup?"
docker compose exec backup ls -lt /backups/backup_*.sql.gz | head -1

# "Is the backup sidecar running?"
docker compose ps backup

# "How many questions/answers do I have?"
curl -s localhost:8000/health/db | jq '.row_counts'

# "Is the connection pool healthy?"
curl -s localhost:8000/health/db | jq '.pool | "in:\(.checked_in) out:\(.checked_out) overflow:\(.overflow)"'

# "Export everything for ML training"
JWT="<admin-jwt>"
curl -H "Authorization: Bearer $JWT" localhost:8000/api/v1/export/training-data > training.jsonl
curl -H "Authorization: Bearer $JWT" localhost:8000/api/v1/export/embeddings > embeddings.jsonl
curl -H "Authorization: Bearer $JWT" localhost:8000/api/v1/export/review-pairs > reviews.jsonl
echo "Exported: $(wc -l < training.jsonl) Q&A pairs, $(wc -l < embeddings.jsonl) embeddings, $(wc -l < reviews.jsonl) review pairs"

# "Full database dump for offline analysis"
docker compose exec backup pg_dump -h db -U app -d knowledge_elicitation | gzip > full_dump_$(date +%Y%m%d).sql.gz
```
