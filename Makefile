.PHONY: up down test test-e2e migrate logs shell

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
