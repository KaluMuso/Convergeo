.PHONY: dev build lint typecheck test format verify-scaffold api-lint api-test api-typecheck

dev:
	pnpm dev

build:
	pnpm build

lint:
	pnpm lint

typecheck:
	pnpm typecheck

test:
	pnpm test

format:
	pnpm format

verify-scaffold:
	pnpm verify-scaffold

# Python API tooling (uv wiring lands in M01-P03)
api-lint:
	@echo "API lint: uv run ruff check (available after M01-P03)"

api-test:
	@echo "API test: uv run pytest (available after M01-P03)"

api-typecheck:
	@echo "API typecheck: uv run mypy (available after M01-P03)"
