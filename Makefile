.PHONY: up down test test-e2e migrate logs shell seed setup create-service-account \
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

# --- Embedding service ---

EMBEDDING_MODEL_DIR ?= ./models
EMBEDDING_MODEL_FILE ?= bge-m3-q8_0.gguf

embed-download:
	@mkdir -p $(EMBEDDING_MODEL_DIR)
	@if [ -f "$(EMBEDDING_MODEL_DIR)/$(EMBEDDING_MODEL_FILE)" ]; then \
		echo "Model already exists at $(EMBEDDING_MODEL_DIR)/$(EMBEDDING_MODEL_FILE)"; \
	else \
		echo "Downloading bge-m3 Q8_0 (~605MB)..."; \
		python3 -c " \
from huggingface_hub import hf_hub_download; \
hf_hub_download( \
    repo_id='ggml-org/bge-m3-Q8_0-GGUF', \
    filename='bge-m3-q8_0.gguf', \
    local_dir='$(EMBEDDING_MODEL_DIR)', \
); \
print('Done') \
"; \
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
