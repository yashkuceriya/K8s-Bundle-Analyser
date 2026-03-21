.PHONY: dev dev-backend dev-frontend test test-backend test-frontend lint lint-backend lint-frontend build up down

# Development
dev:
	@echo "Starting backend and frontend..."
	$(MAKE) dev-backend &
	$(MAKE) dev-frontend

dev-backend:
	cd backend && source venv/bin/activate 2>/dev/null; uvicorn app.main:app --reload --port 8001

dev-frontend:
	cd frontend && npm run dev

# Testing
test: test-backend test-frontend

test-backend:
	cd backend && python -m pytest -v

test-frontend:
	cd frontend && npm test

# Linting
lint: lint-backend lint-frontend

lint-backend:
	cd backend && python -m ruff check . && python -m ruff format --check .

lint-frontend:
	cd frontend && npx eslint src/ && npx prettier --check "src/**/*.{ts,tsx,css}"

# Docker
build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down
