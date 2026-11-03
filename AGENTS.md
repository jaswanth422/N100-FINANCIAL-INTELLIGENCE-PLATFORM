# Agent Instructions

Read these before making changes in this project.

## What this project is

N100 Financial Intelligence Platform — ingests Nifty 100 financial statements
(profit & loss, balance sheet, cash flow) from Excel sources, normalizes
and validates them, loads into SQLite (`nifty100.db`), computes profitability
/ leverage / efficiency / CAGR / cash-flow ratios, and surfaces them through
a Streamlit dashboard, a FastAPI endpoint, and a configurable screener.

## Context files

1. `README.md` — sprint status, dashboard guide, ETL commands
2. `AGENTS.md` (this file) — what to read before editing
3. `.claude/memory.md` — durable project context (stack, scope limits, invariants)
4. `docs/` — sprint retrospectives and architecture decisions

## Core directories

| Path | Role |
|------|------|
| `src/nifty100_etl/` | Excel discovery, column normalization, DQ validators |
| `src/etl/` | SQLite loader + manual review tooling |
| `src/analytics/` | Ratio engines (profitability, leverage, CAGR, cash flow, composite score, peer, radar, valuation) |
| `src/screener/` | Preset + custom filters over the ratio table |
| `src/nlp/` | Analysis-text parser + pros/cons generator |
| `src/dashboard/` | Streamlit UI |
| `src/api/` | FastAPI service |
| `src/reports/` | Tearsheet + sector + portfolio reports |

## Commands

```bash
make setup           # venv + deps + editable install
make db              # build nifty100.db from 12 workbooks
make ratios          # populate financial_ratios (depends on db)
make test            # pytest with coverage across all 8 packages
make lint            # ruff + mypy
make screener        # six preset screens
make dashboard       # streamlit UI on :8501
make api             # fastapi on :8000
```

The test suite auto-builds `nifty100.db` via `tests/conftest.py` on fresh
clones. Delete the file and run `pytest` to reproduce.

## Workflow

1. Understand existing code and conventions — this is a sprint-driven
   codebase; prior sprints have deliberate decisions documented in
   `docs/SPRINT_0X_RETROSPECTIVE.md`.
2. Propose approach, wait for approval on anything non-trivial.
3. Write tests first (`tests/` layout mirrors `src/`), update docs,
   suggest commit message.

## Constraints

- Do not commit or push unless explicitly asked.
- Do not hardcode secrets. No external APIs are required for the core
  ETL and ratio engines — they run offline against bundled workbooks.
- Preserve existing deterministic cross-check behavior in
  `src/analytics/ratios.py` — the OPM warning is a signal, not noise;
  if it fires, investigate the ETL and data, not the formula.
- Do not break the Streamlit dashboard — it is the primary stakeholder-
  facing surface.
