"""Reproducible Nifty 100 financial-archetype clustering and diagnostics."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEATURES = (
    "return_on_equity_pct",
    "debt_to_equity",
    "revenue_cagr_5yr",
    "fcf_cagr_5yr",
    "operating_profit_margin_pct",
)
CORRELATION_KPIS = (
    "return_on_equity_pct",
    "return_on_capital_employed_pct",
    "net_profit_margin_pct",
    "operating_profit_margin_pct",
    "debt_to_equity",
    "interest_coverage",
    "revenue_cagr_5yr",
    "pat_cagr_5yr",
    "fcf_cagr_5yr",
    "free_cash_flow_cr",
)


def latest_ratio_universe(database: str | Path = PROJECT_ROOT / "nifty100.db") -> pd.DataFrame:
    """Return one latest ratio observation and sector for every company."""
    with sqlite3.connect(database) as connection:
        result = pd.read_sql_query(
            """
            WITH ranked AS (
                SELECT fr.*, ROW_NUMBER() OVER (
                    PARTITION BY company_id ORDER BY year DESC, id DESC
                ) AS row_number
                FROM financial_ratios fr
            )
            SELECT c.id AS company_id, c.company_name, s.broad_sector, r.*
            FROM companies c
            LEFT JOIN sectors s ON s.company_id = c.id
            LEFT JOIN ranked r ON r.company_id = c.id AND r.row_number = 1
            ORDER BY c.id
            """,
            connection,
        )
    return result.loc[:, ~result.columns.duplicated()]


def impute_sector_medians(
    frame: pd.DataFrame, features: tuple[str, ...] = FEATURES
) -> pd.DataFrame:
    """Fill missing metric values using the corresponding broad-sector median."""
    result = frame.copy()
    sector = result["broad_sector"].fillna("Unclassified")
    for feature in features:
        values = pd.to_numeric(result[feature], errors="coerce").replace([np.inf, -np.inf], np.nan)
        result[feature] = values.fillna(values.groupby(sector).transform("median")).fillna(
            values.median()
        )
    return result


def _cluster_names(centers: np.ndarray) -> dict[int, str]:
    """Map raw cluster identifiers to stable, financially meaningful archetype names."""
    # Higher quality rewards profitability, growth and cash-flow; leverage is a penalty.
    quality = centers[:, 0] - centers[:, 1] + centers[:, 2] + centers[:, 3] + centers[:, 4]
    growth = centers[:, 2] + centers[:, 3]
    defensive = centers[:, 0] + centers[:, 4] - centers[:, 1] - np.abs(centers[:, 2])
    remaining = set(range(5))
    mapping: dict[int, str] = {}
    high_quality = int(np.argmax(quality))
    mapping[high_quality] = "High-Quality Compounders"
    remaining.remove(high_quality)
    distressed = min(remaining, key=lambda index: quality[index])
    mapping[distressed] = "Distressed or Turnaround"
    remaining.remove(distressed)
    emerging = max(remaining, key=lambda index: growth[index])
    mapping[emerging] = "Emerging Growth"
    remaining.remove(emerging)
    defensive_cluster = max(remaining, key=lambda index: defensive[index])
    mapping[defensive_cluster] = "Defensive Dividend Payers"
    remaining.remove(defensive_cluster)
    mapping[remaining.pop()] = "Value Cyclicals"
    return mapping


def generate_clustering_artifacts(
    database: str | Path = PROJECT_ROOT / "nifty100.db",
    output_dir: str | Path = PROJECT_ROOT / "output",
    reports_dir: str | Path = PROJECT_ROOT / "reports",
) -> pd.DataFrame:
    """Cluster all companies and write labels, elbow, heatmap, outliers and KPI statistics."""
    output = Path(output_dir)
    reports = Path(reports_dir)
    output.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    universe = impute_sector_medians(latest_ratio_universe(database))
    scaled = StandardScaler().fit_transform(universe.loc[:, FEATURES])
    model = KMeans(n_clusters=5, random_state=42, n_init=20)
    clusters = model.fit_predict(scaled)
    names = _cluster_names(model.cluster_centers_)
    distances = np.linalg.norm(scaled - model.cluster_centers_[clusters], axis=1)
    labels = pd.DataFrame(
        {
            "company_id": universe["company_id"],
            "cluster_id": clusters,
            "cluster_name": [names[int(cluster)] for cluster in clusters],
            "distance_from_centroid": distances.round(6),
        }
    )
    labels.to_csv(output / "cluster_labels.csv", index=False)

    inertias = [
        KMeans(n_clusters=k, random_state=42, n_init=20).fit(scaled).inertia_ for k in range(2, 11)
    ]
    figure, axis = plt.subplots(figsize=(8, 5))
    axis.plot(range(2, 11), inertias, marker="o", color="#1565C0")
    axis.set(
        xlabel="Number of clusters (k)", ylabel="Inertia", title="Nifty 100 KMeans elbow curve"
    )
    axis.axvline(5, color="#EF6C00", linestyle="--", label="Selected k = 5")
    axis.legend()
    figure.tight_layout()
    figure.savefig(reports / "elbow_plot.png", dpi=160)
    plt.close(figure)

    correlations = universe.loc[:, CORRELATION_KPIS].apply(pd.to_numeric, errors="coerce").corr()
    figure, axis = plt.subplots(figsize=(12, 9))
    sns.heatmap(correlations, cmap="vlag", center=0, annot=True, fmt=".2f", square=True, ax=axis)
    axis.set_title("Latest-year KPI correlations")
    figure.tight_layout()
    figure.savefig(reports / "correlation_heatmap.png", dpi=160)
    plt.close(figure)

    outlier_frames: list[pd.DataFrame] = []
    for metric in FEATURES:
        values = universe[metric]
        sector_mean = values.groupby(universe["broad_sector"]).transform("mean")
        sector_std = values.groupby(universe["broad_sector"]).transform("std").replace(0, np.nan)
        z_score = (values - sector_mean) / sector_std
        flagged = universe.loc[
            z_score.abs() > 3, ["company_id", "company_name", "broad_sector"]
        ].copy()
        flagged["metric"] = metric
        flagged["value"] = values.loc[flagged.index]
        flagged["z_score"] = z_score.loc[flagged.index]
        outlier_frames.append(flagged)
    outliers = pd.concat(outlier_frames, ignore_index=True) if outlier_frames else pd.DataFrame()
    outliers.to_csv(output / "outlier_report.csv", index=False)

    kpis = universe.loc[:, CORRELATION_KPIS].apply(pd.to_numeric, errors="coerce")
    stats = (
        pd.DataFrame(
            {
                "P10": kpis.quantile(0.10),
                "P25": kpis.quantile(0.25),
                "P50": kpis.quantile(0.50),
                "P75": kpis.quantile(0.75),
                "P90": kpis.quantile(0.90),
                "Mean": kpis.mean(),
                "Std": kpis.std(),
            }
        )
        .rename_axis("kpi")
        .reset_index()
    )
    stats.to_csv(output / "portfolio_stats.csv", index=False)
    return labels


if __name__ == "__main__":
    generate_clustering_artifacts()
