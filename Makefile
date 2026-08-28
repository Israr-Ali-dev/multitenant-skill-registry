.PHONY: up down build logs migrate seed demo test test-local lint fmt

up: ## Start postgres, run migrations, seed fixtures, start the API
	docker compose up --build migrate seed
	docker compose up --build -d api
	@echo "API running at http://localhost:8000  (docs: /docs, health: /health)"

down:
	docker compose down -v

build:
	docker compose build

logs:
	docker compose logs -f api

migrate:
	docker compose run --rm migrate

seed:
	docker compose run --rm seed

demo: ## Run the required end-to-end workflow against a running API
	bash scripts/demo_workflow.sh

test: ## Run the full test suite inside a disposable container against a disposable db
	docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test

lint:
	ruff check app tests scripts
	mypy app

fmt:
	ruff check --fix app tests scripts
	ruff format app tests scripts
