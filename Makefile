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
	uv run fastapi dev src/ecommerce/main.py

test:
	uv run pytest --cov

check:
	uv run pre-commit run --all-files
