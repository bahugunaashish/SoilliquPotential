"""MSF methods and approximate curve digitization from the supplied figure."""

from __future__ import annotations

import math
from typing import Iterable

import pandas as pd

IDRISS_1999 = "Idriss (1999)"

# Anchor points visually read from the user-supplied chart. For these five
# methods, intermediate magnitudes use straight-line interpolation. These are
# approximate chart readings, not transcriptions of the original source tables.
DIGITIZED_CURVES: dict[str, list[tuple[float, float]]] = {
    "Seed & Idriss (1982)": [
        (5.25, 1.52), (6.00, 1.32), (6.75, 1.12), (8.50, 0.89),
    ],
    "Tokimatsu & Yoshimi (1983)": [
        (5.00, 1.58), (5.25, 1.49), (5.50, 1.40), (5.75, 1.33),
        (6.00, 1.27), (6.50, 1.16), (7.00, 1.07), (7.50, 0.99),
        (8.00, 0.91), (8.50, 0.83),
    ],
    "Ambraseys (1985)": [
        (5.50, 2.86), (6.00, 2.20), (6.50, 1.68), (6.75, 1.45),
        (7.00, 1.26), (7.25, 1.06), (7.50, 0.98), (8.00, 0.65),
        (8.50, 0.44),
    ],
    "Arango (1996)": [
        (5.50, 2.25), (6.00, 1.72), (6.50, 1.45), (7.00, 1.25),
        (7.50, 1.00), (8.00, 0.74), (8.25, 0.62),
    ],
    "Cetin et al. (2004)": [
        (5.00, 2.45), (5.25, 2.23), (5.50, 2.00), (5.75, 1.78),
        (6.00, 1.60), (6.25, 1.43), (6.50, 1.30), (6.75, 1.20),
        (7.00, 1.13), (7.25, 1.06), (7.50, 1.00), (7.75, 0.95),
        (8.00, 0.90), (8.25, 0.85), (8.50, 0.81),
    ],
}

MSF_METHODS = [IDRISS_1999, *DIGITIZED_CURVES.keys()]
METHOD_NOTES = {
    IDRISS_1999: "Equation shown in the reference figure; calculated directly and capped at 1.8.",
    **{
        method: "Approximate visual digitization; linear interpolation between chart-read points."
        for method in DIGITIZED_CURVES
    },
}


def msf_for_method(method: str, magnitude: float) -> float:
    """Return an MSF value; chart-digitized methods are limited to their plotted range."""
    if not math.isfinite(magnitude):
        raise ValueError("Earthquake magnitude must be finite.")
    if method == IDRISS_1999:
        value = 6.9 * math.exp(-magnitude / 4.0) - 0.058
        return min(value, 1.8)
    if method not in DIGITIZED_CURVES:
        raise ValueError(f"Unknown MSF method: {method}")
    points = DIGITIZED_CURVES[method]
    low, high = points[0][0], points[-1][0]
    if magnitude < low or magnitude > high:
        raise ValueError(
            f"{method} is digitized only from Mw {low:g} to {high:g}; "
            "choose a magnitude within that range or use Idriss (1999)."
        )
    for (m0, v0), (m1, v1) in zip(points, points[1:]):
        if m0 <= magnitude <= m1:
            if magnitude == m0:
                return v0
            if magnitude == m1:
                return v1
            ratio = (magnitude - m0) / (m1 - m0)
            return v0 + ratio * (v1 - v0)
    return points[-1][1]


def curve_frame(methods: Iterable[str], step: float = 0.05) -> pd.DataFrame:
    """Make a plot-ready dataframe over the reference figure's Mw range."""
    if step <= 0:
        raise ValueError("Step must be positive.")
    magnitudes = [round(4.5 + i * step, 4) for i in range(round(4.0 / step) + 1)]
    rows: list[dict[str, float]] = []
    for magnitude in magnitudes:
        row: dict[str, float] = {"Mw": magnitude}
        for method in methods:
            try:
                row[method] = msf_for_method(method, magnitude)
            except ValueError:
                row[method] = math.nan
        rows.append(row)
    return pd.DataFrame(rows)


def comparison_frame(methods: Iterable[str], magnitude: float) -> pd.DataFrame:
    """List MSF and provenance for the selected methods at the entered Mw."""
    return pd.DataFrame(
        [
            {
                "MSF method": method,
                "Mw": magnitude,
                "MSF": msf_for_method(method, magnitude),
                "Method detail": METHOD_NOTES[method],
            }
            for method in methods
        ]
    )
