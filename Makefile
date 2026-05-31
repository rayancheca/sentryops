SHELL := /bin/bash
DC := docker compose
.DEFAULT_GOAL := help

.PHONY: help env up down build logs ps restart migrate makemigration seed demo \
        test test-backend test-frontend cov lint fmt typecheck capture clean nuke

env: ## Create .env from .env.example if it does not exist
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")

up: env ## Build and start the full stack (postgres, redis, api, worker, web)
	$(DC) up -d --build
	@echo "API docs -> http://localhost:8000/docs"
	@echo "Web      -> http://localhost:3000"

down: ## Stop the stack
	$(DC) down

build: env ## Build all images
	$(DC) build

logs: ## Tail service logs
	$(DC) logs -f --tail=120

ps: ## Show running services
	$(DC) ps

restart: ## Restart api + worker
	$(DC) restart api worker

migrate: ## Apply database migrations
	$(DC) exec api alembic upgrade head

makemigration: ## Autogenerate a migration:  make makemigration m="add table"
	$(DC) exec api alembic revision --autogenerate -m "$(m)"

seed: ## Load demo data (assets, dependency graph, services, violations, incidents, seeded AI triage)
	$(DC) exec api python -m scripts.seed

demo: up ## One command: bring the stack up and seed it so dashboards look alive
	@echo "Waiting for the API to become healthy..."
	@for i in $$(seq 1 45); do curl -sf http://localhost:8000/health >/dev/null && break || sleep 2; done
	$(DC) exec api python -m scripts.seed
	@echo ""
	@echo "SentryOps is live and seeded:"
	@echo "  Dashboard : http://localhost:3000"
	@echo "  API docs  : http://localhost:8000/docs"
	@echo "  Login     : admin@sentryops.local / admin12345   (read-only: viewer@sentryops.local / viewer12345)"

test: test-backend test-frontend ## Run all tests

test-backend: ## Run backend tests with coverage
	$(DC) exec api pytest -q --cov=app --cov-report=term-missing

test-frontend: ## Run frontend unit tests
	cd web && pnpm test run

cov: ## Backend coverage HTML report
	$(DC) exec api pytest --cov=app --cov-report=html

lint: ## Lint backend + frontend
	cd backend && ruff check . && black --check .
	cd web && pnpm lint

fmt: ## Auto-format backend + frontend
	cd backend && ruff check --fix . && black .
	cd web && pnpm format

typecheck: ## Static type checks (mypy strict + tsc)
	cd backend && mypy app
	cd web && pnpm typecheck

capture: ## Capture demo screenshots + GIF with Playwright (stack must be seeded)
	cd web && pnpm exec playwright test capture.spec.ts

clean: ## Remove local caches and build artifacts
	@find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@rm -rf backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache web/.next web/coverage

nuke: ## Stop the stack and DELETE all volumes (destroys data)
	$(DC) down -v

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
