"""Canonical value normalization shared by all source loaders."""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from numbers import Integral, Real
from typing import Any

_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_SHORT_YEAR_RE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[\s/-]+(\d{2})\b",
    re.IGNORECASE,
)
_TICKER_SUFFIX_RE = re.compile(r"\s*\.(?:NS|NSE)\s*$", re.IGNORECASE)
_TICKER_PREFIX_RE = re.compile(r"^\s*NSE\s*:\s*", re.IGNORECASE)
_INVALID_TICKER_CHARS_RE = re.compile(r"[^A-Z0-9&-]+")
_NON_ANNUAL_PERIODS = {"TTM", "LTM"}


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, Real) and math.isnan(value))


def normalize_year(value: Any) -> int | None:
    """Return a four-digit year from common Excel/source representations.

    Blank values return ``None``. Unsupported or out-of-range values raise
    ``ValueError`` so malformed source data cannot silently enter the database.
    """
    if _is_missing(value):
        return None
    if isinstance(value, (datetime, date)):
        return value.year
    if isinstance(value, bool):
        raise ValueError(f"Invalid year: {value!r}")
    if isinstance(value, Integral):
        year = int(float(value))
    elif isinstance(value, Real):
        if not float(value).is_integer():
            raise ValueError(f"Invalid year: {value!r}")
        year = int(float(value))
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.upper() in _NON_ANNUAL_PERIODS:
            return None
        match = _YEAR_RE.search(text)
        if not match:
            short_match = _SHORT_YEAR_RE.search(text)
            if not short_match:
                raise ValueError(f"Invalid year: {value!r}")
            short_year = int(short_match.group(1))
            year = 2000 + short_year if short_year <= 69 else 1900 + short_year
        else:
            year = int(match.group(1))
    if not 1900 <= year <= 2100:
        raise ValueError(f"Year outside supported range: {year}")
    return year


def normalize_ticker(value: Any) -> str | None:
    """Return an uppercase NSE ticker without exchange prefix/suffix noise."""
    if _is_missing(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    text = _TICKER_PREFIX_RE.sub("", text)
    text = _TICKER_SUFFIX_RE.sub("", text)
    text = _INVALID_TICKER_CHARS_RE.sub("", text.upper())
    if not text:
        raise ValueError(f"Invalid ticker: {value!r}")
    return text
