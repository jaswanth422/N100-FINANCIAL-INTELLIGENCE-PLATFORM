# Sprint 04 Retrospective

**Sprint:** Days 22–28  
**Status:** Technical acceptance complete; team-lead sign-off pending external confirmation

## Delivered

- A wide-layout Streamlit application with native sidebar navigation across all
  eight screens.
- Shared, parameterized SQLite loaders in `src/dashboard/utils/db.py`, with a
  600-second `st.cache_data` policy on every database query function.
- Home, Company Profile, Stock Screener, Peer Comparison, Trend Analysis,
  Sector Analysis, Capital Allocation Map, and Annual Reports experiences.
- FCF-yield and sector-relative P/E valuation logic in
  `src/analytics/valuation.py`.
- `output/valuation_summary.xlsx` with 92 company rows and
  `output/valuation_flags.csv` with the Caution and Discount cases.
- Integration tests covering dashboard data access, calculations, valuation,
  and the wider analytics pipeline.

## UX decisions

- **One persistent navigation model.** Native Streamlit navigation keeps all
  screens under one expanded sidebar and avoids separate entry-point scripts.
- **Progressive company search.** Search text narrows an autocomplete selector,
  while an exact unknown ticker receives a friendly recovery message.
- **Comparable peer radar metrics.** Radar values use peer percentiles rather
  than raw units so margins, multiples, growth rates, and leverage can share one
  readable scale.
- **Visible missing-data states.** Cards and tables display `N/A`; charts render
  only valid observations; partial histories include a data-availability note.
- **Responsive Plotly charts.** Every chart stretches to its container width so
  it does not overflow the wide dashboard layout.
- **Actionable controls.** Screener presets populate the same ten live filters,
  and CSV export uses exactly the columns shown in the results table.
- **Safe report links.** Annual-report URLs are checked concurrently and cached;
  missing or unreachable PDFs receive a red unavailable badge.
- **Eleven-sector presentation.** The source's Power & Utilities population is
  presented as separate Power and Utilities views to support the agreed
  11-sector dashboard breakdown while retaining source classifications.

## Data edge cases discovered

- The supplied Nifty universe contains 92 companies, not 100, so all dashboard
  counts and valuation acceptance checks use the available 92-company source.
- Some companies have fewer than ten annual observations. JIOFIN, LICI, ATGL,
  and ADANIGREEN exercise the partial-history path without padding missing
  years.
- ATGL has no usable latest FCF value; the Company Profile correctly shows
  `N/A`.
- Duplicate company/year ratio rows can exist in the analytical source. The
  loader consistently selects the most recent stored record.
- Several source fields contain nulls, non-finite values, or extreme ratios.
  Formatters guard these values and Plotly receives only finite observations.
- Only 56 companies are assigned to the supplied peer groups. Unassigned
  companies remain available elsewhere in the dashboard without causing peer
  comparison failures.
- Annual-report URLs may be absent, return 404, or fail temporarily. These cases
  are handled as unavailable reports rather than page errors.
- The short ticker `LT` also appears inside many company names. Exact ticker and
  exact company-name matches are now ranked ahead of substring matches so the
  requested company cannot be pushed beyond the 20-result autocomplete limit.

## Performance findings

- Company Profile warm-process load measurements for ten cross-sector tickers
  ranged from **0.1272 to 0.1553 seconds**, comfortably below the three-second
  acceptance limit.
- Shared query caching uses a 600-second TTL, reducing repeat SQLite work as
  users switch screens or revisit a company.
- Annual-report availability checks run concurrently and use a one-hour result
  cache so slow remote endpoints do not serially block page rendering.
- Parameterized queries request only the selected company, year, sector, or
  peer group instead of loading every source table for each interaction.

## Acceptance evidence

| Criterion | Result |
| --- | --- |
| Eight screens load without import or runtime errors | Passed |
| Company search screens render all 92 exact tickers | Passed; 92/92 on Profile, Trends, and Reports |
| Cross-sector and partial-history ticker coverage | Passed |
| Missing values render as `N/A` or an explanatory note | Passed |
| Screener minimum/maximum filter extremes do not crash | Passed |
| Screener CSV has the visible column headers and valid row structure | Passed |
| Plotly charts stay within the page container | Passed |
| Company Profile loads in under 3 seconds | Passed; slowest measured 0.1553 s |
| Valuation summary contains all required columns and 92 rows | Passed |
| Automated test suite | Passed; 162 tests |

The valuation result contains 14 Caution, 30 Discount, and 48 Fair companies;
the flags CSV therefore contains the 44 non-Fair cases.

## Technical demo walkthrough

Use live data and follow this sequence:

1. **Home:** select 2024 and explain the six KPIs, sector donut, and top-five
   quality table.
2. **Company Profile:** search for `HDFCBANK`; review the company card, KPIs,
   Revenue/PAT bars, ROE/ROCE lines, and pros/cons. Then search for `ATGL` to
   demonstrate the partial-history note and `N/A` FCF.
3. **Stock Screener:** apply the Quality preset, move one filter, confirm the
   live result count, and download the visible CSV.
4. **Peer Comparison:** select IT Services and benchmark `TCS`; explain the
   eight-metric radar and highlighted table row.
5. **Trend Analysis:** search for `RELIANCE`, overlay Revenue, Net Profit, and
   FCF, and point out the YoY annotations and available-year handling.
6. **Sector Analysis:** select Energy and explain Revenue on X, ROE on Y,
   Market Cap as bubble size, sub-sector colour, and the median KPI bars.
7. **Capital Allocation Map:** select a treemap pattern and show the underlying
   company list.
8. **Annual Reports:** search for `INFY`, open an available BSE PDF, and show
   how an unavailable report is badged without breaking the page.

The technical walkthrough is complete when all eight steps render against the
current `nifty100.db`. Human attendance and acceptance must be recorded below
by the presenter or team lead.

**Automated live-data walkthrough:** completed 29 July 2026. Streamlit's
application-testing runtime rendered the eight screens, all six Home years,
all 11 peer groups, all 11 sector views, all eight capital patterns, all six
screener presets, both screener endpoint configurations, and the three
company-search screens for all 92 tickers. An interactive browser backend was
not attached to the agent session, so the human presentation remains the
explicit sign-off step below.

## Team-lead sign-off

- **Demo date:** ____________________
- **Team lead:** ____________________
- **Decision / comments:** ____________________
