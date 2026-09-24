# Inland Resilience Agent: developer commands.
# Section 7 owns this file and will add `dev`, `migrate`, `seed`, etc.; the lead added the data-pipeline targets.

WORKER := apps/worker
ENVFILE := $(if $(wildcard .env),--env-file ../../.env,)

.PHONY: docker-build docker-test docker-test-live docker-fetch help worker-install test-worker test-live lint-worker format-worker validate-contracts \
        test-connector record-fixture derive-fixtures new-connector

help:            ## list commands
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-20s %s\n", $$1, $$2}'

worker-install:  ## install the worker's Python deps (uv)
	cd $(WORKER) && uv sync

test-worker:     ## all offline worker tests (no keys, no network)
	cd $(WORKER) && uv run pytest

test-live:       ## real calls to real providers (keys from .env)
	cd $(WORKER) && uv run $(ENVFILE) pytest -m live -s tests/live

lint-worker:     ## ruff lint + format check
	cd $(WORKER) && uv run ruff check . && uv run ruff format --check .

format-worker:   ## auto-format worker code
	cd $(WORKER) && uv run ruff check --fix . && uv run ruff format .

validate-contracts: ## check contracts/ (schemas, OpenAPI, examples)
	cd $(WORKER) && uv run pytest tests/test_contracts.py

test-connector:  ## shared suite + tests for one provider: make test-connector PROVIDER=firms
	cd $(WORKER) && uv run pytest tests/connectors/test_$(PROVIDER).py

record-fixture:  ## record a live fixture: make record-fixture PROVIDER=firms CASE=success ARGS="--area sb_county_bbox"
	cd $(WORKER) && uv run $(ENVFILE) python scripts/record_fixture.py $(PROVIDER) $(CASE) $(ARGS)

derive-fixtures: ## derive malformed/extra_fields (+empty): make derive-fixtures PROVIDER=firms ARGS="--empty-csv"
	cd $(WORKER) && uv run python scripts/derive_fixtures.py $(PROVIDER) $(ARGS)

new-connector:   ## copy a reference: make new-connector NAME=cimis GROUP=weather PATTERN=keyed
	cd $(WORKER) && uv run python scripts/new_connector.py --name $(NAME) --group $(GROUP) --pattern $(PATTERN)

# --- Docker: identical environment on any machine (needs Docker Desktop) -------------------------
COMPOSE := docker compose -f infrastructure/docker-compose.yml

docker-build:    ## build the worker image
	$(COMPOSE) build worker

docker-test:     ## offline tests inside the container
	$(COMPOSE) run --rm --build worker-test

docker-test-live: ## live provider tests inside the container (keys from .env)
	$(COMPOSE) run --rm --build worker-test -m live -s tests/live

docker-fetch:    ## fetch one provider in the container: make docker-fetch PROVIDER=wfigs_current ARGS="--bbox -124.5,32.5,-114.1,42.0"
	$(COMPOSE) run --rm --build worker fetch $(PROVIDER) $(ARGS)
