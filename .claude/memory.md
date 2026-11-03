# Project Memory

Durable context Claude should load when working in this repo.

## Vision

N100 Financial Intelligence Platform — Nifty 100 financial-statement ETL,
ratio engine, screener, and dashboard. See `README.md` for sprint status.

## Current stack

- **Language:** Python ≥ 3.11
- **Store:** SQLite (`nifty100.db`), schema at `db/schema.sql`
- **Core packages:** `nifty100_etl`, `etl`, `analytics`, `screener`, `nlp`,
  `dashboard`, `api`, `reports` (all under `src/`)
- **Tests:** pytest, with autouse session fixture at `tests/conftest.py`
  that builds `nifty100.db` on fresh clones
- **Lint/type:** `ruff` (blocking) + `mypy` (non-blocking in CI)
- **CI:** GitHub Actions, Python 3.11 + 3.12 matrix

## Commands

```bash
make setup                           # venv + deps + editable install
make db                              # build nifty100.db
make ratios                          # populate ratios (depends on db)
make test                            # pytest + coverage across 8 packages
make lint                            # ruff check + mypy
PYTHONPATH=src pytest                # run tests manually
```

## Deliberate decisions (don't drift)

- **Scorer determinism:** `src/analytics/ratios.py:operating_profit_margin()`
  always returns the computed OPM (profit/sales*100), using `opm_percentage`
  only as a cross-check reference. Never flip this.
- **INDIGO OPM sanitizer** (`src/nifty100_etl/loader.py:sanitize_opm_percentage`):
  nulls any `opm_percentage` cell outside `[-100, 100]` on load. Root cause:
  historical INDIGO rows in `profitandloss.xlsx` have `operating_profit` (₹
  crore) placed in the OPM column. The sanitizer suppresses the misleading
  cross-check; the underlying column-shift in the Excel source still needs
  a data-pipeline fix (out of scope for the ETL).
- **DB-build test fixture** (`tests/conftest.py`): session-scoped autouse
  that re-runs `etl.loader.load_database` + `analytics.populate_ratios` on
  fresh clones. Keeps tests in lock-step with the current ETL — never cache
  a stale DB.
- **No LLM / external API calls** in the core ETL or ratio layers. Keep
  determinism for CI and evals.

## Known data quality warts

- INDIGO rows FY2013-FY2020 in `profitandloss.xlsx` have shifted columns —
  `operating_profit` and `expenses` are also unreliable, not just OPM.
  Computed OPM for those years remains unrealistic (90%+) because the fix
  only sanitizes the cross-check reference, not the computed inputs. A
  proper fix requires a corrected workbook or an upstream scraper patch.

## CI expectations

- `ruff check src tests` → All checks passed
- `pytest` → 184 passed as of PR #1 (post-remediation)
- Coverage reported across: `analytics`, `api`, `dashboard`, `etl`,
  `nifty100_etl`, `nlp`, `reports`, `screener`

## Guardrails

- Project-local permission allowlist + preflight hook in
  `.claude/settings.json`.
- Dependabot runs weekly for `pip` and `github-actions`.
- `SECURITY.md` routes vulnerability reports to katurijaswanth422@gmail.com.

## Non-goals (for now)

- Multi-tenant SaaS, auth, billing.
- Real-time market data feeds — current ETL is batch over bundled Excel.
- Rewriting the Streamlit dashboard — stable and stakeholder-facing.

## Links

- [README.md](../README.md) — sprint status + dashboard guide
- [AGENTS.md](../AGENTS.md) — read-before-editing checklist
- [docs/](../docs/) — sprint retrospectives
