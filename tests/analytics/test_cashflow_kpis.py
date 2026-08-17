import pytest

from analytics.cashflow_kpis import (
    calculate_fcf_cagr_5yr,
    deleveraging_signal,
    distress_signal,
)


def test_distress_signal_requires_negative_cfo_and_positive_cff():
    assert distress_signal(-10, 5) is True
    assert distress_signal(10, 5) is False
    assert distress_signal(-10, -5) is False
    assert distress_signal(None, 5) is False


def test_deleveraging_requires_negative_cff_and_declining_borrowings():
    assert deleveraging_signal(-20, 80, 100) is True
    assert deleveraging_signal(20, 80, 100) is False
    assert deleveraging_signal(-20, 100, 100) is False
    assert deleveraging_signal(-20, None, 100) is False


def test_fcf_cagr_uses_five_year_interval_and_rejects_nonpositive_endpoints():
    assert calculate_fcf_cagr_5yr({2019: 100, 2024: 161.051}, 2024) == pytest.approx(10)
    assert calculate_fcf_cagr_5yr({2019: -100, 2024: -50}, 2024) is None
    assert calculate_fcf_cagr_5yr({2019: 100, 2024: -50}, 2024) is None
