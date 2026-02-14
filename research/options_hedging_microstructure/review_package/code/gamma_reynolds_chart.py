#!/usr/bin/env python3
"""
Gamma Reynolds Sigmoid Chart
==============================
Generates a publication-quality chart showing the ACF Spectrum across
37 tickers, with squeeze-era data points (GME, AMC) placed as empirical
anchors on the amplified side, revealing the full transition landscape.

Then fits a sigmoid across both regimes (using squeeze-era data).
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from scipy.optimize import curve_fit

RESULTS_DIR = Path(__file__).resolve().parent / "results"
OUTPUT_DIR = Path(__file__).resolve().parent / "figures"
MIN_DAYS = 95  # Exclude tickers with fewer than this many observation days


def sigmoid(x, L, k, x0, b):
    """Generalized sigmoid: L / (1 + exp(-k*(x - x0))) + b"""
    return L / (1 + np.exp(-k * (x - x0))) + b


def load_panel_data():
    """Load 37-ticker panel scan results."""
    path = RESULTS_DIR / "panel_scan_results.json"
    with open(path) as f:
        data = json.load(f)
    return data


def build_chart(data, output_path):
    """Build the Gamma Reynolds Sigmoid chart."""
    
    # Filter to tickers with sufficient observation days
    data = [d for d in data if d["n_days"] >= MIN_DAYS]
    print(f"  Retained {len(data)} / 37 tickers with >= {MIN_DAYS} days")
    
    symbols = [d["symbol"] for d in data]
    pct_amp = np.array([d["pct_amplified"] for d in data])
    mean_acf = np.array([d["mean_lag1"] for d in data])
    n_days = np.array([d["n_days"] for d in data])
    
    # === SQUEEZE-ERA DATA POINTS (from §5.4 of draft.md) ===
    # These are the empirical anchors on the amplified (Short Gamma) side
    squeeze_points = {
        "GME\n(Jan 2021)": {"pct_amp": 85, "mean_acf": +0.107},
        "AMC\n(Jun 2021)": {"pct_amp": 80, "mean_acf": +0.111},
    }
    
    # Classify tickers for color coding
    meme_tickers = {"GME", "AMC", "DJT", "PLTR", "HOOD", "LCID", "RIVN", "BYND"}
    mega_cap = {"AAPL", "MSFT", "TSLA", "NVDA", "SPY", "QQQ", "IWM"}
    
    colors = []
    for s in symbols:
        if s in meme_tickers:
            colors.append("#FF6B6B")   # Coral red — high speculative interest
        elif s in mega_cap:
            colors.append("#58A6FF")   # Blue — deep liquidity / mega-cap
        else:
            colors.append("#8B949E")   # Gray — mid-cap / standard
    
    # Marker sizes proportional to log(n_days)
    sizes = 35 + 90 * (np.log(n_days + 1) / np.log(n_days.max() + 1))
    
    # === FIT SIGMOID across BOTH regimes ===
    # Combine current-regime data with squeeze-era anchors
    all_x = np.concatenate([pct_amp, [85, 80]])
    all_y = np.concatenate([mean_acf, [0.107, 0.111]])
    
    try:
        popt, pcov = curve_fit(
            sigmoid, all_x, all_y,
            p0=[0.45, 0.15, 35, -0.30],
            maxfev=50000,
            bounds=(
                [0.1, 0.01, 10, -0.5],    # lower bounds
                [1.0, 1.0, 70, -0.01],     # upper bounds
            ),
        )
        x_fit = np.linspace(0, 100, 500)
        y_fit = sigmoid(x_fit, *popt)
        sigmoid_fitted = True
        
        # Find the inflection point (x0) — this is Re_Γ ≈ 1
        x0 = popt[2]
        y0 = sigmoid(x0, *popt)
        
        # Compute R²
        y_pred = sigmoid(all_x, *popt)
        ss_res = np.sum((all_y - y_pred) ** 2)
        ss_tot = np.sum((all_y - all_y.mean()) ** 2)
        r_squared = 1 - ss_res / ss_tot
    except (RuntimeError, ValueError) as e:
        print(f"Sigmoid fit failed: {e}")
        sigmoid_fitted = False
        r_squared = None
    
    # === BUILD FIGURE ===
    fig, ax = plt.subplots(figsize=(14, 8))
    fig.patch.set_facecolor("#0D1117")
    ax.set_facecolor("#161B22")
    
    # Grid
    ax.grid(True, alpha=0.12, color="#30363D", linewidth=0.5)
    
    # === PHASE REGIONS ===
    ax.axhspan(-0.45, 0, alpha=0.04, color="#3FB950")
    ax.axhspan(0, 0.20, alpha=0.04, color="#F85149")
    
    # Critical line
    ax.axhline(y=0, color="#58A6FF", linewidth=1.2, alpha=0.6, linestyle="--", zorder=2)
    
    # Phase labels — positioned away from data
    ax.text(50, -0.39, "LAMINAR STATE  (Long Gamma Default)",
            fontsize=12, color="#3FB950", fontweight="bold", alpha=0.4,
            ha="center", va="bottom", style="italic")
    ax.text(50, 0.155, "TURBULENT STATE",
            fontsize=12, color="#F85149", fontweight="bold", alpha=0.4,
            ha="center", va="top", style="italic")
    
    # === SIGMOID FIT ===
    if sigmoid_fitted:
        ax.plot(x_fit, y_fit, color="#F0883E", linewidth=3.0, alpha=0.85,
                zorder=3, label=f"Phase transition sigmoid (R² = {r_squared:.3f})")
        
        # Confidence band
        residuals_std = np.std(all_y - sigmoid(all_x, *popt))
        ax.fill_between(x_fit, y_fit - residuals_std, y_fit + residuals_std,
                        color="#F0883E", alpha=0.08, zorder=2)
        
        # Mark inflection point
        ax.plot(x0, y0, "D", color="#F0883E", markersize=14,
                markeredgecolor="white", markeredgewidth=2.0, zorder=6)
        ax.annotate(
            f"Critical transition\nRe_Γ ≈ 1\n({x0:.0f}% amplified days)",
            xy=(x0, y0),
            xytext=(x0 - 8, y0 + 0.10),
            fontsize=10, color="#F0883E", fontweight="bold",
            ha="left", va="bottom",
            arrowprops=dict(
                arrowstyle="->", color="#F0883E", lw=1.5,
                connectionstyle="arc3,rad=0.2",
            ),
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#21262D",
                      edgecolor="#F0883E", alpha=0.9),
        )
    
    # === SCATTER: Current regime (37 tickers) ===
    for i, sym in enumerate(symbols):
        ax.scatter(pct_amp[i], mean_acf[i], s=sizes[i], c=colors[i],
                   alpha=0.85, edgecolors="white", linewidth=0.6, zorder=5)
    
    # === LABELS: Only 8 well-spaced tickers with large offsets ===
    # Each tuple: (xytext_x, xytext_y) — absolute positions for the label
    # This avoids overlap by placing labels in clear space with leader arrows
    label_positions = {
        # Top-left: deep dampening, low amplified
        "MSFT":  (-1.5, -0.40),    # 2.6% amp, deepest ACF
        "CHWY":  (5,    -0.35),    # 1.4% amp, strong dampening
        "ARM":   (6,    -0.32),    # 1.9% amp, strong dampening
        # Mid cluster
        "AAPL":  (14,   -0.275),   # 8.4% amp, representative mega-cap
        "SPY":   (20,   -0.25),    # 14.8% amp, market benchmark
        "NVDA":  (26,   -0.14),    # 21.5% amp, mega-cap spec
        "GME":   (12,   -0.115),   # 7.2% amp, notable meme ticker
        # Right side: high amplified
        "TSLA":  (35,   -0.175),   # 28.2% amp, mega-cap meme
        "AMC":   (42,   -0.045),   # 30.9% amp, rightmost
        "PLTR":  (25,   -0.025),   # 18.0% amp, high spec
    }
    
    for i, sym in enumerate(symbols):
        if sym in label_positions:
            tx, ty = label_positions[sym]
            ax.annotate(
                sym, xy=(pct_amp[i], mean_acf[i]),
                xytext=(tx, ty),
                fontsize=8.5, color="white", alpha=0.9, fontweight="bold",
                arrowprops=dict(
                    arrowstyle="->", color="white", alpha=0.4, lw=0.8,
                    connectionstyle="arc3,rad=0.15",
                ),
                bbox=dict(boxstyle="round,pad=0.2", facecolor="#21262D",
                          edgecolor="white", alpha=0.3),
            )
    
    # === SQUEEZE-ERA ANCHORS ===
    for label, pt in squeeze_points.items():
        ax.scatter(pt["pct_amp"], pt["mean_acf"], s=250, c="#FF4444",
                   marker="*", edgecolors="white", linewidth=0.8, zorder=6)
    # Label squeeze points with good spacing — stagger vertically
    ax.annotate(
        "GME (Jan 2021)", xy=(85, 0.107),
        xytext=(72, 0.145),
        fontsize=9, color="#FF4444", fontweight="bold",
        ha="center", va="bottom",
        arrowprops=dict(arrowstyle="->", color="#FF4444", lw=1.2),
    )
    ax.annotate(
        "AMC (Jun 2021)", xy=(80, 0.111),
        xytext=(63, 0.128),
        fontsize=9, color="#FF4444", fontweight="bold",
        ha="center", va="bottom",
        arrowprops=dict(arrowstyle="->", color="#FF4444", lw=1.2),
    )
    
    # === AXES ===
    ax.set_xlabel("Percentage of Days in Amplified State  →  (Proxy for Re_Γ)",
                  fontsize=13, color="white", fontweight="bold", labelpad=12)
    ax.set_ylabel("← Dampened (Long Gamma)     Mean ACF     Amplified (Short Gamma) →",
                  fontsize=12, color="white", fontweight="bold", labelpad=12)
    n_shown = len(symbols)
    ax.set_title(f"Gamma Reynolds Phase Transition\n"
                 f"{n_shown}-Ticker Panel (≥{MIN_DAYS} days) + Squeeze-Era Anchors",
                 fontsize=16, color="white", fontweight="bold", pad=18)
    
    # Axis formatting
    ax.tick_params(colors="white", labelsize=11)
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
    ax.set_xlim(-3, 95)
    ax.set_ylim(-0.43, 0.17)
    
    # === LEGEND ===
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#FF6B6B",
               markersize=10, label="Meme / High-Spec", linestyle="None"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#58A6FF",
               markersize=10, label="Mega-Cap / ETF", linestyle="None"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#8B949E",
               markersize=10, label="Mid-Cap / Standard", linestyle="None"),
        Line2D([0], [0], marker="*", color="w", markerfacecolor="#FF4444",
               markersize=14, label="Squeeze-Era Anchor", linestyle="None"),
        Line2D([0], [0], color="#58A6FF", linestyle="--", linewidth=1.2,
               label="ACF = 0 (Criticality)"),
    ]
    if sigmoid_fitted:
        legend_elements.append(
            Line2D([0], [0], color="#F0883E", linewidth=2.5,
                   label=f"Phase transition (R² = {r_squared:.3f})")
        )
    
    legend = ax.legend(handles=legend_elements, loc="lower right", fontsize=10,
                       facecolor="#21262D", edgecolor="#30363D", labelcolor="white",
                       framealpha=0.9)
    
    # Spines
    for spine in ax.spines.values():
        spine.set_color("#30363D")
    
    plt.tight_layout()
    
    # Save
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200, facecolor=fig.get_facecolor(),
                edgecolor="none", bbox_inches="tight")
    print(f"Saved: {output_path}")
    
    # Print statistics
    print(f"\n=== GAMMA REYNOLDS STATISTICS ===")
    print(f"Panel size: {len(symbols)} tickers (current regime)")
    print(f"+ 2 squeeze-era anchors (GME Jan 2021, AMC Jun 2021)")
    print(f"ACF range (current): [{mean_acf.min():.4f}, {mean_acf.max():.4f}]")
    print(f"% Amplified range: [{pct_amp.min():.1f}%, {pct_amp.max():.1f}%]")
    if sigmoid_fitted:
        print(f"Sigmoid R²: {r_squared:.4f}")
        print(f"Inflection point: {x0:.1f}% amplified days (Re_Γ ≈ 1)")
        print(f"Sigmoid params: L={popt[0]:.4f}, k={popt[1]:.4f}, x0={popt[2]:.1f}, b={popt[3]:.4f}")
        # Value at 0% amplified
        y_0 = sigmoid(0, *popt)
        y_50 = sigmoid(50, *popt)
        y_100 = sigmoid(100, *popt)
        print(f"Predicted ACF at 0% amp: {y_0:.4f}")
        print(f"Predicted ACF at 50% amp: {y_50:.4f}")
        print(f"Predicted ACF at 100% amp: {y_100:.4f}")
    
    plt.close(fig)
    return {
        "n_tickers": len(symbols),
        "r_squared": round(r_squared, 4) if r_squared else None,
        "inflection_pct": round(x0, 1) if sigmoid_fitted else None,
    }


def main():
    data = load_panel_data()
    output = OUTPUT_DIR / "gamma_reynolds_sigmoid.png"
    result = build_chart(data, output)
    print(f"\nResult: {json.dumps(result, indent=2)}")


if __name__ == "__main__":
    main()
