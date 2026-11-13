# Shortcuts for the Docker Compose workflow. Run `make help`.
COMPOSE_DEV  = docker compose --env-file .env -f infra/compose/docker-compose.yml -f infra/compose/docker-compose.dev.yml
COMPOSE_PROD = docker compose --env-file .env -f infra/compose/docker-compose.yml -f infra/compose/docker-compose.prod.yml

.PHONY: help env up down ps logs migrate test lint shell prod-config

help:          ## Show this help
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

env:           ## Create .env from .env.example (once)
	@test -f .env || cp .env.example .env

up: env        ## Build and start everything (dev)
	$(COMPOSE_DEV) up -d --build

down:          ## Stop everything (data volumes are kept)
	$(COMPOSE_DEV) down

ps:            ## Show services and their health
	$(COMPOSE_DEV) ps

logs:          ## Follow logs; one service: make logs s=api
	$(COMPOSE_DEV) logs -f $(s)

migrate:       ## Apply database migrations
	$(COMPOSE_DEV) run --rm migrate

test:          ## Run backend tests inside the container
	$(COMPOSE_DEV) run --rm api pytest

lint:          ## Lint and type-check the backend
	$(COMPOSE_DEV) run --rm api sh -c "ruff check . && ruff format --check . && mypy app && lint-imports"

shell:         ## Open a shell in the API container
	$(COMPOSE_DEV) exec api sh

prod-config:   ## Validate the production compose config
	$(COMPOSE_PROD) config --quiet
