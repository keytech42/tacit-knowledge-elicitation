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

## Quick Setup

For a fire-and-go experience, use the interactive setup script:

```bash
git clone <repo-url>
cd tacit-knowledge-elicitation
make setup
```

This walks you through generating secrets, configuring optional services (AI, Slack, embeddings), creates the `.env` file, starts the stack, and sets up the worker service account — all interactively. Once done, proceed to [step 8 (reverse proxy)](#8-set-up-the-reverse-proxy) to expose the platform externally.

For a manual step-by-step walkthrough, continue below.

---

## Step-by-Step Deployment

### 1. Prerequisites

Install Docker and Docker Compose v2:

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in for group change to take effect
```

Other requirements:

- `git`, `make`, `curl` (pre-installed on most Linux distributions)
- Node.js 18+ (for building the frontend static files in [step 8](#8-set-up-the-reverse-proxy))
- A domain name with DNS pointing to the server
- (Optional) Google OAuth credentials for production auth
- (Optional) Anthropic API key for AI features
- (Optional) Slack app for notifications

> [!NOTE]
> Node.js is only needed to build the frontend. If you don't have it, the `setup-reverse-proxy` script can build via Docker instead.

### 2. Clone and configure

```bash
git clone <repo-url>
cd tacit-knowledge-elicitation
cp .env.example .env
```

Generate production secrets and set the minimum required values in `.env`:

```bash
# Generate strong secrets (copy these into .env)
openssl rand -hex 32   # → JWT_SECRET
openssl rand -hex 16   # → DB_PASSWORD
```

Update `.env`:

```bash
DB_PASSWORD=<generated-password>
DATABASE_URL=postgresql+asyncpg://app:<generated-password>@db:5432/knowledge_elicitation
JWT_SECRET=<generated-secret>
FRONTEND_URL=https://your-domain.com
CORS_ORIGINS=["https://your-domain.com"]
DEV_LOGIN_ENABLED=true   # Keep true for initial setup, disable in step 9
```

See [Environment Variables](#environment-variables) below for the full reference including optional services.

### 3. Start core services

```bash
make up-prod
```

This skips the `docker-compose.override.yml` (which adds dev-only features) and starts only the production services. Compared to `make up`:

- Runs in **detached mode** (`-d`)
- Removes `--reload` from API and worker (uses `--workers` instead)
- Binds all ports to **127.0.0.1** (only accessible from the server itself, not the internet)
- Removes source code volume mounts (uses code baked into the Docker image)
- Disables the `web` dev server (the reverse proxy serves static frontend files)
- Adds `restart: unless-stopped` so services survive reboots

On first run, database migrations execute automatically before the API starts.

> [!WARNING]
> **Do not use `make up` for production.** The dev compose exposes ports on all interfaces (0.0.0.0), which means the database, API, and worker are directly accessible from the internet — even if you have a firewall like UFW. Docker port mappings bypass iptables rules on Linux.

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

The worker authenticates to the API as a service account. The simplest way is the management script, which operates directly on the database — no JWT or browser login required:

```bash
docker compose exec api python scripts/create_service_account.py
```

This creates a service account with `author` and `reviewer` roles and prints the API key. Set it in `.env`:

```bash
WORKER_API_KEY=<the-printed-api-key>
```

Restart services to pick up the change:

```bash
make restart-prod
```

<details>
<summary>Alternative: create via the REST API (requires admin JWT)</summary>

During initial setup, dev-login is enabled by default. Use it to get an admin token:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/dev-login \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -s -X POST http://localhost:8000/api/v1/service-accounts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"display_name": "LLM Worker", "model_id": "claude-sonnet-4-6", "roles": ["author", "reviewer"]}'
```

In production (dev-login disabled), get the admin JWT from the browser:
1. Log in via Google OAuth
2. Open browser DevTools → Application → Local Storage
3. Copy the `access_token` value

</details>

> [!TIP]
> The management script works regardless of `DEV_LOGIN_ENABLED` — use it to create or rotate service accounts in production without needing a browser.

> [!NOTE]
> The dev-login endpoint (`POST /api/v1/auth/dev-login`) is only available when `DEV_LOGIN_ENABLED=true` (the default). It creates a test admin user (`dev@localhost`) with all roles. Use it during initial setup if you prefer the REST API path, then disable it in step 9. After that, admin access is via Google OAuth — the user whose email matches `BOOTSTRAP_ADMIN_EMAIL` auto-receives all roles on first login.

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

Restart with embeddings enabled:

```bash
docker compose -f docker-compose.yml --profile embedding up -d --build db api worker embedding
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

5. Restart the API: `make restart-prod`

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

> [!TIP]
> **Automated setup available:** Run `make setup-reverse-proxy` (or `bash scripts/setup-reverse-proxy.sh`) to interactively install and configure the reverse proxy. The script handles package installation, frontend build, TLS certificates, and `.env` updates. The manual steps below are for reference or custom setups.

A reverse proxy sits between the internet and your Docker services. It handles TLS (HTTPS), serves the frontend static files, and forwards API requests to the backend. This platform uses SSE (Server-Sent Events) for real-time updates, which requires specific proxy configuration.

#### 8a. Build the frontend

The frontend is a React SPA (Single Page Application). Build it into static files:

```bash
cd frontend
npm install
npm run build
```

This produces a `dist/` directory containing `index.html` and bundled JS/CSS assets. The reverse proxy will serve these directly.

#### 8b. Prerequisites

- Your server's domain name (e.g., `knowledge.yourcompany.com`) must have a DNS A record pointing to the server's IP address
- Ports 80 and 443 must be open in your firewall

Verify DNS is set up:

```bash
dig +short knowledge.yourcompany.com
# Should return your server's IP address
```

#### 8c. Choose a reverse proxy

We provide configurations for two options. **Caddy is recommended for first-time setup** — it automatically obtains and renews TLS certificates from Let's Encrypt with zero configuration.

<details open>
<summary><strong>Option A: Caddy (recommended — automatic TLS)</strong></summary>

**Install Caddy:**

```bash
# Ubuntu/Debian
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

**Configure Caddy:**

Create `/etc/caddy/Caddyfile`:

```
knowledge.yourcompany.com {
    # Frontend static files
    root * /path/to/frontend/dist
    file_server

    # API proxy (includes SSE — Caddy handles streaming automatically)
    handle /api/* {
        reverse_proxy localhost:8000
    }

    # Health check proxy
    handle /health {
        reverse_proxy localhost:8000
    }

    # SPA fallback — serve index.html for all non-file routes
    try_files {path} /index.html
}
```

Replace `knowledge.yourcompany.com` with your domain and `/path/to/frontend/dist` with the actual path to the built frontend.

**Start Caddy:**

```bash
sudo systemctl enable caddy
sudo systemctl restart caddy
```

Caddy automatically obtains a TLS certificate from Let's Encrypt on first request. No manual certificate management needed.

**Verify:**

```bash
curl -I https://knowledge.yourcompany.com
# Should return HTTP/2 200 with a valid TLS certificate
```

> [!NOTE]
> Caddy handles SSE correctly out of the box — no additional buffering or timeout configuration needed. It automatically detects streaming responses and disables buffering.

</details>

<details>
<summary><strong>Option B: nginx (manual TLS setup)</strong></summary>

**Install nginx:**

```bash
# Ubuntu/Debian
sudo apt install nginx
```

**Obtain a TLS certificate:**

Use [Certbot](https://certbot.eff.org/) (free, from Let's Encrypt):

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d knowledge.yourcompany.com
```

Certbot will obtain the certificate and update the nginx config with the paths. Note the certificate paths it prints (typically `/etc/letsencrypt/live/knowledge.yourcompany.com/`).

**Configure nginx:**

Create `/etc/nginx/sites-available/knowledge-elicitation`:

```nginx
server {
    listen 443 ssl http2;
    server_name knowledge.yourcompany.com;

    ssl_certificate /etc/letsencrypt/live/knowledge.yourcompany.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/knowledge.yourcompany.com/privkey.pem;

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

    # Health check proxy
    location = /health {
        proxy_pass http://127.0.0.1:8000;
    }

    # SPA fallback — serve index.html for all non-file routes
    location / {
        try_files $uri $uri/ /index.html;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name knowledge.yourcompany.com;
    return 301 https://$host$request_uri;
}
```

**Enable the site and restart:**

```bash
sudo ln -s /etc/nginx/sites-available/knowledge-elicitation /etc/nginx/sites-enabled/
sudo nginx -t          # test configuration — must show "syntax is ok"
sudo systemctl restart nginx
```

**Set up automatic certificate renewal:**

```bash
# Certbot adds a systemd timer automatically. Verify it's active:
sudo systemctl status certbot.timer
```

> [!IMPORTANT]
> **SSE requires `proxy_buffering off`** on the `/api/` location. Without it, nginx buffers the event stream and the client receives nothing until the connection closes. The `proxy_read_timeout` should be long (e.g., 3600s) because SSE connections are persistent.

</details>

#### 8d. Verify the deployment

After the reverse proxy is running:

```bash
# TLS and frontend
curl -I https://knowledge.yourcompany.com
# Should return HTTP/2 200

# API through the proxy
curl https://knowledge.yourcompany.com/api/v1/auth/config
# Should return JSON with auth configuration

# SSE connectivity (should hang with an open connection, receiving events)
curl -N https://knowledge.yourcompany.com/api/v1/questions/00000000-0000-0000-0000-000000000000/events?token=test
# Expected: HTTP 401 (auth error) — confirms the SSE endpoint is reachable
```

Open `https://knowledge.yourcompany.com` in a browser. You should see the login page.

### 9. Disable development mode

In `.env`, ensure:

```bash
DEV_LOGIN_ENABLED=false
CORS_ORIGINS=["https://your-domain.com"]
FRONTEND_URL=https://your-domain.com
```

Then restart:

```bash
make restart-prod
```

> [!NOTE]
> If you used `make up-prod` (step 3), the `--reload` flags and source code mounts are already excluded (they live in `docker-compose.override.yml`, which production skips). No manual edits needed.

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

- [ ] Using `make up-prod` (not `make up`) — ports bound to 127.0.0.1, no `--reload`, restart policies
- [ ] Strong random `JWT_SECRET` (at least 32 characters)
- [ ] Strong `DB_PASSWORD`
- [ ] `DEV_LOGIN_ENABLED=false`
- [ ] `CORS_ORIGINS` restricted to production domain
- [ ] `FRONTEND_URL` set to production domain (used in Slack links and OAuth)
- [ ] HTTPS with valid TLS certificate
- [ ] Google OAuth configured (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`)
- [ ] `BOOTSTRAP_ADMIN_EMAIL` set to first admin's Google email
- [ ] PostgreSQL with automated backups
- [ ] Reverse proxy configured with SSE support (`proxy_buffering off` for nginx)
- [ ] Service account created for worker with `WORKER_API_KEY` set
- [ ] `ANTHROPIC_API_KEY` set (if using AI features)
- [ ] Slack app created and tokens set (if using notifications)
- [ ] Embedding model downloaded and service started (if using embedding strategy)
