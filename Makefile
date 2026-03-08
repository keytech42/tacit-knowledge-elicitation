.PHONY: up down test migrate logs shell seed

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

shell:
	docker compose exec api bash

seed:
	docker compose exec api python scripts/seed.py
