.PHONY: bootstrap up migrate seed dev test lint e2e down

bootstrap:
	cd apps/api && uv sync
	cd apps/web && pnpm install

up:
	docker compose up -d db

migrate:
	cd apps/api && uv run alembic upgrade head

seed:
	cd apps/api && uv run python -m scripts.seed_demo

dev:
	cd apps/api && uv run uvicorn app.main:app --reload --port 8000 &
	cd apps/web && pnpm dev

test:
	cd apps/api && uv run pytest
	cd apps/web && pnpm test

lint:
	cd apps/api && uv run ruff check . && uv run mypy app
	cd apps/web && pnpm lint

e2e:
	cd apps/api && uv run pytest tests/e2e

down:
	docker compose down
