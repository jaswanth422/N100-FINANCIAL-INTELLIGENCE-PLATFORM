# Sprint 01 Retrospective

## Outcome

Days 01–07 are complete. The platform now has repeatable ingestion, normalization, validation, SQLite loading, audits, manual review, and exploratory SQL.

## What went well

- Workbook title rows and mixed fiscal-year formats were normalized automatically.
- The loader enables SQLite foreign-key enforcement and verifies it after loading.
- Tests caught fractional years, TTM/LTM periods, and short year labels.

## Source-data constraints

- The 92-row company master does not contain nine tickers referenced by historical files.
- Those rows are retained in `output/validation_failures.csv` and rejected during database loading.
- `AGTL` appears to be a source typo for `ATGL`; it is not silently rewritten.

## Next sprint

- Obtain an authoritative mapping or master records for the orphan tickers.
- Add analytics and API layers over the validated database.

