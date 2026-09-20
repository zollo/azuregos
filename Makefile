.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: init
init: ## Copy .env.example to .env if missing
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")

.PHONY: up
up: init ## Start the full stack (dev mode w/ hot reload)
	$(COMPOSE) up --build

.PHONY: up-d
up-d: init ## Start the full stack detached
	$(COMPOSE) up --build -d

.PHONY: down
down: ## Stop the stack
	$(COMPOSE) down

.PHONY: clean
clean: ## Stop and remove volumes (DESTROYS data)
	$(COMPOSE) down -v

.PHONY: logs
logs: ## Tail all logs
	$(COMPOSE) logs -f

.PHONY: migrate
migrate: ## Run DB migrations inside the backend container
	$(COMPOSE) exec backend alembic upgrade head

.PHONY: makemigration
makemigration: ## Autogenerate a migration: make makemigration m="message"
	$(COMPOSE) exec backend alembic revision --autogenerate -m "$(m)"

.PHONY: backend-test
backend-test: ## Run backend tests
	$(COMPOSE) exec backend pytest -q

.PHONY: backend-lint
backend-lint: ## Lint + format-check the backend
	$(COMPOSE) exec backend ruff check .

.PHONY: frontend-test
frontend-test: ## Run frontend tests
	$(COMPOSE) exec frontend npm test

.PHONY: shell
shell: ## Open a shell in the backend container
	$(COMPOSE) exec backend sh
