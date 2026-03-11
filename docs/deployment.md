# Deployment

This guide covers deploying the Knowledge Elicitation Platform on a dedicated server using Docker Compose. For development setup, see [Development Guide](development.md).

## Architecture Overview

The platform runs as five Docker Compose services:

| Service | Image | Internal Port | Exposed | Profile |
|---------|-------|---------------|---------|---------|
| **db** | pgvector/pgvector:pg16 | 5432 | Optional | default |
| **api** | ./backend | 8000 | Via reverse proxy | default |
| **web** | ./frontend (dev only) | 5173 | — | default |
| **worker** | ./worker | 8001 | No | default |
| **embedding** | ghcr.io/ggml-org/llama.cpp:server | 8090 | No | `embedding` |

In production, the **web** service is replaced by static files served from a reverse proxy (nginx/caddy). The **worker** and **embedding** services are optional — the platform functions fully without them.

## Step-by-Step Deployment

### 1. Prerequisites

- Docker and Docker Compose v2
- A domain name with DNS pointing to the server
- A reverse proxy with TLS termination (nginx, caddy, or similar)
- (Optional) Google OAuth credentials for production auth
- (Optional) Anthropic API key for AI features
- (Optional) Slack app for notifications

### 2. Clone and configure

```bash
git clone <repo-url>
cd tacit-knowledge-elicitation
cp .env.example .env
```

Edit `.env` with production values. See [Environment Variables](#environment-variables) below for the full reference.

### 3. Start core services

```bash
make up
```

This starts `db`, `api`, `web`, and `worker`. On first run, migrations execute automatically before the API starts.

Verify the API is running:

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

### 4. Seed initial data (optional)

```bash
make seed
```

Creates 5 sample users and 5 questions in varied states — useful for verifying the deployment works end-to-end before configuring real accounts.

### 5. Create a service account for the worker

The worker authenticates to the API as a service account. Log in as admin, then:

```bash
curl -X POST http://localhost:8000/api/v1/service-accounts \
  -H "Authorization: Bearer <admin-jwt>" \
  -H "Content-Type: application/json" \
  -d '{"display_name": "LLM Worker", "model_id": "claude-sonnet-4-6", "roles": ["author", "reviewer"]}'
```

Copy the returned `api_key` and set it in `.env`:

```bash
WORKER_API_KEY=<the-returned-api-key>
```

Restart services to pick up the change:

```bash
docker compose restart worker api
```

### 6. Enable embeddings (optional)

> [!NOTE]
> Embeddings are entirely optional. If you prefer LLM-based recommendations (no local inference needed), set `RECOMMENDATION_STRATEGY=llm` in `.env` and skip this step.

> [!WARNING]
> The `embedding` Docker Compose service runs **CPU-only inference**. This is sufficient for typical workloads (a few embeddings per minute) and well-suited for servers without a GPU. If you have a GPU available, see [Embeddings Setup — GPU Alternatives](embeddings.md#gpu-alternatives) for CUDA, Metal, ROCm, and cloud options.

```bash
make embed-download    # download bge-m3 Q8_0 (~605MB, one-time)
```

Add to `.env`:

```bash
EMBEDDING_MODEL=openai/bge-m3
EMBEDDING_API_BASE=http://embedding:8090/v1/
EMBEDDING_API_KEY=no-key
```

Start all services including embeddings:

```bash
make up-embed
```

Verify:

```bash
make embed-status
# Embedding service:  healthy
```

See [Embeddings Setup](embeddings.md) for the full guide including GPU alternatives, cloud providers, and troubleshooting.

### 7. Configure Slack notifications (optional)

1. Create a Slack app at https://api.slack.com/apps
2. Add Bot Token Scopes: `chat:write`, `users:read`, `users:read.email`, `conversations:open`
3. Install the app to your workspace
4. Add to `.env`:

```bash
SLACK_BOT_TOKEN=xoxb-<your-token>
SLACK_DEFAULT_CHANNEL=#knowledge-elicitation
FRONTEND_URL=https://your-domain.com
```

5. Restart the API: `docker compose restart api`

Slack notifications are fire-and-forget — if the token is invalid or the service is unreachable, the API continues normally without blocking.

**What gets notified:**

| Event | Channel | DM |
|-------|---------|-----|
| Question published | Default channel (thread created) | — |
| Answer submitted | Question thread | — |
| Reviewer assigned | — | Assigned reviewer |
| Review verdict | Question thread | Author (if changes requested) |
| Respondent assigned | — | Assigned respondent |

### 8. Set up the reverse proxy

The API serves both the REST endpoints and SSE (Server-Sent Events) connections. Your reverse proxy must handle both.

Example nginx configuration:

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # Frontend static files
    root /path/to/frontend/dist;
    index index.html;

    # API and SSE proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE support — disable buffering and set long timeouts
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    # SPA fallback — all non-file routes serve index.html
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

> [!IMPORTANT]
> **SSE requires `proxy_buffering off`** on the `/api/` location. Without it, nginx buffers the event stream and the client receives nothing until the connection closes. The `proxy_read_timeout` should be long (e.g., 3600s) because SSE connections are persistent.

Build the frontend static files:

```bash
cd frontend
npm install
npm run build
# Copy dist/ to the path configured in nginx
```

### 9. Disable development mode

In `.env`, ensure:

```bash
DEV_LOGIN_ENABLED=false
CORS_ORIGINS=["https://your-domain.com"]
```

Remove `--reload` from the API and worker commands if you're overriding the default entrypoint.

## Environment Variables

### Core (required)

| Variable | Example | Notes |
|----------|---------|-------|
| `DATABASE_URL` | `postgresql+asyncpg://app:password@db:5432/knowledge_elicitation` | Must use `asyncpg` driver |
| `JWT_SECRET` | `<random-32-char-string>` | Generate with `openssl rand -hex 32` |
| `DB_PASSWORD` | `<strong-password>` | Used by the `db` service |
| `CORS_ORIGINS` | `["https://your-domain.com"]` | JSON array of allowed origins |
| `DEV_LOGIN_ENABLED` | `false` | **Must be `false` in production** |

### Authentication

| Variable | Example | Notes |
|----------|---------|-------|
| `GOOGLE_CLIENT_ID` | `<client-id>.apps.googleusercontent.com` | From Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | `GOCSPX-...` | Keep secret |
| `GOOGLE_REDIRECT_URI` | `https://your-domain.com/auth/callback` | Must match GCP config |
| `BOOTSTRAP_ADMIN_EMAIL` | `admin@yourcompany.com` | First user with this email auto-receives all roles |

### AI / Worker (optional)

| Variable | Default | Notes |
|----------|---------|-------|
| `WORKER_URL` | `http://worker:8001` | Empty = AI features disabled |
| `WORKER_API_KEY` | — | Service account API key (see step 5) |
| `ANTHROPIC_API_KEY` | — | Required for Anthropic models |
| `LLM_MODEL` | `anthropic/claude-sonnet-4-6` | Worker's primary LLM |
| `RECOMMENDATION_STRATEGY` | `auto` | `auto`, `llm`, or `embedding` |
| `RECOMMENDATION_MODEL` | `anthropic/claude-haiku-4-5-20251001` | Cost-efficient scoring model |
| `DEDUP_STRATEGY` | `llm` | `llm` or `embedding` (for question extraction) |
| `EXTRACTION_AUTO_SUBMIT` | `false` | Auto-submit extracted questions as draft |

### Embeddings (optional)

| Variable | Default | Notes |
|----------|---------|-------|
| `EMBEDDING_MODEL` | — (disabled) | `openai/bge-m3` (local) or `text-embedding-3-small` (cloud) |
| `EMBEDDING_API_BASE` | — | `http://embedding:8090/v1/` (compose) or cloud URL |
| `EMBEDDING_API_KEY` | — | `no-key` for local; actual key for cloud |
| `EMBEDDING_MODEL_DIR` | `./models` | Host path to GGUF files |
| `EMBEDDING_MODEL_FILE` | `bge-m3-q8_0.gguf` | Filename within model dir |

### Slack (optional)

| Variable | Default | Notes |
|----------|---------|-------|
| `SLACK_BOT_TOKEN` | — (disabled) | `xoxb-...` from Slack app settings |
| `SLACK_DEFAULT_CHANNEL` | — | Channel ID or `#name` for broadcast notifications |
| `FRONTEND_URL` | `http://localhost:5173` | Used in Slack notification links |

## Database

### PostgreSQL requirements

- **Image**: `pgvector/pgvector:pg16` (drop-in replacement for `postgres:16` with the `vector` extension)
- The `vector` extension is created automatically by the first migration
- If using a managed PostgreSQL instance, ensure the `pgvector` extension is available

### Migrations

Migrations run automatically before the API starts (`alembic upgrade head` in the compose command). For manual control:

```bash
make migrate
# or
docker compose exec api alembic upgrade head
```

When running multiple API replicas, run migrations as a **one-off task** before starting instances — not on every replica startup.

### Backups

For production, use a managed PostgreSQL instance with automated backups. If using the Docker container:

```bash
docker compose exec db pg_dump -U app knowledge_elicitation > backup.sql
```

## Monitoring

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Returns `{"status": "ok"}` — use for liveness probes |
| `GET /admin/ai-logs` | AI operation logs (admin UI) |

The AI logging middleware records all write operations from service accounts with latency, request body, and response status.

### Embedding service health

```bash
make embed-status
# or
curl http://localhost:8090/health
```

## Scaling

| Component | Scalable? | Notes |
|-----------|-----------|-------|
| **api** | Horizontal | Stateless — scale behind a load balancer |
| **worker** | No | In-memory task tracking — single instance only |
| **embedding** | No | Single llama-server process per model |
| **db** | Vertical | Use managed PostgreSQL for read replicas |

- JWT tokens are self-contained — no session store needed
- Database connections are pooled via SQLAlchemy's async engine
- SSE connections are persistent — account for connection limits when sizing the API instances (one connection per open QuestionDetail page)

## Production Checklist

- [ ] Strong random `JWT_SECRET` (at least 32 characters)
- [ ] Strong `DB_PASSWORD`
- [ ] `DEV_LOGIN_ENABLED=false`
- [ ] `CORS_ORIGINS` restricted to production domain
- [ ] HTTPS with valid TLS certificate
- [ ] Google OAuth configured (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`)
- [ ] `BOOTSTRAP_ADMIN_EMAIL` set to first admin's Google email
- [ ] PostgreSQL with TLS and automated backups
- [ ] Reverse proxy configured with SSE support (`proxy_buffering off`)
- [ ] Service account created for worker with `WORKER_API_KEY` set
- [ ] `ANTHROPIC_API_KEY` set (if using AI features)
- [ ] `--reload` removed from API and worker commands
- [ ] Slack app created and tokens set (if using notifications)
- [ ] Embedding model downloaded and service started (if using embedding strategy)
- [ ] `FRONTEND_URL` set to production domain (used in Slack links and emails)
