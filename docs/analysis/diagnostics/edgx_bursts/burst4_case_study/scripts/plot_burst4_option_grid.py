"""
Plot the option-ladder lattice that fed the 2024-05-17 08:03:26 ET burst.

Axes:
  - x: days to expiration (trade-date basis)
  - y: strike price
  - z: signed notional (calls positive, puts negative) scaled to [−1, 1]

A slider lets you toggle between the aggregated ladder (all lag days) and
each individual lookback day. This makes it easier to see how calls/puts
populate the lattice ahead of the burst.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import pandas as pd
import plotly.graph_objects as go

matplotlib.use("Agg")

BURST_ID = "2024-05-17_2024-05-17 08:03:26-04:00"


def load_burst_meta(base: Path) -> tuple[pd.Series, pd.Timestamp]:
    meta = pd.read_csv(base / "burst_future_with_options.csv")
    row = meta[meta["burst_id"] == BURST_ID]
    if row.empty:
        raise SystemExit(f"burst {BURST_ID} not found in burst_future_with_options.csv")
    row = row.iloc[0]
    start = pd.to_datetime(row["start"], utc=True).tz_convert("America/New_York")
    return row, start


def load_option_lag_summary(base: Path) -> pd.DataFrame:
    summary = pd.read_csv(base / "burst_option_summary.csv")
    subset = summary[summary["burst_id"] == BURST_ID].copy()
    if subset.empty:
        raise SystemExit(f"no option summary rows for {BURST_ID}")
    return subset


def load_option_trades(dates: list[pd.Timestamp]) -> pd.DataFrame:
    root = Path("reports/diagnostics/options_trades/GME")
    frames = []
    for day in dates:
        path = root / f"{day.year:04d}" / f"{day.month:02d}" / f"{day:%Y-%m-%d}.parquet"
        if not path.exists():
            # Skip silently; not all lag days have downloads.
            continue
        df = pd.read_parquet(path)
        df["trade_date"] = day
        frames.append(df)
    if not frames:
        raise SystemExit("no option trade parquet files found for requested lag days")
    data = pd.concat(frames, ignore_index=True)
    data["notional"] = data["price"] * data["size"] * 100.0
    data = data[data["notional"] > 0]
    data["contract_type"] = data["contract_type"].str.lower()
    return data


def aggregate_option_points(data: pd.DataFrame) -> pd.DataFrame:
    # Aggregate to strike/expiration/type per trade date.
    grouped = (
        data.groupby(
            ["trade_date", "expiration_date", "contract_type", "strike_price"], as_index=False
        )
        .agg(
            notional=("notional", "sum"),
            avg_price=("price", "mean"),
            avg_days_to_exp=("days_to_expiration", "mean"),
        )
    )
    grouped["trade_date"] = pd.to_datetime(grouped["trade_date"])
    grouped["expiration_date"] = pd.to_datetime(grouped["expiration_date"])
    grouped["days_to_exp"] = grouped["avg_days_to_exp"]

    max_notional = grouped["notional"].max()
    if max_notional <= 0:
        max_notional = 1.0
    sign = grouped["contract_type"].map({"call": 1.0, "put": -1.0}).fillna(0.0)
    grouped["signed_depth"] = sign * (grouped["notional"] / max_notional)
    grouped["size_scaled"] = 4 + 8 * (grouped["notional"] / max_notional)
    return grouped


def build_plot(grouped: pd.DataFrame) -> go.Figure:
    grouped = grouped.copy()
    grouped["lag_label"] = grouped["trade_date"].dt.strftime("%Y-%m-%d")
    datasets = [("All days", grouped)]
    for label in sorted(grouped["lag_label"].unique()):
        datasets.append((label, grouped[grouped["lag_label"] == label]))

    traces: list[go.Scatter3d] = []
    labels: list[str] = []
    for dataset_idx, (label, df) in enumerate(datasets):
        for opt_type, color in [("call", "#ff8c00"), ("put", "#1f77b4")]:
            sub = df[df["contract_type"] == opt_type]
            visible = dataset_idx == 0  # show aggregated view by default
            traces.append(
                go.Scatter3d(
                    x=sub["days_to_exp"],
                    y=sub["strike_price"],
                    z=sub["signed_depth"],
                    mode="markers",
                    visible=visible,
                    marker=dict(
                        size=sub["size_scaled"],
                        color=sub["strike_price"],
                        colorscale="Viridis",
                        opacity=0.85,
                        colorbar=dict(title="Strike"),
                        showscale=dataset_idx == 0 and opt_type == "call",
                    ),
                    name=f"{label} {opt_type}",
                    hovertemplate=(
                        "trade day=%{customdata[0]}<br>"
                        "expiry=%{customdata[1]}<br>"
                        "strike=%{customdata[2]:.2f}<br>"
                        "type=%{customdata[3]}<br>"
                        "notional=$%{customdata[4]:,.0f}<extra></extra>"
                    ),
                    customdata=sub[
                        [
                            "lag_label",
                            "expiration_date",
                            "strike_price",
                            "contract_type",
                            "notional",
                        ]
                    ],
                )
            )
        labels.append(label)

    steps = []
    for dataset_idx, label in enumerate(labels):
        visibility = [False] * len(traces)
        base = dataset_idx * 2
        visibility[base] = True
        visibility[base + 1] = True
        steps.append({"label": label, "method": "update", "args": [{"visible": visibility}, {}]})

    slider = {"active": 0, "currentvalue": {"prefix": "Lag day: "}, "steps": steps, "pad": {"t": 30}}

    fig = go.Figure(data=traces)
    fig.update_layout(
        title="Option lattice feeding burst4 (x=days to exp, y=strike, z=call-vs-put)",
        sliders=[slider],
        scene=dict(
            xaxis=dict(title="Days to expiration"),
            yaxis=dict(title="Strike ($)"),
            zaxis=dict(title="Signed notional depth"),
        ),
        margin=dict(l=0, r=0, b=0, t=80),
    )
    return fig


def main() -> None:
    base = Path("reports/diagnostics/edgx_bursts")
    burst_row, burst_start = load_burst_meta(base)
    option_summary = load_option_lag_summary(base)
    lag_days = sorted(option_summary["lag_days"].dropna().unique().astype(int))
    lag_dates = [(burst_start - pd.Timedelta(days=int(lag))).normalize() for lag in lag_days]

    option_trades = load_option_trades(lag_dates)
    grouped = aggregate_option_points(option_trades)
    fig = build_plot(grouped)
    out_html = base / "burst4_option_grid_3d.html"
    fig.write_html(out_html, include_plotlyjs="cdn")
    print(f"saved {out_html}")


if __name__ == "__main__":
    main()

