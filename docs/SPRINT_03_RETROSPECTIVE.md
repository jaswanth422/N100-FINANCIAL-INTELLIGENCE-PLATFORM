# Sprint 03 Retrospective — Screener, Peer Analytics, and Reports

Date: 2026-07-23  
Status: Technical acceptance complete; team-lead meeting/sign-off pending external confirmation.

## Delivered

- Six analyst-editable screeners backed by `config/screener_config.yaml`.
- Sector-relative P10/P90 composite quality score on a 0–100 scale.
- Six-sheet `output/screener_output.xlsx` with 20 KPIs and threshold colours.
- Ten persisted peer percentile metrics for 56 companies across 11 peer groups.
- Eleven-sheet `output/peer_comparison.xlsx` with 20 raw metrics, 20 percentile
  columns, benchmark highlighting, and peer-median rows.
- Ninety-two company chart PNGs: 56 peer radars and 36 Nifty 100 fallback charts.

## Acceptance evidence

### Preset counts

| Preset | Companies | Required range | Status |
|---|---:|---:|---|
| Quality Compounder | 17 | 5–50 | PASS |
| Value Pick | 5 | 5–50 | PASS |
| Growth Accelerator | 18 | 5–50 | PASS |
| Dividend Champion | 30 | 5–50 | PASS |
| Debt-Free Blue Chip | 8 | 5–50 | PASS |
| Turnaround Watch | 30 | 5–50 | PASS |

Value Pick's P/B ceiling was calibrated from 3x to 5x to satisfy the minimum
sample size. Debt-Free Blue Chip treats D/E up to 0.02 as immaterial rounding
debt. Both decisions are documented beside the editable thresholds.

### Quality Compounder manual top-five check

| Company | ROE % | D/E | FCF (Cr) | Revenue CAGR 5yr % | Result |
|---|---:|---:|---:|---:|---|
| Adani Power | 37.23 | 0.674 | 17,651 | 16.09 | PASS |
| InterGlobe Aviation | 856.98 | 0.021 | 9,424 | 19.31 | PASS |
| Asian Paints | 30.84 | 0.140 | 3,556 | 13.03 | PASS |
| Nestle India | 98.57 | 0.093 | 2,938 | 14.55 | PASS |
| IRCTC | 31.54 | 0.012 | 667 | 17.96 | PASS |

All 17 Quality Compounder results have ROE above 15% and D/E below 1. The
Financials D/E exemption is explicitly disabled for this preset.

### Peer percentile spot checks

- IT Services: TCS has the highest ROE (45.42%) and the highest ROE percentile
  rank (1.00).
- FMCG: Nestle India has the highest ROE (98.57%) and the highest ROE percentile
  rank (1.00).
- D/E ranks remain inverted so lower leverage receives the higher percentile.

### Automated verification

- Dedicated DQ acceptance suite: 14 tests passed, 0 failed (`DQ-03`–`DQ-16`).
- Full regression suite: 158 tests passed, 0 failed.
- `screener_output.xlsx`: exactly 6 sheets, 92 rows per sheet, 25 columns,
  score-sorted, no formula-error strings.
- `peer_comparison.xlsx`: exactly 11 sheets, 42 columns per sheet, all peer
  assignments covered, benchmark and percentile fills present, median row on
  every sheet, no formula-error strings.
- `peer_percentiles`: 560 rows, 56 companies, 11 groups, 10 metrics, ranks
  bounded from 0.00 to 1.00.
- Radar directory: 92 readable PNGs.

## What went well

- Scoring, screening, persisted rankings, Excel reports, and chart generation
  now share canonical metric definitions.
- Acceptance checks exposed a hidden sector-exemption interaction in Quality
  Compounder before review; the exemption is now preset-configurable.
- Missing peer assignments degrade gracefully and produce a useful Nifty 100
  comparison rather than an exception.

## What changed during review

- Removed the seventh Summary tab from the screener workbook to meet the exact
  six-sheet deliverable.
- Added 20 report-level percentile calculations without changing the ten-metric
  SQLite persistence contract from Day 18.
- Added a dedicated 14-test DQ acceptance file while retaining the broader
  production validation suite.

## Follow-ups

- Investigate the source-data outlier for InterGlobe Aviation's 2024 ROE before
  using the metric in an investment decision.
- Decide whether report-level percentiles for the additional ten metrics should
  also be persisted in SQLite in the next sprint.
- Record the team lead's decision in the sign-off section below.

## Demo and sign-off record

Demo sequence:

1. Open `output/screener_output.xlsx` and review Quality Compounder threshold
   colours and top-five rows.
2. Open `output/peer_comparison.xlsx`, inspect IT Services and FMCG ROE ranks,
   benchmark highlighting, and median rows.
3. Open `reports/radar_charts/TCS_radar.png`.
4. Query `peer_percentiles` for IT Services ROE.
5. Review `config/screener_config.yaml`.

Team lead: ____________________  
Meeting date: ____________________  
Decision: ☐ Approved ☐ Approved with actions ☐ Not approved  
Comments: ______________________________________________________________  
Signature: ____________________
