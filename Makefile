PYTHON := .venv/bin/python
PIP := .venv/bin/pip
export PYTHONPATH := src

.PHONY: setup install test lint format clean inspect validate db review sprint

setup:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PIP) install -e .

install:
	$(PIP) install -r requirements.txt
	$(PIP) install -e .

test:
	$(PYTHON) -m pytest --cov=nifty100_etl --cov-report=term-missing

lint:
	$(PYTHON) -m ruff check src tests
	$(PYTHON) -m mypy src

format:
	$(PYTHON) -m ruff format src tests
	$(PYTHON) -m ruff check --fix src tests

inspect:
	$(PYTHON) -m nifty100_etl.loader --source-dir .

validate:
	$(PYTHON) -m etl.validator --source-dir . --output output/validation_failures.csv

db:
	$(PYTHON) -m etl.loader --source-dir . --database nifty100.db --schema db/schema.sql --audit output/load_audit.csv

review: db
	$(PYTHON) -m etl.manual_review --database nifty100.db --output output/manual_review.csv --coverage-output output/year_coverage.csv

sprint: validate review test lint

clean:
	rm -rf .pytest_cache .coverage htmlcov build dist src/*.egg-info
