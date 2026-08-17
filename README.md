# N100 FINANCIAL INTELLIGENCE PLATFORM

Financial data ingestion, normalization, validation, and analytics platform for the NIFTY 100 universe.

## Sprint 01 status

- Day 01: environment and project setup — complete
- Day 02: Excel ingestion and normalization — complete
- Day 03: sixteen data-quality rules — complete
- Day 04: ten-table SQLite schema — complete
- Day 05: full 12-file load and audit — complete
- Day 06: five-company manual review — complete
- Day 07: exploratory SQL, tests, database demo, and retrospective — complete

Run `make sprint` to rebuild and verify all Sprint 01 deliverables.

## Sprint 02 status

- Profitability, leverage, efficiency, CAGR, and cash-flow KPI engines — complete
- Financial ratios populated for 92 companies and 1,192 rows — complete
- Capital-allocation classifications and categorized ratio edge-case log — complete
- Twenty-test KPI acceptance suite — complete

See `docs/SPRINT_02_RETROSPECTIVE.md` for formula decisions, validation results, and known source-data edge cases.

## Sprint 03 screener

Run `make screener` to apply the six presets in `config/screener_config.yaml` to the
latest 92-company universe and rebuild `output/screener_output.xlsx`. Each
preset sheet contains five identifier fields plus 20 KPIs, is sorted by the
sector-relative composite score, and highlights threshold passes in green and
failures in red. Custom screens are available through
`ScreenerEngine.run_custom(...)` or `apply_filters(...)` in
`src/screener/engine.py`.

The composite score is a P10/P90-winsorised 0-100 model computed within each
`broad_sector`: profitability 35%, cash quality 30%, growth 20%, and leverage
15%. Run `make ratios` to refresh the score and its coverage percentage in
SQLite.

## Peer analytics and charts

- `make peers` loads the 11 groups in `supporting datasets/peer_groups.xlsx`,
  calculates ten within-group percentile ranks, and populates the
  `peer_percentiles` table. It also generates `output/peer_comparison.xlsx`
  with 20 metrics and 20 report percentiles per company. D/E rank is inverted
  so lower leverage ranks higher.
- `make radar` generates one PNG per company in `reports/radar_charts/`. The 56
  assigned companies receive eight-axis peer radar charts; unassigned companies
  receive a composite-score comparison against the Nifty 100 average.

## Streamlit dashboard

Create and activate a Python environment, install the project dependencies, and
start the dashboard from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run src/dashboard/app.py
```

Streamlit opens **Nifty 100 Analytics** in a wide layout with the navigation
sidebar expanded. The application reads `nifty100.db` by default; set
`NIFTY100_DB_PATH` to use another compatible SQLite database. Database query
results are cached for 10 minutes, so use Streamlit's **Clear cache** command
after replacing the database during a running session.

### Screen guide

| Screen | What to demonstrate |
| --- | --- |
| **Home** | Select a financial year from 2019–2024 and review six market KPIs, the 11-sector company-count donut, and the top-five quality-score table. |
| **Company Profile** | Search by company name or ticker, select the autocomplete result, and review the company card, six KPIs, 10-year Revenue/PAT and ROE/ROCE charts, and pros/cons. Partial histories and missing metrics are shown as notes or `N/A`. |
| **Stock Screener** | Adjust ten live filters or apply one of six presets, inspect the matching-company count and visible metrics, then download the same result columns as a CSV. |
| **Peer Comparison** | Choose one of 11 peer groups and a benchmark company to compare eight percentile-normalized metrics on a radar chart and in a side-by-side KPI table. |
| **Trend Analysis** | Search for a company, overlay up to three metrics, and inspect the available 10-year series with year-over-year percentage annotations. |
| **Sector Analysis** | Select a sector to compare Revenue, ROE, Market Cap, and sub-sector membership in a bubble chart, followed by sector-median KPI bars. |
| **Capital Allocation Map** | Explore all 92 companies in a treemap grouped into eight capital-allocation patterns; selecting a pattern reveals its company list. |
| **Annual Reports** | Search for a company and open the available BSE annual-report PDFs. Broken or missing links are labelled **Report unavailable** instead of failing the page. |

### Valuation outputs

Rebuild the valuation workbooks from the latest database and market-cap input:

```bash
PYTHONPATH=src python -m analytics.valuation
```

This produces `output/valuation_summary.xlsx` for all 92 companies and
`output/valuation_flags.csv` for the Caution and Discount cases. The workbook
contains P/E, P/B, EV/EBITDA, FCF yield, five-year median P/E, the comparison
with the sector median, and the resulting valuation flag.

Sprint 4 delivery evidence, UX decisions, edge cases, performance results, and
the repeatable team-lead demo script are documented in
[`docs/SPRINT_04_RETROSPECTIVE.md`](docs/SPRINT_04_RETROSPECTIVE.md). Task
completion is tracked in [`docs/SPRINT_04_BOARD.md`](docs/SPRINT_04_BOARD.md).
