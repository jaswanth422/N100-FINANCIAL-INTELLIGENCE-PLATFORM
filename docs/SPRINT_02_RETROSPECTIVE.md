# Sprint 02 Retrospective — Financial Analytics Engine

## Outcome

Sprint 02 implemented profitability, leverage, efficiency, CAGR, cash-flow, and capital-allocation
analytics and populated `nifty100.db` for the available N100 source universe.

- `financial_ratios`: 1,192 rows across all 92 companies in the master table.
- Required KPI columns: all 17 requested columns have at least one non-null value.
- Financials leverage carve-out: zero `high_leverage_flag` rows for all companies classified as
  `broad_sector = Financials`.
- KPI acceptance suite: 20 passed, 0 failed.
- Full repository suite: 131 passed, 0 failed.
- Screener preview (`ROE > 15% AND D/E < 1`): 34 companies, within the required 15–50 range.
- Capital-allocation output: generated for every unique, complete company-year cash-flow record.

## Formula decisions

| KPI | Decision |
| --- | --- |
| Net profit margin | `PAT / sales * 100`; zero sales returns null. |
| Operating margin | `operating_profit / sales * 100`; reported OPM is a cross-check only. |
| ROE | `PAT / (equity_capital + reserves) * 100`; non-positive equity returns null. |
| ROCE | `(operating_profit + other_income) / (equity + reserves + borrowings) * 100`. |
| Debt-to-equity | `borrowings / (equity + reserves)`; debt-free companies return zero. |
| Interest coverage | `(operating_profit + other_income) / interest`; zero interest is `Debt Free`. |
| Net debt | `borrowings - investments`, using investments as the liquid-asset proxy. |
| Free cash flow | `operating_activity + investing_activity`; negative FCF is valid. |
| CapEx | `abs(investing_activity)` because a dedicated capital-expenditure source field is absent. |
| Book value/share | `(equity + reserves) * face_value / equity_capital`. |
| CAGR | Exact year endpoints with 3-, 5-, and 10-year windows; sign changes return explicit flags. |
| Composite quality | Equal-weight average of normalized ROE, margin, D/E, ICR, and CFO/PAT components. |

## Edge-case resolutions

1. The sector workbook currently identifies 23 Financials companies, while the requirement expected
   19. The rule is data-driven, so leverage warnings are suppressed for all 23 classified companies.
2. Computed ROE and ROCE are analytics values. `companies.xlsx` ratios are display-only cross-checks.
3. The latest ROE/ROCE comparison produced 52 anomalies over five percentage points:
   8 data-source issues, 26 version differences, and 18 formula discrepancies.
4. TCS source ROE is `0.52%` versus an engine ROE of `45.42%`; this is documented as a data-source
   issue and the engine value is retained for analytics.
5. Standard ROCE is not sector-comparable for banks, NBFCs, and insurers. Financial-sector ROCE
   differences are categorized as formula discrepancies and require sector-relative interpretation.
6. The source ratio workbook contains duplicate company-year keys. Existing rows were retained to
   preserve the required row count, but each duplicate is populated consistently from the same latest
   normalized statement record.
7. The capital-allocation pattern list omits `(-,+,-)` and has a conditional duplicate of `(+,-,-)`.
   The uncovered combination and zero-flow cases use `Mixed`.

Every anomaly and its explanation is recorded in `output/ratio_edge_cases.log`.

## Manual spot-check

The following values were independently recomputed from the latest normalized P&L and balance-sheet
inputs. Differences are percentage points and are below the 0.1 threshold.

| Company | Year | Manual ROE | DB ROE | ROE diff | Manual Revenue CAGR 5Y | DB CAGR 5Y | CAGR diff |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| INFY | 2024 | 29.015177% | 29.015177% | 0.000000 | 13.199101% | 13.199101% | 0.000000 |
| RELIANCE | 2024 | 9.643018% | 9.643018% | 0.000000 | 9.606097% | 9.606097% | 0.000000 |
| TCS | 2024 | 45.419971% | 45.419971% | 0.000000 | 10.463615% | 10.463615% | 0.000000 |

The requested `.xlsx` version remains pending because the mandated spreadsheet artifact runtime was
not available in this execution environment. The calculations and reconciliation above are complete.

## Screener review

The 34-result preview includes established high-return, low-debt companies such as TCS, Infosys, ITC,
Asian Paints, HCL Technologies, Eicher Motors, Pidilite, and Maruti. BEL, HAL, and InterGlobe Aviation
show implausibly high ROE caused by documented source-input anomalies; the preview marks these rows for
review rather than silently removing them from the mechanical filter.

## Team demo and sign-off

`output/financial_ratios_demo.csv` contains latest-year complete KPI rows for RELIANCE, TCS, INFY,
HDFCBANK, and ITC. The technical demo artifact is ready. Team-lead meeting completion and sign-off are
pending external human confirmation and must not be recorded as complete until that confirmation occurs.
