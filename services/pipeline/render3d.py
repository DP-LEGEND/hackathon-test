"""Render a rotating 3D skeleton GIF from world landmarks (proof / debugging)."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.animation import FuncAnimation, PillowWriter  # noqa: E402

BONES = [(11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (11, 23), (12, 24), (23, 24),
         (23, 25), (25, 27), (24, 26), (26, 28), (27, 31), (28, 32), (15, 19), (16, 20), (0, 11), (0, 12)]


def render_gif(world: np.ndarray, out_path: str, title: str = "", loops: int = 2, fps: int = 20,
               color: str = "#FF8A3D") -> None:
    """world: (frames, 33, 3) MediaPipe world landmarks (x right, y down, z toward camera)."""
    P = np.stack([world[..., 0], world[..., 2], -world[..., 1]], axis=-1)  # x, depth, up
    n = len(P)
    total = n * loops
    fig = plt.figure(figsize=(5, 5), facecolor="#0b0f14")
    ax = fig.add_subplot(projection="3d", facecolor="#0b0f14")
    lines = [ax.plot([], [], [], color=color, lw=3)[0] for _ in BONES]
    pts = ax.plot([], [], [], "o", color="#5BE7F0", ms=3)[0]
    r = float(np.nanmax(np.abs(P[..., :2]))) * 1.05 or 1.0
    for setlim in (ax.set_xlim, ax.set_ylim):
        setlim(-r, r)
    ax.set_zlim(float(np.nanmin(P[..., 2])) - 0.05, float(np.nanmin(P[..., 2])) + 2 * r)
    ax.set_axis_off()
    txt = fig.text(0.03, 0.95, title, color="white", fontsize=9)

    def draw(k):
        f = P[k % n]
        for ln, (a, b) in zip(lines, BONES):
            ln.set_data_3d([f[a, 0], f[b, 0]], [f[a, 1], f[b, 1]], [f[a, 2], f[b, 2]])
        pts.set_data_3d(f[:, 0], f[:, 1], f[:, 2])
        ax.view_init(elev=12, azim=-90 + 360 * k / total)
        txt.set_text(f"{title}  frame {k % n + 1}/{n}")
        return lines + [pts]

    FuncAnimation(fig, draw, frames=total, blit=False).save(out_path, writer=PillowWriter(fps=fps))
    plt.close(fig)
