"""Day 13 ratio cross-checks and categorized anomaly logging."""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RatioAnomaly:
    company_id: str
    company_name: str
    metric: str
    year: int
    computed: float
    source_display: float
    difference_pp: float
    category: str
    explanation: str


def _categorize(
    *,
    metric: str,
    computed: float,
    source: float,
    difference: float,
    year: int,
    broad_sector: str | None,
) -> tuple[str, str]:
    if abs(computed) > 200 or (abs(source) < 1 and abs(computed) > 10):
        return (
            "data source issue",
            "Implausible source or statement input scale; retain engine value for analytics "
            "and source value for display only.",
        )
    if year < 2024 or difference <= 15:
        return (
            "version difference",
            "Source summary and latest normalized annual statements appear to use different "
            "periods or data versions.",
        )
    if metric == "ROCE" and broad_sector == "Financials":
        return (
            "formula discrepancy",
            "Standard capital-employed ROCE is not economically comparable for a leveraged "
            "financial institution; sector-relative review is required.",
        )
    return (
        "formula discrepancy",
        "Engine uses normalized annual statement inputs and the documented Sprint 2 formula; "
        "source summary methodology is not available.",
    )


def collect_ratio_anomalies(
    connection: sqlite3.Connection,
    *,
    tolerance_pp: float = 5.0,
) -> list[RatioAnomaly]:
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        WITH ranked AS (
            SELECT r.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY r.company_id ORDER BY r.year DESC, r.id DESC
                   ) AS rank_no
            FROM financial_ratios r
            WHERE r.year IS NOT NULL
        )
        SELECT c.id AS company_id, c.company_name, c.roe_percentage, c.roce_percentage,
               s.broad_sector, r.year, r.return_on_equity_pct, r.return_on_capital_employed_pct
        FROM companies c
        JOIN ranked r ON r.company_id = c.id AND r.rank_no = 1
        LEFT JOIN sectors s ON s.company_id = c.id
        ORDER BY c.id
        """
    )
    anomalies: list[RatioAnomaly] = []
    for row in rows:
        pairs = (
            ("ROE", row["return_on_equity_pct"], row["roe_percentage"]),
            ("ROCE", row["return_on_capital_employed_pct"], row["roce_percentage"]),
        )
        for metric, computed_raw, source_raw in pairs:
            if computed_raw is None or source_raw is None:
                continue
            computed = float(computed_raw)
            source = float(source_raw)
            difference = abs(computed - source)
            if difference <= tolerance_pp:
                continue
            category, explanation = _categorize(
                metric=metric,
                computed=computed,
                source=source,
                difference=difference,
                year=int(row["year"]),
                broad_sector=row["broad_sector"],
            )
            anomalies.append(
                RatioAnomaly(
                    company_id=row["company_id"],
                    company_name=row["company_name"],
                    metric=metric,
                    year=int(row["year"]),
                    computed=computed,
                    source_display=source,
                    difference_pp=difference,
                    category=category,
                    explanation=explanation,
                )
            )
    return anomalies


def write_ratio_edge_case_log(
    anomalies: list[RatioAnomaly],
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    category_counts = {
        category: sum(item.category == category for item in anomalies)
        for category in ("data source issue", "version difference", "formula discrepancy")
    }
    lines = [
        "SPRINT 2 RATIO EDGE CASE REVIEW",
        (
            "Rule: latest computed ROE/ROCE versus companies source display; anomaly if "
            ">5 percentage points."
        ),
        (
            "Policy: computed engine values drive analytics; companies.xlsx values remain "
            "display-only."
        ),
        (
            "Financials: D/E warning suppressed for every company classified in "
            "broad_sector=Financials."
        ),
        (
            "Dataset note: current sectors source contains 23 Financials companies, not the "
            "expected 19."
        ),
        f"Anomalies: {len(anomalies)} | Categories: {category_counts}",
        "",
    ]
    for item in anomalies:
        company_name = " ".join(item.company_name.split())
        lines.append(
            f"company_id={item.company_id} | company_name={company_name} | "
            f"metric={item.metric} | year={item.year} | computed={item.computed:.4f}% | "
            f"source_display={item.source_display:.4f}% | difference={item.difference_pp:.4f}pp | "
            f"category={item.category} | explanation={item.explanation}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path.resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate categorized ratio edge-case log")
    parser.add_argument("--database", default="nifty100.db")
    parser.add_argument("--output", default="output/ratio_edge_cases.log")
    args = parser.parse_args()
    connection = sqlite3.connect(args.database)
    try:
        anomalies = collect_ratio_anomalies(connection)
    finally:
        connection.close()
    path = write_ratio_edge_case_log(anomalies, args.output)
    print(f"Wrote {len(anomalies)} categorized anomalies to {path}")


if __name__ == "__main__":
    main()
