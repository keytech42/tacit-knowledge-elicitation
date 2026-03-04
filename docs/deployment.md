# Deployment

## Production Checklist

Before deploying to production, ensure the following:

### Security

- [ ] Set a strong random `JWT_SECRET` (at least 32 characters)
- [ ] Set a strong `DB_PASSWORD`
- [ ] Configure `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` for real OAuth
- [ ] Set `BOOTSTRAP_ADMIN_EMAIL` to the first admin's Google email
- [ ] Restrict `CORS_ORIGINS` to your production frontend domain
- [ ] Run PostgreSQL with TLS enabled
- [ ] Use HTTPS for all external traffic

### Database

- [ ] Use a managed PostgreSQL instance (not the Docker container)
- [ ] Set up automated backups
- [ ] Update `DATABASE_URL` to point to the production database

### Environment Variables

```bash
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/knowledge_elicitation
JWT_SECRET=<random-32-char-string>
JWT_EXPIRY_HOURS=24
GOOGLE_CLIENT_ID=<your-google-client-id>
GOOGLE_CLIENT_SECRET=<your-google-client-secret>
BOOTSTRAP_ADMIN_EMAIL=admin@yourcompany.com
CORS_ORIGINS=["https://your-domain.com"]
```

## Docker Compose (Staging)

The included `docker-compose.yml` works for staging with environment variable overrides:

```bash
DB_PASSWORD=strong-password \
JWT_SECRET=random-secret \
GOOGLE_CLIENT_ID=... \
GOOGLE_CLIENT_SECRET=... \
BOOTSTRAP_ADMIN_EMAIL=admin@example.com \
docker compose up -d
```

## Container-Based Deployment

For production, build and deploy the api and web containers separately.

### Backend

```dockerfile
# Build
docker build -t knowledge-api ./backend

# Run
docker run -d \
  -e DATABASE_URL=... \
  -e JWT_SECRET=... \
  -e GOOGLE_CLIENT_ID=... \
  -e GOOGLE_CLIENT_SECRET=... \
  -p 8000:8000 \
  knowledge-api \
  bash -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"
```

Remove `--reload` in production.

### Frontend

Build static assets and serve with any web server:

```bash
cd frontend
npm install
npm run build
# Serve the dist/ directory with nginx, caddy, etc.
```

Configure the web server to:
- Serve static files from `dist/`
- Proxy `/api/*` requests to the backend
- Return `index.html` for all non-file routes (SPA fallback)

## Migrations

Migrations run automatically before the API starts (`alembic upgrade head`). For manual control, remove the migration command from the container entrypoint and run it as a separate step in your deployment pipeline.

## Monitoring

- **Health check**: `GET /health` returns `{"status": "ok"}`
- **AI logs**: Admin users can view all service account interactions at `/admin/ai-logs`
- The AI logging middleware records all write operations from service accounts with latency, request body, and response status

## Scaling Considerations

- The backend is stateless — scale horizontally behind a load balancer
- JWT tokens are self-contained, no session store needed
- Database connections are pooled via SQLAlchemy's async engine
- Run migrations as a one-off task, not on every instance startup, when running multiple replicas
