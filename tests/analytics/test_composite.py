from __future__ import annotations

import pandas as pd
import pytest

from analytics.composite import compute_composite_scores, winsorised_scale


def test_winsorised_scale_caps_p10_and_p90() -> None:
    values = pd.Series([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 1000], dtype=float)

    scores = winsorised_scale(values)

    assert scores.iloc[0] == pytest.approx(0)
    assert scores.iloc[1] == pytest.approx(0)
    assert scores.iloc[9] == pytest.approx(100)
    assert scores.iloc[10] == pytest.approx(100)


def test_composite_score_is_sector_relative() -> None:
    frame = pd.DataFrame(
        {
            "company_id": ["A_LOW", "A_TARGET", "A_HIGH", "B_TARGET", "B_MID", "B_HIGH"],
            "broad_sector": ["A", "A", "A", "B", "B", "B"],
            "return_on_equity_pct": [0, 10, 20, 10, 20, 30],
        }
    )

    scored = compute_composite_scores(frame)
    scores = scored.set_index("company_id")["composite_quality_score"]

    assert scores["A_TARGET"] == pytest.approx(50)
    assert scores["B_TARGET"] == pytest.approx(0)
    assert scored["composite_score_coverage_pct"].eq(15).all()
