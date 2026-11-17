.PHONY: setup test lint dev groom-test groom-lint dashboard-test dashboard-lint e2e

# One-time setup: install dependencies for both components and enable the pre-commit guard.
# Run `nvm use` first so the Node version from .nvmrc (24, with npm 11) is active.
setup:
	git config core.hooksPath .githooks
	cd groom && uv sync
	cd dashboard && npm ci

test: groom-test dashboard-test

lint: groom-lint dashboard-lint

dev:
	cd dashboard && npm run dev

groom-test:
	cd groom && uv run pytest -q

groom-lint:
	cd groom && uv run ruff check . && uv run ruff format --check . && uv run mypy

dashboard-test:
	cd dashboard && npx vitest --run

dashboard-lint:
	cd dashboard && npm run lint && npm run check

e2e:
	cd dashboard && npx playwright test
