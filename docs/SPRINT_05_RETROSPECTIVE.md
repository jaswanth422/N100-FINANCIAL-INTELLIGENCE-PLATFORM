# Sprint 5 Retrospective - Cash Flow Intelligence and Reports

## Outcome

Sprint 5 delivered the cash-flow intelligence calculations, capital-allocation
audit, NLP outputs, company tearsheets, sector reports, portfolio summary, and a
repeatable structural validation script.

The source database has 92 roster companies. Cash-flow coverage is 91/92:

- ATGL has no cash-flow rows.
- JIOFIN has only 2023 and 2024 cash-flow rows.

The Day 34 rule requires skipping companies with fewer than three years of
cash-flow data. The batch therefore contains 90 tearsheets and records both
exceptions in `output/skipped_tearsheets.csv`.

## Cash-flow intelligence

`src/analytics/cashflow_kpis.py` implements:

- five-year average CFO/PAT quality score and the High Quality, Moderate, and
  Accrual Risk labels;
- latest-year CapEx intensity and Asset Light, Moderate, and Capital Intensive
  labels;
- latest-year distress detection (`CFO < 0` and `CFF > 0`);
- latest-year deleveraging detection (`CFF < 0` and borrowings below the prior
  year);
- five-year FCF CAGR, FCF conversion, and capital-allocation labels;
- capital-allocation completeness checks, latest-pattern distribution, and
  year-over-year pattern changes.

The generated intelligence CSV has 92 rows and the exact 11 requested columns.
ATGL remains in the roster with unavailable cash-flow metrics rather than being
silently dropped. There are 13 distress alerts.

Capital allocation now contains 1,054 unique company-year rows for the 91
companies with cash-flow history. The latest available distribution is:

| Pattern | Companies |
| --- | ---: |
| Reinvestor | 16 |
| Shareholder Returns | 39 |
| Liquidating Assets | 7 |
| Distress Signal | 1 |
| Growth Funded by Debt | 12 |
| Cash Accumulator | 0 |
| Pre-Revenue | 1 |
| Mixed | 15 |

The 13 direct distress alerts and one `Distress Signal` allocation are not a
contradiction: the alert uses only CFO and CFF, while the eight-pattern
allocation classifier also uses the sign of CFI.

## PDF reports

All PDF tables route textual cells through wrapped ReportLab `Paragraph`
objects. The company tearsheet uses fixed-size chart panels and a controlled
page break to guarantee two pages.

Visual review was performed on TCS, HDFCBANK, RELIANCE, SUNPHARMA, and
TATASTEEL. The review led to three fixes before the batch run:

- wider and smaller ticker headers for long symbols;
- a dedicated second-page header to remove top-edge clipping;
- negative waterfall labels placed inside bars to prevent axis collisions.

Final automated PDF checks:

- 90 eligible tearsheets;
- every tearsheet has exactly two pages;
- smallest tearsheet is 91,103 bytes;
- no blank tearsheet pages;
- 11 sector reports;
- 92-page portfolio summary with no blank pages.

The source `broad_sector` field contains 10 values because Utilities companies
are grouped into Energy. Sector reporting restores Utilities as the eleventh
sector using the source sub-sectors Gas Distribution, Power & Utilities, Power
Transmission, and Renewable Energy.

## NLP deliverables

- `analysis_parsed.csv`: 63 structured values from 20 source rows; 17 regex
  misses and one CAGR divergence are retained in `parse_failures.csv`.
- `pros_cons_generated.csv`: 510 signals across all 92 companies. Every company
  has at least one pro and one con; honest rule-0 manual-review sentinels are used
  where no quantitative rule clears the confidence threshold.

## Verification

Cash-flow unit and acceptance tests: 40 passed.

`scripts/validate_sprint5.py` checks PDF page counts, blank pages, file sizes,
CSV schemas and row counts, and full pros/cons coverage.

## Open environment limitation

`output/cashflow_intelligence.xlsx` was not authored in this session because
the required spreadsheet artifact runtime and dependency loader were not
available. The validated 92-row source is
`output/cashflow_intelligence.csv`. The workbook should be exported from that
source when the supported spreadsheet runtime is available; using an alternate
workbook library would bypass the required spreadsheet validation workflow.
