from datetime import date, datetime

import pytest

from nifty100_etl.normalize import normalize_ticker, normalize_year


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (2024, 2024),
        (2024.0, 2024),
        ("2024", 2024),
        (" 2024 ", 2024),
        ("FY2024", 2024),
        ("FY 2024", 2024),
        ("2024-25", 2024),
        ("Mar 2024", 2024),
        ("31-03-2024", 2024),
        ("Mar-13", 2013),
        ("Dec 99", 1999),
        (date(2023, 3, 31), 2023),
        (datetime(2022, 12, 1, 9, 30), 2022),
        (None, None),
        ("", None),
        ("   ", None),
        ("TTM", None),
        ("ltm", None),
        (float("nan"), None),
    ],
)
def test_normalize_year(raw, expected):
    assert normalize_year(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [True, False, 1899, 2101, 2024.5, "unknown", "24", object()],
)
def test_normalize_year_rejects_invalid_values(raw):
    with pytest.raises(ValueError):
        normalize_year(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("RELIANCE", "RELIANCE"),
        (" reliance ", "RELIANCE"),
        ("RELIANCE.NS", "RELIANCE"),
        ("reliance.nse", "RELIANCE"),
        ("NSE:RELIANCE", "RELIANCE"),
        (" nse : infy ", "INFY"),
        ("M&M", "M&M"),
        ("BAJAJ-AUTO", "BAJAJ-AUTO"),
        ("HDFC BANK", "HDFCBANK"),
        ("L&T.NS", "L&T"),
        (123, "123"),
        (None, None),
        ("", None),
        ("  ", None),
        (float("nan"), None),
    ],
)
def test_normalize_ticker(raw, expected):
    assert normalize_ticker(raw) == expected


@pytest.mark.parametrize("raw", [".", "***", "NSE:", " .NS "])
def test_normalize_ticker_rejects_invalid_values(raw):
    with pytest.raises(ValueError):
        normalize_ticker(raw)
