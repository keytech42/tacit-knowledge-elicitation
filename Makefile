.PHONY: up down test test-e2e migrate logs shell seed setup create-service-account \
       setup-reverse-proxy up-prod down-prod logs-prod restart-prod \
       up-embed down-embed embed-download embed-status

# --- Setup ---

setup:
	@bash scripts/setup.sh

# --- Core services ---

up:
	docker compose up --build

down:
	docker compose down

test:
	docker compose exec api pytest -xvs

migrate:
	docker compose exec api alembic upgrade head

logs:
	docker compose logs -f

test-e2e:
	docker compose up -d db api web
	cd frontend && npx playwright test

shell:
	docker compose exec api bash

seed:
	docker compose exec api python scripts/seed.py

create-service-account:
	docker compose exec api python scripts/create_service_account.py

setup-reverse-proxy:
	@bash scripts/setup-reverse-proxy.sh

# --- Production ---

COMPOSE_PROD := docker compose -f docker-compose.yml

up-prod:
	$(COMPOSE_PROD) up -d --build db api worker

down-prod:
	$(COMPOSE_PROD) down

logs-prod:
	$(COMPOSE_PROD) logs -f

restart-prod:
	$(COMPOSE_PROD) restart

# --- Embedding service ---

EMBEDDING_MODEL_DIR ?= ./models
EMBEDDING_MODEL_FILE ?= bge-m3-q8_0.gguf
EMBEDDING_HF_REPO ?= ggml-org/bge-m3-Q8_0-GGUF

embed-download:
	@mkdir -p $(EMBEDDING_MODEL_DIR)
	@if [ -f "$(EMBEDDING_MODEL_DIR)/$(EMBEDDING_MODEL_FILE)" ]; then \
		echo "Model already exists at $(EMBEDDING_MODEL_DIR)/$(EMBEDDING_MODEL_FILE)"; \
	else \
		echo "Downloading bge-m3 Q8_0 (~605MB)..."; \
		curl -L --progress-bar \
			-o "$(EMBEDDING_MODEL_DIR)/$(EMBEDDING_MODEL_FILE)" \
			"https://huggingface.co/$(EMBEDDING_HF_REPO)/resolve/main/$(EMBEDDING_MODEL_FILE)"; \
		echo "Done: $(EMBEDDING_MODEL_DIR)/$(EMBEDDING_MODEL_FILE)"; \
	fi

up-embed:
	@if [ ! -f "$(EMBEDDING_MODEL_DIR)/$(EMBEDDING_MODEL_FILE)" ]; then \
		echo "Error: Model not found at $(EMBEDDING_MODEL_DIR)/$(EMBEDDING_MODEL_FILE)"; \
		echo "Run 'make embed-download' first."; \
		exit 1; \
	fi
	docker compose --profile embedding up --build

down-embed:
	docker compose --profile embedding down

embed-status:
	@printf "Embedding service: "
	@curl -sf http://localhost:$${EMBEDDING_HOST_PORT:-8090}/health \
		&& echo " healthy" \
		|| echo " not running"
