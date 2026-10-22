.PHONY: setup up seed migrate test test-unit test-integration test-browser lint down reset

setup: up seed

up:
	docker compose up --build -d --wait

seed:
	docker compose exec api python -m app.seed

migrate:
	docker compose run --rm migrate

test:
	docker compose --profile test run --build --rm tests

test-unit:
	docker compose --profile test run --build --rm tests pytest -q -m "not integration"

test-integration:
	docker compose --profile test run --build --rm tests pytest -q -m integration

test-browser:
	cd frontend && npm ci && npx playwright install chromium && E2E_BASE_URL=http://localhost:8080 npm run test:e2e

lint:
	docker compose run --rm --no-deps api ruff check .
	docker compose run --rm --no-deps api ruff format --check .
	cd frontend && npm ci && npm run format:check && npm run build

down:
	docker compose --profile test down

# DESTRUCTIVE: development data only; explicitly invoked by the developer.
reset:
	docker compose --profile test down --volumes
	$(MAKE) setup
