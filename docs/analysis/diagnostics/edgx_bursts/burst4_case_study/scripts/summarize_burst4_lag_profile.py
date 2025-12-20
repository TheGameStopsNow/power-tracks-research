"""
Summarize the future return profile and option lag contributions for the
2024-05-17 08:03:26 ET burst ("burst4 main").

Outputs:
- CSV table listing future closes/returns at standard horizons.
- CSV + PNG summarizing per-lag (1,4,7 days) option notional, call/put mix,
  and ATM/OTM composition.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

matplotlib.use("Agg")

BURST_ID = "2024-05-17_2024-05-17 08:03:26-04:00"


def load_future_returns(base: Path) -> pd.Series:
    df = pd.read_csv(base / "burst_future_with_options.csv")
    row = df[df["burst_id"] == BURST_ID]
    if row.empty:
        raise SystemExit(f"{BURST_ID} not found in burst_future_with_options.csv")
    return row.iloc[0]


def write_future_return_table(row: pd.Series, out_dir: Path) -> None:
    horizons = [
        ("close", "0d"),
        ("close_fwd_1d", "1d"),
        ("close_fwd_5d", "5d"),
        ("close_fwd_20d", "20d"),
        ("close_fwd_60d", "60d"),
        ("close_fwd_120d", "120d"),
        ("close_fwd_250d", "250d"),
        ("close_fwd_360d", "360d"),
        ("close_fwd_500d", "500d"),
    ]
    records = []
    for col, label in horizons:
        price = row.get(col)
        ret_col = col.replace("close_fwd", "return")
        ret = row.get(ret_col, float("nan"))
        records.append({"horizon": label, "price": price, "return_pct": ret})
    table = pd.DataFrame(records)
    table.to_csv(out_dir / "burst4_future_return_profile.csv", index=False)


def load_lag_summary(base: Path) -> pd.DataFrame:
    summary = pd.read_csv(base / "burst_option_summary.csv")
    lag_rows = summary[summary["burst_id"] == BURST_ID].copy()
    if lag_rows.empty:
        raise SystemExit(f"no option lag rows for {BURST_ID}")
    return lag_rows


def write_lag_breakdown(lag_rows: pd.DataFrame, out_dir: Path) -> None:
    # Keep only lags 1, 4, 7 (others exist but user emphasized these).
    lag_rows = lag_rows[lag_rows["lag_days"].isin([1, 4, 7])]
    if lag_rows.empty:
        raise SystemExit("no lag rows for days {1,4,7}")
    agg_cols = [
        "total_notional",
        "call_notional",
        "put_notional",
        "call_itm_notional",
        "call_atm_notional",
        "call_otm_notional",
        "put_itm_notional",
        "put_atm_notional",
        "put_otm_notional",
    ]
    lag_summary = (
        lag_rows.groupby("lag_days")[agg_cols]
        .sum()
        .assign(call_share=lambda df: df["call_notional"] / df["total_notional"])
        .reset_index()
    )
    lag_summary.to_csv(out_dir / "burst4_option_lag_breakdown.csv", index=False)

    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.bar(
        lag_summary["lag_days"].astype(int).astype(str),
        lag_summary["total_notional"] / 1e6,
        color="#4c72b0",
    )
    ax.set_xlabel("Lag days before burst")
    ax.set_ylabel("Total notional ($MM)")
    for idx, row in lag_summary.iterrows():
        ax.text(
            idx,
            row["total_notional"] / 1e6 + 1,
            f"{row['call_share']*100:.1f}% calls",
            ha="center",
            fontsize=8,
        )
    ax.set_title("Option ladder feeding burst4 (lag 1/4/7 breakdown)")
    fig.tight_layout()
    fig.savefig(out_dir / "burst4_option_lag_breakdown.png", dpi=200)
    plt.close(fig)


def main() -> None:
    base = Path("reports/diagnostics/edgx_bursts")
    burst_row = load_future_returns(base)
    write_future_return_table(burst_row, base)
    lag_rows = load_lag_summary(base)
    write_lag_breakdown(lag_rows, base)


if __name__ == "__main__":
    main()
