PYTHON := .venv/bin/python
PIP := .venv/bin/pip
export PYTHONPATH := src

.PHONY: setup install test lint format clean inspect validate db load review ratios screener peers radar cashflow nlp tearsheets sectors portfolio reports report dashboard api sprint

setup:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PIP) install -e .

install:
	$(PIP) install -r requirements.txt
	$(PIP) install -e .

test:
	mkdir -p reports
	$(PYTHON) -m pytest -v \
	    --cov=analytics --cov=api --cov=dashboard --cov=etl --cov=nifty100_etl \
	    --cov=nlp --cov=reports --cov=screener \
	    --cov-report=term-missing \
	    --html=reports/pytest_report.html --self-contained-html

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

load: db
	mkdir -p data
	cp nifty100.db data/nifty100.db

review: db
	$(PYTHON) -m etl.manual_review --database nifty100.db --output output/manual_review.csv --coverage-output output/year_coverage.csv

ratios: db
	$(PYTHON) -m analytics.populate_ratios --database nifty100.db

screener: ratios
	$(PYTHON) -m screener.engine --database nifty100.db --output output/screener_output.xlsx

peers: ratios
	$(PYTHON) -m analytics.peer --database nifty100.db --peer-groups "supporting datasets/peer_groups.xlsx" --output output/peer_comparison.xlsx

radar: peers
	$(PYTHON) -m analytics.radar --database nifty100.db --peer-groups "supporting datasets/peer_groups.xlsx" --output-dir reports/radar_charts

cashflow: ratios
	$(PYTHON) -m analytics.cashflow_kpis --database nifty100.db --output-dir output

nlp:
	$(PYTHON) -m nlp.parser
	$(PYTHON) -m nlp.pros_cons_generator

tearsheets: cashflow nlp
	$(PYTHON) -m reports.tearsheet

sectors: cashflow
	$(PYTHON) -m reports.sector_report

portfolio: cashflow
	$(PYTHON) -m reports.portfolio_summary

reports: tearsheets sectors portfolio
	$(PYTHON) scripts/validate_sprint5.py

report: reports

dashboard:
	$(PYTHON) -m streamlit run src/dashboard/app.py --server.port 8501

api:
	$(PYTHON) -m uvicorn api.main:app --port 8000

sprint: validate review test lint

clean:
	rm -rf .pytest_cache .coverage htmlcov build dist src/*.egg-info
