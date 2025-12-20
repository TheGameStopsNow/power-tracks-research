"""
Layer burst4 (08:03:26–08:05:05 ET) into per-tick slices so we can see how each
normalized time band contributes to the overall drawing.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

matplotlib.use("Agg")


def main() -> None:
    base = Path("reports/diagnostics/edgx_bursts")
    burst_id = "2024-05-17_2024-05-17 08:03:26-04:00"
    points = pd.read_parquet(base / "normalized_points.parquet")
    pts = points[points["burst_id"] == burst_id].copy()
    if pts.empty:
        raise SystemExit(f"no normalized points for {burst_id}")

    bin_edges = np.linspace(0, 1, 11)  # 10 ticks (0.0,0.1,...1.0)
    pts["bin"] = pd.cut(
        pts["norm_x"],
        bins=bin_edges,
        labels=[f"{i}" for i in range(10)],
        include_lowest=True,
        right=False,
    )

    # Multi-panel view
    fig, axes = plt.subplots(5, 2, figsize=(10, 14))
    axes = axes.ravel()
    for idx in range(10):
        ax = axes[idx]
        subset = pts[pts["bin"] == str(idx)]
        if subset.empty:
            ax.text(0.5, 0.5, "empty", ha="center", va="center", fontsize=10)
            ax.set_axis_off()
            continue
        width = bin_edges[idx + 1] - bin_edges[idx]
        local_x = (subset["norm_x"] - bin_edges[idx]) / width
        ax.scatter(local_x, subset["norm_y"], s=6, alpha=0.7)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_title(f"slice {idx} ({bin_edges[idx]:.1f}-{bin_edges[idx+1]:.1f})")
        ax.set_xticks([])
        ax.set_yticks([])

    fig.suptitle("Burst4 face — per-tick slices (normalized time bands)")
    fig.tight_layout(rect=[0, 0, 1, 0.98])
    out_grid = base / "normalized_burst4_layers.png"
    fig.savefig(out_grid, dpi=200)
    plt.close(fig)

    # Overlay view: collapse each time band to 0-1 and color by bin
    colors = plt.cm.viridis(np.linspace(0, 1, 10))
    fig2, ax2 = plt.subplots(figsize=(6, 6))
    for idx in range(10):
        subset = pts[pts["bin"] == str(idx)]
        if subset.empty:
            continue
        width = bin_edges[idx + 1] - bin_edges[idx]
        local_x = (subset["norm_x"] - bin_edges[idx]) / width
        ax2.scatter(local_x, subset["norm_y"], s=6, alpha=0.7, color=colors[idx], label=f"{idx}")
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)
    ax2.set_xlabel("normalized time within slice")
    ax2.set_ylabel("normalized price")
    ax2.set_title("Burst4 face — all slices collapsed (color = time tick)")
    ax2.legend(title="slice", bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=8)
    fig2.tight_layout()
    out_overlay = base / "normalized_burst4_layers_overlay.png"
    fig2.savefig(out_overlay, dpi=200)
    plt.close(fig2)

    print(f"saved {out_grid}")
    print(f"saved {out_overlay}")


if __name__ == "__main__":
    main()

