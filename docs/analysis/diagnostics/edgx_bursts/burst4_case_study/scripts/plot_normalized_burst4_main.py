"""
Normalized scatter for the 2024-05-17 08:03:26 ET burst (C4 block you highlighted).

This uses the normalized point cloud plus metadata so we can see how the
stroke looks in the same compressed [0,1] x [0,1] space as the other face plots.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
import plotly.graph_objects as go

matplotlib.use("Agg")


def main() -> None:
    base = Path("reports/diagnostics/edgx_bursts")
    points = pd.read_parquet(base / "normalized_points.parquet")
    meta = pd.read_csv(base / "burst_future_with_options.csv")

    burst_id = "2024-05-17_2024-05-17 08:03:26-04:00"
    pts = points[points["burst_id"] == burst_id].copy()
    if pts.empty:
        raise SystemExit(f"no normalized points for {burst_id}")

    info = meta[meta["burst_id"] == burst_id]
    if info.empty:
        raise SystemExit(f"no metadata for {burst_id}")
    info = info.iloc[0]

    order = np.linspace(0, 1, len(pts))
    pts = pts.assign(order=order)

    fig, ax = plt.subplots(figsize=(6, 6))
    scatter = ax.scatter(
        pts["norm_x"],
        pts["norm_y"],
        c=pts["order"],
        cmap="viridis",
        s=6,
        alpha=0.75,
    )
    ax.set_title("Normalized view – burst4 main 08:03:26–08:05:05 ET (C4)")
    ax.set_xlabel("normalized time [0,1]")
    ax.set_ylabel("normalized price [0,1]")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    fig.colorbar(scatter, label="relative stroke order")

    start = pd.Timestamp(info["start"]).tz_convert("America/New_York")
    end = pd.Timestamp(info["end"]).tz_convert("America/New_York")
    summary = (
        f"start: {start:%Y-%m-%d %H:%M:%S %Z}\n"
        f"end:   {end:%Y-%m-%d %H:%M:%S %Z}\n"
        f"cluster: C{int(info['cluster']) if not np.isnan(info['cluster']) else 'nan'}\n"
        f"duration: {info['duration_seconds']:.1f}s, trades: {int(info['trade_count'])}\n"
        f"return_120d: {info['return_120d']:.2f}%"
    )
    ax.text(
        0.02,
        0.01,
        summary,
        ha="left",
        va="bottom",
        fontsize=8,
        bbox=dict(facecolor="white", alpha=0.6, edgecolor="none"),
        transform=ax.transAxes,
    )

    fig.tight_layout()
    out = base / "normalized_burst4_main.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    print(f"saved {out}")

    # 3D view: treat normalized time as x, normalized price as y, and stroke order as z
    fig3d = plt.figure(figsize=(10, 4))
    ax_left = fig3d.add_subplot(1, 2, 1, projection="3d")
    ax_right = fig3d.add_subplot(1, 2, 2, projection="3d")

    for ax, (elev, azim) in zip((ax_left, ax_right), ((20, -60), (10, 120))):
        ax.scatter(
            pts["norm_x"],
            pts["norm_y"],
            pts["order"],
            c=pts["order"],
            cmap="viridis",
            s=4,
            alpha=0.75,
        )
        ax.set_xlabel("norm time")
        ax.set_ylabel("norm price")
        ax.set_zlabel("stroke order")
        ax.view_init(elev=elev, azim=azim)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_zlim(0, 1)

    ax_left.set_title("Layered view (azim=-60°)")
    ax_right.set_title("Edge view (azim=120°)")
    fig3d.suptitle("3D normalized burst4 main – stroke order as depth")
    fig3d.tight_layout(rect=[0, 0, 1, 0.94])

    out3d = base / "normalized_burst4_main_3d.png"
    fig3d.savefig(out3d, dpi=200)
    plt.close(fig3d)
    print(f"saved {out3d}")

    # Prepare alternate depth mappings for interactive slider
    order_vals = pts["order"].to_numpy()
    norm_y_vals = pts["norm_y"].to_numpy()

    diff = np.diff(norm_y_vals, prepend=norm_y_vals[0])
    z_delta_raw = np.abs(diff)
    z_delta = z_delta_raw / z_delta_raw.max() if np.any(z_delta_raw) else z_delta_raw

    slice_idx = np.clip((pts["norm_x"] * 10).astype(int), 0, 9)
    slice_base = slice_idx / 9.0
    z_slice = slice_base + (norm_y_vals - 0.5) * 0.25
    z_slice = np.clip(z_slice, 0, 1)

    depth_modes = {
        "stroke order": order_vals,
        "norm price": norm_y_vals,
        "slice+jitter": z_slice,
        "price step delta": z_delta,
    }

    traces = []
    labels = []
    for idx, (label, zvals) in enumerate(depth_modes.items()):
        trace = go.Scatter3d(
            x=pts["norm_x"],
            y=pts["norm_y"],
            z=zvals,
            mode="markers",
            visible=(idx == 0),
            marker=dict(
                size=2.5,
                color=zvals,
                colorscale="Viridis",
                opacity=0.8,
                cmin=0,
                cmax=1,
            ),
            name=label,
        )
        traces.append(trace)
        labels.append(label)

    fig_html = go.Figure(data=traces)
    steps = []
    for idx, label in enumerate(labels):
        visibility = [False] * len(labels)
        visibility[idx] = True
        steps.append(
            {
                "label": label,
                "method": "update",
                "args": [
                    {"visible": visibility},
                    {"scene": {"zaxis": {"title": f"depth ({label})", "range": [0, 1]}}},
                ],
            }
        )

    slider = {
        "active": 0,
        "currentvalue": {"prefix": "Depth mode: "},
        "steps": steps,
        "pad": {"t": 30},
    }

    size_steps = []
    for size in [0.6, 1.0, 1.5, 2.5, 4.0]:
        size_steps.append(
            {
                "label": f"{size:.1f}",
                "method": "update",
                "args": [
                    {"marker": [{"size": size} for _ in labels]},
                    {},
                ],
            }
        )
    size_slider = {
        "active": 1,
        "currentvalue": {"prefix": "Point size: "},
        "steps": size_steps,
        "pad": {"t": 10},
    }

    def camera_button(label: str, eye: tuple[float, float, float], up=(0, 0, 1)):
        return {
            "label": label,
            "method": "relayout",
            "args": [
                {
                    "scene.camera": {
                        "eye": {"x": eye[0], "y": eye[1], "z": eye[2]},
                        "up": {"x": up[0], "y": up[1], "z": up[2]},
                    }
                }
            ],
        }

    fig_html.update_layout(
        sliders=[slider, size_slider],
        updatemenus=[
            {
                "buttons": [
                    {
                        "label": "Perspective",
                        "method": "relayout",
                        "args": [
                            {
                                "scene.camera.projection.type": "perspective",
                            }
                        ],
                    },
                    {
                        "label": "Orthographic",
                        "method": "relayout",
                        "args": [
                            {
                                "scene.camera.projection.type": "orthographic",
                            }
                        ],
                    },
                ],
                "type": "buttons",
                "direction": "left",
                "pad": {"t": 0, "r": 10},
                "x": 0.0,
                "y": 1.1,
            },
        ],
        title="Interactive 3D – burst4 main (try different depth mappings)",
        scene=dict(
            dragmode="orbit",
            xaxis=dict(title="norm time", range=[0, 1]),
            yaxis=dict(title="norm price", range=[0, 1]),
            zaxis=dict(title="depth", range=[0, 1]),
        ),
        margin=dict(l=0, r=0, b=0, t=110),
    )

    html = fig_html.to_html(include_plotlyjs="cdn", full_html=True, div_id="burst4_3d")
    post_script = """
<script>
(function() {
  const gd = document.getElementById('burst4_3d');
  if (!gd || !window.Plotly) return;
  const baseCamera = {
    eye: {x: 1.3, y: 1.3, z: 1.3},
    up: {x: 0, y: 0, z: 1}
  };
  function setAxis(axis) {
    let camera = {};
    if (axis === 'x') {
      camera = {eye: {x: 0.01, y: 1.8, z: 0.01}, up: {x: 1, y: 0, z: 0}};
    } else if (axis === 'y') {
      camera = {eye: {x: -1.8, y: 0.01, z: 0.01}, up: {x: 0, y: 1, z: 0}};
    } else if (axis === 'z') {
      camera = {eye: {x: 0.01, y: 0.01, z: 1.8}, up: {x: 0, y: 0, z: 1}};
    }
    Plotly.relayout(gd, {
      'scene.dragmode': 'turntable',
      'scene.camera': camera
    });
  }
  function resetView() {
    Plotly.relayout(gd, {
      'scene.dragmode': 'orbit',
      'scene.camera': baseCamera
    });
  }
  document.addEventListener('keydown', (event) => {
    if (event.target && (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA' || event.target.isContentEditable)) {
      return;
    }
    const key = event.key.toLowerCase();
    if (key === 'x' || key === 'y' || key === 'z') {
      setAxis(key);
    } else if (key === 'o') {
      resetView();
    }
  });
  const info = document.createElement('div');
  info.style.fontSize = '12px';
  info.style.margin = '4px 0';
  info.textContent = 'Hotkeys: X/Y/Z lock rotation axis (turntable), O resets to orbit.';
  gd.parentNode.insertBefore(info, gd);
})();
</script>
"""
    html = html.replace("</body>", post_script + "</body>")
    out_html = base / "normalized_burst4_main_3d.html"
    out_html.write_text(html, encoding="utf-8")
    print(f"saved {out_html}")


if __name__ == "__main__":
    main()
