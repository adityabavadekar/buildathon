.PHONY: help install dev dev-backend dev-frontend test lint lint-backend lint-frontend \
        format format-backend format-frontend build check clean

BACKEND  := backend
FRONTEND := frontend

help: ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies for both services
	cd $(BACKEND) && uv sync --all-groups
	cd $(FRONTEND) && pnpm install

dev: ## Run both services (backend :8000, frontend :5173)
	./scripts/dev-up.sh

dev-backend: ## Run the backend only
	cd $(BACKEND) && uv run fastapi dev src/app/main.py --port 8000

dev-frontend: ## Run the frontend only
	cd $(FRONTEND) && pnpm dev --port 5173

worker: ## Run the recovery background worker daemon
	cd $(BACKEND) && uv run python -m app.worker.main

test: ## Run backend tests
	cd $(BACKEND) && uv run pytest

lint: lint-backend lint-frontend ## Lint and typecheck both services

lint-backend:
	cd $(BACKEND) && uv run ruff check .
	cd $(BACKEND) && uv run mypy

lint-frontend:
	cd $(FRONTEND) && pnpm lint
	cd $(FRONTEND) && pnpm typecheck

format: format-backend format-frontend ## Auto-format both services

format-check: ## Check formatting only (for pre-commit/release)
	cd $(BACKEND) && uv run ruff format --check .
	cd $(FRONTEND) && pnpm format:check

format-backend:
	cd $(BACKEND) && uv run ruff format .
	cd $(BACKEND) && uv run ruff check --fix .

format-frontend:
	cd $(FRONTEND) && pnpm format

build: ## Production build of the frontend
	cd $(FRONTEND) && pnpm build

check-backend: lint-backend test ## Fast backend-only lint + tests

check-frontend: lint-frontend ## Fast frontend-only lint + typecheck

check: lint test build ## Everything CI runs

clean: ## Remove caches and build output
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.mypy_cache $(BACKEND)/.ruff_cache
	rm -rf $(FRONTEND)/.next $(FRONTEND)/dist $(FRONTEND)/node_modules/.vite
	find . -type d -name __pycache__ -not -path '*/node_modules/*' -exec rm -rf {} +
