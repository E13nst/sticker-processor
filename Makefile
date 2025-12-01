.PHONY: help install install-dev test test-unit test-integration test-cov clean lint format run-dev run-prod

# Variables
VENV = venv/bin
PYTHON = $(VENV)/python3.13
PYTEST = $(VENV)/pytest
PIP = $(VENV)/pip

help:
	@echo "Sticker Processor Service - Makefile Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install         Install production dependencies"
	@echo "  make install-dev     Install development dependencies"
	@echo ""
	@echo "Testing:"
	@echo "  make test            Run all tests"
	@echo "  make test-unit       Run only unit tests"
	@echo "  make test-integration Run only integration tests"
	@echo "  make test-cov        Run tests with coverage report"
	@echo "  make test-watch      Run tests in watch mode"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint            Run linters (flake8, mypy)"
	@echo "  make format          Format code (black, isort)"
	@echo "  make check-format    Check if code is formatted"
	@echo ""
	@echo "Running:"
	@echo "  make run-dev         Run service in development mode"
	@echo "  make run-prod        Run service in production mode"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean           Clean cache files and test artifacts"
	@echo "  make redis-local     Start local Redis with Docker"

# Setup
install:
	$(PIP) install -r requirements.txt

install-dev:
	$(PIP) install -r requirements-dev.txt

# Testing
test:
	$(PYTEST) -v

test-unit:
	$(PYTEST) -v -m unit

test-integration:
	$(PYTEST) -v -m integration

test-redis:
	$(PYTEST) -v -m redis

test-cov:
	$(PYTEST) --cov=app --cov-report=html --cov-report=term-missing
	@echo ""
	@echo "Coverage report generated in htmlcov/index.html"
	@echo "Open with: open htmlcov/index.html"

test-watch:
	$(PYTEST) -f

test-failed:
	$(PYTEST) --lf -v

# Code Quality
lint:
	@echo "Running flake8..."
	-$(VENV)/flake8 app tests
	@echo ""
	@echo "Running mypy..."
	-$(VENV)/mypy app

format:
	@echo "Running black..."
	$(VENV)/black app tests
	@echo ""
	@echo "Running isort..."
	$(VENV)/isort app tests

check-format:
	@echo "Checking black..."
	$(VENV)/black --check app tests
	@echo ""
	@echo "Checking isort..."
	$(VENV)/isort --check app tests

# Running
run-dev:
	$(PYTHON) -m uvicorn app.main:app --host 127.0.0.1 --port 8081 --reload

run-prod:
	$(VENV)/gunicorn app.main:app \
		--workers 4 \
		--worker-class uvicorn.workers.UvicornWorker \
		--bind 0.0.0.0:8081 \
		--timeout 120 \
		--keepalive 5

# Utilities
clean:
	@echo "Cleaning cache files..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage.*" -delete
	@echo "Clean complete!"

redis-local:
	@echo "Starting local Redis..."
	docker run -d -p 6379:6379 --name sticker-redis redis:7-alpine
	@echo "Redis running on localhost:6379"
	@echo "Stop with: docker stop sticker-redis"
	@echo "Remove with: docker rm sticker-redis"

redis-stop:
	docker stop sticker-redis || true
	docker rm sticker-redis || true

# Docker
docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f sticker-processor

docker-test:
	docker-compose run --rm sticker-processor pytest

# Health checks
health:
	@curl -s http://localhost:8081/health | python3 -m json.tool

stats:
	@curl -s http://localhost:8081/api/stats | python3 -m json.tool

cache-stats:
	@curl -s http://localhost:8081/cache/stats | python3 -m json.tool

