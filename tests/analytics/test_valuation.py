from __future__ import annotations

import pandas as pd

from analytics.valuation import build_valuation_summary


def test_build_valuation_summary_computes_yield_medians_and_flags() -> None:
    market = pd.DataFrame(
        {
            "id": range(1, 13),
            "company_id": ["A", "A", "A", "A", "A", "B", "B", "B", "B", "B", "C", "C"],
            "year": [
                2020,
                2021,
                2022,
                2023,
                2024,
                2020,
                2021,
                2022,
                2023,
                2024,
                2023,
                2024,
            ],
            "market_cap_crore": [1000] * 12,
            "pe_ratio": [10, 11, 12, 13, 31, 18, 19, 20, 21, 10, 20, 20],
            "pb_ratio": [2.0] * 12,
            "ev_ebitda": [8.0] * 12,
        }
    )
    ratios = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "company_id": ["A", "B", "C"],
            "year": ["Mar 2024", "Mar 2024", "Mar 2024"],
            "free_cash_flow_cr": [50.0, 20.0, 10.0],
        }
    )
    companies = pd.DataFrame(
        {
            "id": ["A", "B", "C"],
            "company_name": ["Alpha", "Beta", "Gamma"],
        }
    )
    sectors = pd.DataFrame(
        {
            "company_id": ["A", "B", "C"],
            "broad_sector": ["Technology", "Technology", "Healthcare"],
        }
    )

    summary, sector_medians = build_valuation_summary(market, ratios, companies, sectors)
    indexed = summary.set_index("company_id")

    assert indexed.loc["A", "FCF_yield_pct"] == 5.0
    assert indexed.loc["A", "5yr_median_PE"] == 12.0
    assert indexed.loc["A", "flag"] == "Caution"
    assert indexed.loc["B", "flag"] == "Discount"
    assert indexed.loc["C", "flag"] == "Fair"
    assert set(sector_medians["sector"]) == {"Healthcare", "Technology"}
