.PHONY: install up down migrate revision run test check

install:
	uv sync
	uv run pre-commit install

up:
	docker compose up -d --wait

down:
	docker compose down

migrate:
	uv run alembic upgrade head

revision:
	uv run alembic revision --autogenerate -m "$(m)"

run:
	uv run fastapi dev src/fastapi_ecommerce_api/main.py

test:
	uv run pytest

check:
	uv run pre-commit run --all-files
