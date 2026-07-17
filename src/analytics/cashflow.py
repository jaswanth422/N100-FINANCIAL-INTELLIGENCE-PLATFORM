"""Cash-flow KPIs and capital-allocation classification."""

from __future__ import annotations

import csv
import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from numbers import Real
from pathlib import Path

CFO_QUALITY_YEARS = 5
CFO_HIGH_QUALITY_THRESHOLD = 1.0
CFO_MODERATE_THRESHOLD = 0.5


def _number(value: object) -> float | None:
    """Return a finite number while rejecting booleans and missing values."""
    if value is None or isinstance(value, bool) or not isinstance(value, Real):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def free_cash_flow(
    operating_activity: Real | None,
    investing_activity: Real | None,
) -> float | None:
    """Calculate CFO + CFI; negative free cash flow remains a valid result."""
    cfo = _number(operating_activity)
    cfi = _number(investing_activity)
    if cfo is None or cfi is None:
        return None
    return cfo + cfi


def cfo_quality_score(
    operating_cash_flows: Iterable[Real | None],
    net_profits: Iterable[Real | None],
) -> float | None:
    """Average annual CFO/PAT over the latest five aligned years.

    At least five observations are required. A missing value or zero PAT in the
    selected window makes the score unavailable.
    """
    cfo_values = list(operating_cash_flows)
    pat_values = list(net_profits)
    if len(cfo_values) < CFO_QUALITY_YEARS or len(pat_values) < CFO_QUALITY_YEARS:
        return None

    cfo_window = cfo_values[-CFO_QUALITY_YEARS:]
    pat_window = pat_values[-CFO_QUALITY_YEARS:]
    ratios: list[float] = []
    for cfo_value, pat_value in zip(cfo_window, pat_window, strict=True):
        cfo = _number(cfo_value)
        pat = _number(pat_value)
        if cfo is None or pat is None or pat == 0:
            return None
        ratios.append(cfo / pat)
    return sum(ratios) / CFO_QUALITY_YEARS


def classify_cfo_quality(score: Real | None) -> str | None:
    """Classify a five-year CFO/PAT quality score."""
    value = _number(score)
    if value is None:
        return None
    if value > CFO_HIGH_QUALITY_THRESHOLD:
        return "High Quality"
    if value >= CFO_MODERATE_THRESHOLD:
        return "Moderate"
    return "Accrual Risk"


def capex_intensity(
    investing_activity: Real | None,
    sales: Real | None,
) -> float | None:
    """Calculate abs(CFI) / sales * 100; zero sales has no meaningful ratio."""
    cfi = _number(investing_activity)
    revenue = _number(sales)
    if cfi is None or revenue is None or revenue == 0:
        return None
    return abs(cfi) / revenue * 100


def classify_capex_intensity(intensity_pct: Real | None) -> str | None:
    """Classify CapEx intensity using the 3% and 8% boundaries."""
    intensity = _number(intensity_pct)
    if intensity is None:
        return None
    if intensity < 3:
        return "Asset Light"
    if intensity <= 8:
        return "Moderate"
    return "Capital Intensive"


def fcf_conversion_rate(
    free_cash_flow_value: Real | None,
    operating_profit: Real | None,
) -> float | None:
    """Calculate FCF / operating profit * 100."""
    fcf = _number(free_cash_flow_value)
    profit = _number(operating_profit)
    if fcf is None or profit is None or profit == 0:
        return None
    return fcf / profit * 100


def cash_flow_sign(value: Real | None) -> str | None:
    """Return ``+``, ``-``, or ``0`` for a cash-flow value."""
    number = _number(value)
    if number is None:
        return None
    if number > 0:
        return "+"
    if number < 0:
        return "-"
    return "0"


def classify_capital_allocation(
    operating_activity: Real | None,
    investing_activity: Real | None,
    financing_activity: Real | None,
    *,
    cfo_pat_ratio: Real | None = None,
) -> str | None:
    """Classify capital allocation from CFO, CFI, and CFF signs.

    The otherwise unspecified ``(-,+,-)`` combination and combinations containing
    a zero cash flow use the neutral ``Mixed`` label.
    """
    signs = (
        cash_flow_sign(operating_activity),
        cash_flow_sign(investing_activity),
        cash_flow_sign(financing_activity),
    )
    if any(sign is None for sign in signs):
        return None
    if "0" in signs:
        return "Mixed"

    if signs == ("+", "-", "-"):
        ratio = _number(cfo_pat_ratio)
        if ratio is not None and ratio > CFO_HIGH_QUALITY_THRESHOLD:
            return "Shareholder Returns"
        return "Reinvestor"

    patterns = {
        ("+", "+", "-"): "Liquidating Assets",
        ("-", "+", "+"): "Distress Signal",
        ("-", "-", "+"): "Growth Funded by Debt",
        ("+", "+", "+"): "Cash Accumulator",
        ("-", "-", "-"): "Pre-Revenue",
        ("+", "-", "+"): "Mixed",
        ("-", "+", "-"): "Mixed",
    }
    return patterns[signs]


@dataclass(frozen=True)
class CapitalAllocationRow:
    """One row in the capital-allocation output report."""

    company_id: str
    year: int
    cfo_sign: str
    cfi_sign: str
    cff_sign: str
    pattern_label: str


def build_capital_allocation_row(
    *,
    company_id: str,
    year: int,
    operating_activity: Real,
    investing_activity: Real,
    financing_activity: Real,
    net_profit: Real | None = None,
) -> CapitalAllocationRow:
    """Build a report row, using annual CFO/PAT for the shareholder-return test."""
    cfo = _number(operating_activity)
    pat = _number(net_profit)
    ratio = None if cfo is None or pat is None or pat == 0 else cfo / pat
    cfo_sign = cash_flow_sign(operating_activity)
    cfi_sign = cash_flow_sign(investing_activity)
    cff_sign = cash_flow_sign(financing_activity)
    label = classify_capital_allocation(
        operating_activity,
        investing_activity,
        financing_activity,
        cfo_pat_ratio=ratio,
    )
    if cfo_sign is None or cfi_sign is None or cff_sign is None or label is None:
        raise ValueError("capital-allocation inputs must be finite numbers")
    return CapitalAllocationRow(company_id, year, cfo_sign, cfi_sign, cff_sign, label)


def write_capital_allocation_csv(
    rows: Iterable[CapitalAllocationRow],
    output_path: str | Path,
) -> Path:
    """Write capital-allocation rows with a stable six-column schema."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(CapitalAllocationRow.__dataclass_fields__)
    records = [asdict(row) for row in rows]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    return path.resolve()


def generate_capital_allocation_report(
    source_dir: str | Path,
    output_path: str | Path,
) -> Path:
    """Generate the company-year capital-allocation report from source workbooks.

    If normalization produces duplicate company-year keys, the row with the latest
    source ``id`` is retained so the six-column report remains uniquely keyed.
    """
    from nifty100_etl.loader import ExcelSource, load_excel

    root = Path(source_dir)
    cash_flows = load_excel(
        ExcelSource(root / "cashflow.xlsx", "financial_statements", "cash_flow")
    )
    profits = load_excel(
        ExcelSource(root / "profitandloss.xlsx", "financial_statements", "profit_and_loss")
    )

    key = ["company_id", "year"]
    cash_flows = cash_flows.sort_values("id").drop_duplicates(key, keep="last")
    cash_flows = cash_flows.dropna(
        subset=["operating_activity", "investing_activity", "financing_activity"]
    )
    profits = (
        profits.dropna(subset=["year"])
        .sort_values("id")
        .drop_duplicates(key, keep="last")
    )
    combined = cash_flows.merge(
        profits[key + ["net_profit"]],
        how="left",
        on=key,
        validate="one_to_one",
    ).sort_values(key)

    rows = (
        build_capital_allocation_row(
            company_id=str(row.company_id),
            year=int(row.year),
            operating_activity=row.operating_activity,
            investing_activity=row.investing_activity,
            financing_activity=row.financing_activity,
            net_profit=row.net_profit,
        )
        for row in combined.itertuples(index=False)
    )
    return write_capital_allocation_csv(rows, output_path)
