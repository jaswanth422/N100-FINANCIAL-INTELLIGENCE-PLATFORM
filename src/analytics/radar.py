"""Peer-relative radar charts and unassigned-company fallback charts."""

from __future__ import annotations

import argparse
import os
import sqlite3
import tempfile
from pathlib import Path

# Keep Matplotlib/font caches in a writable location in restricted CI runners.
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "n100-matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .peer import (  # noqa: E402
    DEFAULT_PEER_GROUPS,
    compute_peer_percentiles,
    load_peer_groups,
    load_ratio_universe,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "reports" / "radar_charts"

RADAR_AXES: tuple[tuple[str, str], ...] = (
    ("ROE", "ROE"),
    ("ROCE", "ROCE"),
    ("NPM", "Net Profit Margin"),
    ("D/E", "D/E"),
    ("FCF score", "FCF"),
    ("PAT CAGR 5yr", "PAT CAGR 5yr"),
    ("Revenue CAGR 5yr", "Revenue CAGR 5yr"),
)


def _close_polygon(values: list[float]) -> list[float]:
    return [*values, values[0]]


def _draw_peer_radar(
    *,
    company_name: str,
    peer_group_name: str,
    company_values: list[float],
    peer_values: list[float],
    output_path: Path,
) -> None:
    labels = [axis[0] for axis in RADAR_AXES] + ["Composite Score"]
    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
    closed_angles = _close_polygon(angles)

    figure, axis = plt.subplots(figsize=(8, 8), subplot_kw={"polar": True})
    axis.plot(
        closed_angles,
        _close_polygon(company_values),
        color="#1565C0",
        linewidth=2.2,
        label=company_name,
    )
    axis.fill(closed_angles, _close_polygon(company_values), color="#42A5F5", alpha=0.28)
    axis.plot(
        closed_angles,
        _close_polygon(peer_values),
        color="#EF6C00",
        linewidth=2.0,
        linestyle="--",
        label=f"{peer_group_name} average",
    )
    axis.set_xticks(angles)
    axis.set_xticklabels(labels, fontsize=10)
    axis.set_ylim(0, 100)
    axis.set_yticks([20, 40, 60, 80, 100])
    axis.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=8, color="#616161")
    axis.set_title(f"{company_name}\nPeer-relative quality profile", fontsize=14, pad=24)
    axis.legend(loc="upper right", bbox_to_anchor=(1.32, 1.15), fontsize=9)
    axis.grid(color="#BDBDBD", alpha=0.65)
    figure.tight_layout()
    figure.savefig(output_path, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def _draw_standalone_composite(
    *,
    company_name: str,
    company_score: float,
    nifty_average: float,
    output_path: Path,
) -> None:
    """Draw the requested single-metric fallback when no peer group exists."""
    figure, axis = plt.subplots(figsize=(7.2, 4.8))
    bars = axis.bar(
        [company_name, "Nifty 100 average"],
        [company_score, nifty_average],
        color=["#1565C0", "#EF6C00"],
        width=0.58,
    )
    axis.set_ylim(0, 100)
    axis.set_ylabel("Composite quality score (0-100)", fontsize=11)
    axis.set_title(f"{company_name}\nNo peer group assigned", fontsize=14)
    axis.grid(axis="y", alpha=0.3)
    axis.tick_params(axis="x", labelsize=10)
    for bar, value in zip(bars, [company_score, nifty_average], strict=True):
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            min(99, value + 2),
            f"{value:.1f}",
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold",
        )
    figure.tight_layout()
    figure.savefig(output_path, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def generate_radar_charts(
    database: str | Path | sqlite3.Connection,
    *,
    peer_groups_path: str | Path = DEFAULT_PEER_GROUPS,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    year: int | None = None,
) -> pd.DataFrame:
    """Generate peer radars for assigned firms and composite fallbacks otherwise."""
    owns_connection = not isinstance(database, sqlite3.Connection)
    connection = sqlite3.connect(str(database)) if owns_connection else database
    assert isinstance(connection, sqlite3.Connection)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    try:
        ratios = load_ratio_universe(connection, year=year)
        companies = pd.read_sql_query(
            "SELECT id AS company_id, company_name FROM companies ORDER BY id", connection
        )
        universe = companies.merge(ratios, on="company_id", how="inner", validate="one_to_one")
        assignments = load_peer_groups(peer_groups_path)[["peer_group_name", "company_id"]]
        assignments = assignments.drop_duplicates(["company_id"], keep="first")
        percentiles = compute_peer_percentiles(ratios, assignments)
        rank_matrix = percentiles.pivot_table(
            index=["peer_group_name", "company_id"],
            columns="metric",
            values="percentile_rank",
            aggfunc="first",
        )

        group_members = assignments.merge(
            ratios[["company_id", "composite_quality_score"]],
            on="company_id",
            how="left",
        )
        group_composite_average = group_members.groupby("peer_group_name")[
            "composite_quality_score"
        ].mean()
        peer_rank_average = rank_matrix.groupby(level="peer_group_name").mean() * 100.0
        nifty_average = float(
            pd.to_numeric(universe["composite_quality_score"], errors="coerce").mean()
        )
        if not np.isfinite(nifty_average):
            nifty_average = 50.0

        assignment_map = assignments.set_index("company_id")["peer_group_name"].to_dict()
        manifests: list[dict[str, object]] = []
        for row in universe.itertuples(index=False):
            company_id = str(row.company_id)
            company_name = str(row.company_name).strip()
            company_score = (
                float(row.composite_quality_score)
                if pd.notna(row.composite_quality_score)
                else 50.0
            )
            chart_path = output / f"{company_id}_radar.png"
            peer_group = assignment_map.get(company_id)
            if peer_group is None:
                _draw_standalone_composite(
                    company_name=company_name,
                    company_score=company_score,
                    nifty_average=nifty_average,
                    output_path=chart_path,
                )
                chart_type = "standalone"
                reference = "Nifty 100 average"
            else:
                try:
                    company_rank_row = rank_matrix.loc[(peer_group, company_id)]
                except KeyError:
                    company_rank_row = pd.Series(dtype="float64")
                company_values = [
                    float(company_rank_row.get(metric_label, np.nan)) * 100.0
                    for _, metric_label in RADAR_AXES
                ] + [company_score]
                peer_values = [
                    float(peer_rank_average.loc[peer_group].get(metric_label, np.nan))
                    for _, metric_label in RADAR_AXES
                ] + [float(group_composite_average.get(peer_group, nifty_average))]
                company_values = [
                    50.0 if not np.isfinite(value) else value for value in company_values
                ]
                peer_values = [50.0 if not np.isfinite(value) else value for value in peer_values]
                _draw_peer_radar(
                    company_name=company_name,
                    peer_group_name=str(peer_group),
                    company_values=company_values,
                    peer_values=peer_values,
                    output_path=chart_path,
                )
                chart_type = "radar"
                reference = str(peer_group)
            manifests.append(
                {
                    "company_id": company_id,
                    "company_name": company_name,
                    "chart_type": chart_type,
                    "reference": reference,
                    "path": str(chart_path.resolve()),
                }
            )
        return pd.DataFrame(manifests)
    finally:
        if owns_connection:
            connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate company peer radar charts")
    parser.add_argument("--database", default="nifty100.db")
    parser.add_argument("--peer-groups", default=str(DEFAULT_PEER_GROUPS))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--year", type=int)
    args = parser.parse_args()
    manifest = generate_radar_charts(
        args.database,
        peer_groups_path=args.peer_groups,
        output_dir=args.output_dir,
        year=args.year,
    )
    counts = manifest["chart_type"].value_counts().to_dict()
    print(
        f"Generated {len(manifest)} charts in {Path(args.output_dir)} "
        f"({counts.get('radar', 0)} peer radars, {counts.get('standalone', 0)} standalone)"
    )


if __name__ == "__main__":
    main()
