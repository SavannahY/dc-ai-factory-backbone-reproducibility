#!/usr/bin/env python3
"""Build two candidate Fig. 1 architecture diagrams.

The outputs are exploratory figure options:

- fig1_integrated_grid_context_v1: one shared grid context with the three
  architecture choices drawn as alternative branches.
- fig1_separate_oneline_v1: three separated one-line-style panels.
"""
import os
import tempfile
from pathlib import Path

cache_root = Path(tempfile.gettempdir()) / "dc_backbone_ai_factory_cache"
os.environ.setdefault("MPLCONFIGDIR", str(cache_root / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(cache_root / "xdg"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "figures" / "fig1_options"
OUT.mkdir(parents=True, exist_ok=True)

AC = "#c44e00"
DC = "#1f78b4"
GRID = "#5f7f50"
GREY = "0.34"
LIGHT = "#f7f7f7"


def savefig(fig, name):
    for ext in ("png", "svg"):
        path = OUT / f"{name}.{ext}"
        fig.savefig(path, dpi=300, bbox_inches="tight")
        if ext == "svg":
            path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n")
    plt.close(fig)


def line(ax, x0, y0, x1, y1, color, lw=2.2, z=2):
    ax.plot([x0, x1], [y0, y1], color=color, lw=lw, solid_capstyle="round", zorder=z)


def node(ax, x, y, color, r=0.045):
    ax.add_patch(Circle((x, y), r, facecolor=color, edgecolor=color, lw=0.8, zorder=6))


def breaker(ax, x, y, color, orient="h", size=0.12):
    ax.add_patch(Rectangle((x - size / 2, y - size / 2), size, size, facecolor="white", edgecolor=GREY, lw=0.9, zorder=5))
    if orient == "h":
        line(ax, x - size * 1.35, y, x - size / 2, y, color, lw=1.4, z=4)
        line(ax, x + size / 2, y, x + size * 1.35, y, color, lw=1.4, z=4)
    else:
        line(ax, x, y - size * 1.35, x, y - size / 2, color, lw=1.4, z=4)
        line(ax, x, y + size / 2, x, y + size * 1.35, color, lw=1.4, z=4)


def transformer(ax, x, y, r=0.13):
    ax.add_patch(Circle((x - r * 0.45, y), r, facecolor="white", edgecolor=GREY, lw=0.9, zorder=4))
    ax.add_patch(Circle((x + r * 0.45, y), r, facecolor="white", edgecolor=GREY, lw=0.9, zorder=4))


def substation(ax, x, y, label=None, w=1.18, h=0.58):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.03,rounding_size=0.04",
                                facecolor=LIGHT, edgecolor="0.46", lw=1.0, zorder=0))
    line(ax, x - 0.38, y + 0.14, x + 0.38, y + 0.14, GREY, lw=1.0, z=2)
    line(ax, x - 0.38, y - 0.13, x + 0.38, y - 0.13, GREY, lw=1.0, z=2)
    transformer(ax, x - 0.45, y - 0.01, 0.12)
    for bx in (x - 0.18, x + 0.12, x + 0.38):
        breaker(ax, bx, y + 0.01, GREY, orient="v", size=0.08)
    if label:
        ax.text(x, y + h / 2 + 0.09, label, ha="center", va="bottom", fontsize=6.8, color="0.25")


def split_box(ax, x, y, label="AC/DC", w=0.68, h=0.38, fs=7.0):
    ax.add_patch(Rectangle((x - w / 2, y - h / 2), w / 2, h, facecolor=AC, edgecolor="none", alpha=0.16, zorder=3))
    ax.add_patch(Rectangle((x, y - h / 2), w / 2, h, facecolor=DC, edgecolor="none", alpha=0.16, zorder=3))
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.02,rounding_size=0.04",
                                facecolor="none", edgecolor=GREY, lw=1.1, zorder=4))
    ax.plot([x, x], [y - h / 2, y + h / 2], color="0.60", lw=0.8, ls="--", zorder=4)
    ax.text(x, y, label, ha="center", va="center", fontsize=fs, weight="bold", zorder=5)


def box(ax, x, y, label, w=0.64, h=0.34, fs=6.8):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.02,rounding_size=0.04",
                                facecolor="white", edgecolor=GREY, lw=1.1, zorder=4))
    ax.text(x, y, label, ha="center", va="center", fontsize=fs, weight="bold", zorder=5)


def data_hall(ax, x, y, scale=1.0):
    w = 0.52 * scale
    h = 0.28 * scale
    ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h, facecolor="#e9eef2", edgecolor="0.25", lw=1.0, zorder=4))
    for dx in (-0.16, 0, 0.16):
        ax.add_patch(Rectangle((x + dx * scale - 0.025 * scale, y - h / 2), 0.05 * scale, h,
                               facecolor="#c1cdd6", edgecolor="none", zorder=5))
    ax.add_patch(Rectangle((x - 0.20 * scale, y + h / 2), 0.12 * scale, 0.05 * scale,
                           facecolor="#d4d4d4", edgecolor="0.5", lw=0.4, zorder=5))
    ax.add_patch(Rectangle((x + 0.08 * scale, y + h / 2), 0.12 * scale, 0.05 * scale,
                           facecolor="#d4d4d4", edgecolor="0.5", lw=0.4, zorder=5))


def tower(ax, x, y, scale=0.62, color="0.45"):
    ax.plot([x - 0.12 * scale, x, x + 0.12 * scale], [y - 0.18 * scale, y + 0.18 * scale, y - 0.18 * scale],
            color=color, lw=0.8, zorder=3)
    ax.plot([x - 0.18 * scale, x + 0.18 * scale], [y + 0.07 * scale, y + 0.07 * scale], color=color, lw=0.8, zorder=3)
    ax.plot([x - 0.13 * scale, x + 0.13 * scale], [y - 0.03 * scale, y - 0.03 * scale], color=color, lw=0.8, zorder=3)


def grid_icon(ax, x, y, scale=1.0):
    ax.add_patch(Rectangle((x - 0.22 * scale, y - 0.07 * scale), 0.44 * scale, 0.14 * scale,
                           facecolor="#eeeeee", edgecolor=GREY, lw=0.9, zorder=3))
    for dx in (-0.14, 0, 0.14):
        ax.add_patch(Rectangle((x + dx * scale - 0.025 * scale, y - 0.07 * scale), 0.05 * scale, 0.28 * scale,
                               facecolor="#d8d8d8", edgecolor=GREY, lw=0.7, zorder=4))


def plant_icon(ax, x, y, label):
    ax.add_patch(Rectangle((x - 0.18, y - 0.11), 0.36, 0.22, facecolor="#8d6e4f", edgecolor="0.35", lw=0.8))
    ax.add_patch(Rectangle((x - 0.12, y + 0.11), 0.055, 0.26, facecolor="#b56a39", edgecolor="0.35", lw=0.6))
    ax.add_patch(Rectangle((x + 0.02, y + 0.11), 0.055, 0.20, facecolor="#b56a39", edgecolor="0.35", lw=0.6))
    ax.text(x, y - 0.24, label, ha="center", va="top", fontsize=6.3, color="0.25")


def solar_icon(ax, x, y):
    for i in range(3):
        ax.add_patch(Rectangle((x - 0.30 + i * 0.22, y - 0.12), 0.18, 0.24, angle=-8,
                               facecolor="#2e65b8", edgecolor="0.35", lw=0.6))
    ax.text(x, y - 0.27, "solar", ha="center", va="top", fontsize=6.3, color="0.25")


def wind_icon(ax, x, y):
    line(ax, x, y - 0.18, x, y + 0.15, "0.45", lw=0.8)
    for ang in (90, 210, 330):
        import math

        rad = math.radians(ang)
        line(ax, x, y + 0.15, x + 0.20 * math.cos(rad), y + 0.15 + 0.20 * math.sin(rad), "0.45", lw=0.8)
    ax.text(x, y - 0.27, "wind", ha="center", va="top", fontsize=6.3, color="0.25")


def branch_bus(ax, x, y, color, span=0.68):
    line(ax, x, y - span / 2, x, y + span / 2, color, lw=2.8)


def draw_common_grid_context(ax):
    ax.add_patch(FancyBboxPatch((0.35, 5.10), 3.05, 1.25, boxstyle="round,pad=0.05,rounding_size=0.08",
                                facecolor="#f7f8f6", edgecolor="0.72", lw=0.9, zorder=0))
    ax.text(1.88, 6.18, "Bulk transmission grid", ha="center", va="center", fontsize=9.5, weight="bold", color="0.25")
    ax.text(1.88, 5.92, "230-500 kV AC network", ha="center", va="center", fontsize=7.2, color="0.35")
    plant_icon(ax, 0.85, 5.55, "thermal")
    solar_icon(ax, 1.80, 5.55)
    wind_icon(ax, 2.70, 5.55)
    line(ax, 3.40, 5.72, 4.05, 5.72, GRID, lw=1.8)
    breaker(ax, 3.72, 5.72, GRID)
    substation(ax, 4.55, 5.72, "230/138 kV utility substation", w=1.28, h=0.58)
    line(ax, 5.19, 5.72, 5.65, 5.72, AC, lw=2.1)
    tower(ax, 5.92, 5.72, 0.66)
    tower(ax, 6.36, 5.72, 0.66)
    line(ax, 5.65, 5.72, 6.65, 5.72, AC, lw=2.1)
    ax.text(6.05, 5.30, "138 kV subtransmission source", ha="center", fontsize=7.1, color=AC)


def fig_integrated():
    fig, ax = plt.subplots(figsize=(12.8, 7.15))
    ax.set_xlim(0, 12.0)
    ax.set_ylim(0, 7.0)
    ax.axis("off")

    draw_common_grid_context(ax)
    ax.add_patch(FancyBboxPatch((0.35, 0.55), 11.15, 4.15, boxstyle="round,pad=0.05,rounding_size=0.08",
                                facecolor="#fbfbfb", edgecolor="0.80", lw=0.9, zorder=0))
    ax.text(1.35, 4.48, "AI factory load pocket alternatives", ha="left", va="center", fontsize=10.0, weight="bold", color="0.22")

    source_x = 0.55
    branch_bus(ax, source_x, 3.05, AC, span=2.9)
    line(ax, 6.65, 5.72, 6.65, 4.86, AC, lw=1.45)
    line(ax, 6.65, 4.86, source_x, 4.86, AC, lw=1.45)
    line(ax, source_x, 4.86, source_x, 4.38, AC, lw=1.45)
    node(ax, source_x, 4.38, AC)

    rows = [(3.72, "Traditional AC", "campus AC/DC boundary"),
            (2.48, "Local SST", "boundary inside SST"),
            (1.24, "Utility DC backbone", "utility AC/DC boundary")]
    for y, title, note in rows:
        ax.text(0.85, y + 0.34, title, ha="left", va="center", fontsize=9.0, weight="bold", color="0.12")
        ax.text(0.85, y + 0.08, note, ha="left", va="center", fontsize=6.8, color="0.35")
        line(ax, source_x, y, 1.28, y, AC, lw=1.7)

    # Traditional AC branch.
    y = rows[0][0]
    breaker(ax, 1.40, y, AC)
    line(ax, 1.50, y, 3.40, y, AC, lw=2.0)
    ax.text(2.42, y - 0.28, "138 kV AC corridor", ha="center", fontsize=6.8, color=AC)
    branch_bus(ax, 3.55, y, AC, span=0.62)
    for dy in (0.26, 0, -0.26):
        cy = y + dy
        line(ax, 3.55, cy, 4.20, cy, AC, lw=1.7)
        breaker(ax, 3.78, cy, AC, size=0.09)
        substation(ax, 4.68, cy, None, w=0.66, h=0.26)
        line(ax, 5.02, cy, 5.56, cy, AC, lw=1.6)
        split_box(ax, 5.82, cy, "AC/DC", w=0.50, h=0.26, fs=5.7)
        line(ax, 6.08, cy, 6.75, cy, DC, lw=1.6)
        data_hall(ax, 6.96, cy, 0.68)
    ax.text(4.68, y + 0.54, "campus AC switchyards", ha="center", fontsize=6.7, color="0.25")
    ax.text(5.82, y - 0.54, "3 AC-facing interfaces", ha="center", fontsize=6.6, color="0.25")

    # Local SST branch.
    y = rows[1][0]
    breaker(ax, 1.40, y, AC)
    line(ax, 1.50, y, 4.64, y, AC, lw=2.0)
    ax.text(2.72, y - 0.28, "138 kV AC corridor", ha="center", fontsize=6.8, color=AC)
    branch_bus(ax, 4.78, y, AC, span=0.62)
    for dy in (0.26, 0, -0.26):
        cy = y + dy
        line(ax, 4.78, cy, 5.45, cy, AC, lw=1.7)
        breaker(ax, 5.02, cy, AC, size=0.09)
        split_box(ax, 5.82, cy, "SST", w=0.52, h=0.28, fs=5.9)
        line(ax, 6.08, cy, 6.75, cy, DC, lw=1.6)
        data_hall(ax, 6.96, cy, 0.68)
    ax.text(5.82, y - 0.54, "3 local AC-facing SSTs", ha="center", fontsize=6.6, color="0.25")

    # DC-backbone branch.
    y = rows[2][0]
    breaker(ax, 1.40, y, AC)
    line(ax, 1.50, y, 2.20, y, AC, lw=1.9)
    split_box(ax, 2.55, y, "AC/DC", w=0.62, h=0.34, fs=6.1)
    node(ax, 2.24, y, AC)
    node(ax, 2.87, y, DC)
    line(ax, 2.87, y + 0.055, 4.70, y + 0.055, DC, lw=1.6)
    line(ax, 2.87, y - 0.055, 4.70, y - 0.055, DC, lw=1.6)
    tower(ax, 3.30, y, 0.56)
    tower(ax, 3.76, y, 0.56)
    tower(ax, 4.22, y, 0.56)
    ax.text(3.72, y - 0.34, "+/-138 kV DC backbone", ha="center", fontsize=6.8, color=DC)
    branch_bus(ax, 4.82, y, DC, span=0.62)
    for dy in (0.26, 0, -0.26):
        cy = y + dy
        line(ax, 4.82, cy, 5.30, cy, DC, lw=1.6)
        breaker(ax, 5.02, cy, DC, size=0.09)
        box(ax, 5.66, cy, "DC/DC", w=0.50, h=0.26, fs=5.6)
        line(ax, 5.92, cy, 6.45, cy, DC, lw=1.5)
        box(ax, 6.70, cy, "DC/DC", w=0.48, h=0.26, fs=5.6)
        line(ax, 6.94, cy, 7.42, cy, DC, lw=1.5)
        data_hall(ax, 7.64, cy, 0.68)
    ax.text(2.55, y - 0.54, "single utility terminal", ha="center", fontsize=6.6, color="0.25")
    ax.text(6.15, y + 0.54, "campus DC stations", ha="center", fontsize=6.7, color="0.25")

    # Boundary movement.
    ax.text(8.35, 4.34, "800 VDC AI data halls", ha="left", va="center", fontsize=7.0, color=DC)
    ax.add_patch(FancyArrowPatch((5.85, 0.78), (2.55, 0.78), arrowstyle="-|>", mutation_scale=12, lw=1.1, color="0.30"))
    ax.text(4.20, 0.55, "AC/DC boundary moves upstream", ha="center", va="top", fontsize=7.0, color="0.25")

    ax.plot([10.15, 10.55], [0.86, 0.86], color=AC, lw=3.0)
    ax.text(10.63, 0.86, "AC", va="center", fontsize=7.8, color=AC)
    ax.plot([10.95, 11.35], [0.86, 0.86], color=DC, lw=3.0)
    ax.text(11.43, 0.86, "DC", va="center", fontsize=7.8, color=DC)
    savefig(fig, "fig1_integrated_grid_context_v1")


def draw_row_front(ax, y):
    grid_icon(ax, 0.75, y, 0.95)
    ax.text(0.75, y - 0.28, "AC grid", ha="center", fontsize=6.8)
    line(ax, 0.96, y, 1.45, y, AC, lw=2.0)
    substation(ax, 2.10, y, "230/138 kV utility substation", w=1.20, h=0.55)
    line(ax, 2.70, y, 3.25, y, AC, lw=2.0)


def draw_ac_corridor(ax, y, x0=3.25, x1=4.95):
    line(ax, x0, y, x1, y, AC, lw=2.0)
    for tx in (3.72, 4.18, 4.64):
        tower(ax, tx, y, 0.58)
    ax.text((x0 + x1) / 2, y - 0.34, "138 kV AC corridor", ha="center", fontsize=6.8, color=AC)


def fig_separate():
    fig, ax = plt.subplots(figsize=(12.8, 7.2))
    ax.set_xlim(0, 12.0)
    ax.set_ylim(0, 7.05)
    ax.axis("off")
    rows = [(5.85, "a", "Traditional AC delivery"),
            (3.70, "b", "Local SST delivery"),
            (1.50, "c", "Utility DC backbone")]

    for y, letter, title in rows:
        ax.text(0.15, y + 0.56, letter, fontsize=13.5, weight="bold", ha="left", va="center")
        ax.text(0.48, y + 0.56, title, fontsize=12.5, weight="bold", ha="left", va="center")

    # Traditional AC.
    y = rows[0][0]
    draw_row_front(ax, y)
    draw_ac_corridor(ax, y)
    branch_bus(ax, 5.10, y, AC, span=0.82)
    for dy in (0.34, 0, -0.34):
        cy = y + dy
        breaker(ax, 5.28, cy, AC, size=0.10)
        line(ax, 5.38, cy, 6.05, cy, AC, lw=1.8)
        substation(ax, 6.55, cy, None, w=0.82, h=0.30)
        line(ax, 6.96, cy, 7.45, cy, AC, lw=1.7)
        split_box(ax, 7.78, cy, "AC/DC", w=0.58, h=0.30, fs=6.1)
        line(ax, 8.07, cy, 9.18, cy, DC, lw=1.8)
        data_hall(ax, 9.44, cy, 0.78)
        ax.text(9.95, cy, "800 VDC", va="center", fontsize=6.8, color=DC)
    ax.text(6.44, y + 0.70, "campus AC switchyards", ha="center", fontsize=6.7, color="0.25")
    ax.text(8.10, y + 0.70, "AC/DC boundary\nat campuses", ha="center", va="bottom", fontsize=6.7, color="0.25")
    ax.text(7.78, y - 0.72, "3 campus AC/DC interfaces", ha="center", fontsize=6.8, color="0.25")

    # Local SST.
    y = rows[1][0]
    draw_row_front(ax, y)
    draw_ac_corridor(ax, y)
    branch_bus(ax, 5.10, y, AC, span=0.82)
    for dy in (0.34, 0, -0.34):
        cy = y + dy
        breaker(ax, 5.28, cy, AC, size=0.10)
        line(ax, 5.38, cy, 6.65, cy, AC, lw=1.8)
        split_box(ax, 7.02, cy, "SST", w=0.62, h=0.32, fs=6.3)
        line(ax, 7.33, cy, 9.18, cy, DC, lw=1.8)
        data_hall(ax, 9.44, cy, 0.78)
        ax.text(9.95, cy, "800 VDC", va="center", fontsize=6.8, color=DC)
    ax.text(6.15, y + 0.66, "AC input", ha="center", fontsize=6.8, color=AC)
    ax.text(7.98, y + 0.66, "DC output", ha="center", fontsize=6.8, color=DC)
    ax.text(7.02, y + 0.86, "AC/DC boundary inside local SSTs", ha="center", fontsize=6.8, color="0.25")
    ax.text(7.02, y - 0.72, "3 SST AC-facing interfaces", ha="center", fontsize=6.8, color="0.25")

    # Utility DC backbone.
    y = rows[2][0]
    draw_row_front(ax, y)
    split_box(ax, 3.45, y, "AC/DC", w=0.70, h=0.40, fs=6.5)
    ax.plot([3.45, 3.45], [y - 0.62, y + 0.62], color="0.25", lw=0.9, ls="--", zorder=0)
    ax.text(3.45, y + 0.76, "AC/DC boundary\nat utility terminal", ha="center", va="bottom", fontsize=6.8, color="0.25")
    node(ax, 3.10, y, AC)
    node(ax, 3.80, y, DC)
    line(ax, 3.80, y + 0.06, 5.00, y + 0.06, DC, lw=1.7)
    line(ax, 3.80, y - 0.06, 5.00, y - 0.06, DC, lw=1.7)
    for tx in (4.12, 4.50, 4.86):
        tower(ax, tx, y, 0.54)
    ax.text(4.45, y - 0.36, "+/-138 kV DC corridor", ha="center", fontsize=6.8, color=DC)
    branch_bus(ax, 5.12, y, DC, span=0.82)
    for dy in (0.34, 0, -0.34):
        cy = y + dy
        breaker(ax, 5.30, cy, DC, size=0.10)
        line(ax, 5.40, cy, 6.05, cy, DC, lw=1.8)
        box(ax, 6.42, cy, "DC/DC", w=0.58, h=0.30, fs=6.0)
        line(ax, 6.71, cy, 7.52, cy, DC, lw=1.7)
        ax.text(7.10, cy + 0.15, "34.5 kV DC", ha="center", fontsize=6.2, color=DC)
        box(ax, 7.88, cy, "DC/DC", w=0.58, h=0.30, fs=6.0)
        line(ax, 8.17, cy, 9.18, cy, DC, lw=1.7)
        data_hall(ax, 9.44, cy, 0.78)
        ax.text(9.95, cy, "800 VDC", va="center", fontsize=6.8, color=DC)
    ax.text(3.45, y - 0.73, "single utility AC/DC terminal", ha="center", fontsize=6.8, color="0.25")
    ax.text(6.42, y - 0.73, "campus DC stations", ha="center", fontsize=6.8, color="0.25")
    ax.text(9.44, y - 0.73, "AI data halls", ha="center", fontsize=6.8, color="0.25")

    ax.plot([0.20, 0.55], [0.25, 0.25], color=AC, lw=3.0)
    ax.text(0.62, 0.25, "AC", va="center", fontsize=8, color=AC)
    ax.plot([0.92, 1.27], [0.25, 0.25], color=DC, lw=3.0)
    ax.text(1.34, 0.25, "DC", va="center", fontsize=8, color=DC)
    savefig(fig, "fig1_separate_oneline_v1")


def main():
    fig_integrated()
    fig_separate()


if __name__ == "__main__":
    main()
