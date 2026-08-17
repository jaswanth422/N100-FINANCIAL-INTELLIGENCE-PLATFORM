"""Regression tests for dashboard company autocomplete."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

PAGES_DIR = Path(__file__).resolve().parents[2] / "src" / "dashboard" / "pages"


@pytest.mark.parametrize(
    "page_name",
    ["02_profile.py", "05_trends.py", "08_reports.py"],
)
def test_exact_ticker_is_prioritized_over_substring_matches(
    page_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LT must not be displaced by the many company names containing 'lt'."""
    response = SimpleNamespace(status_code=200)
    monkeypatch.setattr("requests.head", lambda *args, **kwargs: response)
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: response)

    app = AppTest.from_file(str(PAGES_DIR / page_name), default_timeout=10).run()
    app = app.text_input[0].set_value("LT").run()

    assert not app.exception
    assert app.selectbox[0].options[0].startswith("LT —")
