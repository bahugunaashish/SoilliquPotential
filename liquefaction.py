"""Calculation engine for the SoilliquPotential Streamlit app."""

from __future__ import annotations

import math
import re
from typing import Any

import pandas as pd
from msf_methods import IDRISS_1999, msf_for_method

GAMMA_W = 9.80665
PA_KPA = 101.3
FT_TO_M = 0.3048
PCF_TO_KN_M3 = 0.157087463
KPA_TO_PSF = 20.885434273

REQUIRED_COLUMNS = [
    "soil_code",
    "top_depth",
    "bottom_depth",
    "unit_weight",
    "spt_n",
    "fines_percent",
]

IMPORT_ALIASES = {
    "soil_code": {"soil_code", "soil_type", "soil"},
    "top_depth": {"top_depth", "top"},
    "bottom_depth": {"bottom_depth", "bottom"},
    "unit_weight": {"unit_weight", "bulk_unit_weight", "gamma"},
    "spt_n": {"spt_n", "measured_spt_n", "n_value"},
    "fines_percent": {"fines_percent", "fines_content", "fines"},
    "analyze": {"analyze", "include"},
}


def water_table_depth_from_inputs(
    input_mode: str,
    *,
    depth_below_surface: float | None = None,
    ground_surface_elevation: float | None = None,
    water_table_elevation: float | None = None,
) -> float:
    """Return water-table depth relative to grade; positive is below grade.

    Elevation inputs must use the same vertical datum (the app labels them MSL).
    A negative result represents groundwater above the ground surface.
    """
    if input_mode == "Elevation above MSL":
        if ground_surface_elevation is None or water_table_elevation is None:
            raise ValueError("Enter both ground-surface and water-table elevations.")
        return float(ground_surface_elevation) - float(water_table_elevation)
    if input_mode == "Depth below ground surface":
        if depth_below_surface is None:
            raise ValueError("Enter the water-table depth below ground surface.")
        return float(depth_below_surface)
    raise ValueError("Choose either depth below ground surface or elevation above MSL.")


def is_default_excluded(soil_code: Any) -> bool:
    """Return true for CH/MH USCS codes, including descriptions such as CH/Clay."""
    code = "" if pd.isna(soil_code) else str(soil_code).strip().upper()
    return bool(re.match(r"^(CH|MH)(?:$|[^A-Z0-9])", code))


def _as_bool(value: Any, default: bool = True) -> bool:
    if pd.isna(value):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() not in {"false", "0", "no", "n", ""}


def normalize_import_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize common boring-log header aliases and default CH/MH to excluded."""
    aliases: dict[str, str] = {}
    for original in frame.columns:
        key = re.sub(r"[^a-z0-9]+", "_", str(original).strip().lower()).strip("_")
        for canonical, options in IMPORT_ALIASES.items():
            if key in options:
                aliases[original] = canonical
                break
    result = frame.rename(columns=aliases).copy()
    missing = [column for column in REQUIRED_COLUMNS if column not in result.columns]
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))
    result = result.loc[:, REQUIRED_COLUMNS + (["analyze"] if "analyze" in result.columns else [])]
    result["soil_code"] = result["soil_code"].fillna("").astype(str).str.strip()
    for column in REQUIRED_COLUMNS[1:]:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    if "analyze" not in result.columns:
        result["analyze"] = [not is_default_excluded(code) for code in result["soil_code"]]
    else:
        result["analyze"] = [
            _as_bool(value, default=not is_default_excluded(code))
            for code, value in zip(result["soil_code"], result["analyze"])
        ]
    return result.reset_index(drop=True)


def calculate_profile(
    frame: pd.DataFrame,
    *,
    units: str,
    magnitude: float,
    pga: float,
    water_table: float,
    energy_pct: float,
    borehole_inches: float,
    rod_length: float,
    sampler: str,
    rd_mode: str,
    analysis_mode: str,
    msf_method: str = IDRISS_1999,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Calculate SPT liquefaction screening for each layer in one boring log."""
    if frame.empty:
        raise ValueError("Enter at least one soil layer.")
    if not 3 <= magnitude <= 9.5:
        raise ValueError("Earthquake magnitude must be between 3 and 9.5.")
    triggering_mode = analysis_mode == "triggerPga"
    if not triggering_mode and not 0 < pga <= 2:
        raise ValueError("Design PGA must be greater than 0 and no more than 2 g.")
    if not 0 < energy_pct <= 150:
        raise ValueError("Hammer energy ratio must be between 0 and 150%.")

    english = units == "English"
    depth_scale = FT_TO_M if english else 1.0
    unit_weight_scale = PCF_TO_KN_M3 if english else 1.0
    stress_scale = KPA_TO_PSF if english else 1.0

    ce = energy_pct / 60.0
    borehole_mm = 102.0 if borehole_inches <= 4.5 else 150.0 if borehole_inches <= 7.0 else 200.0
    cb = 1.0 if borehole_mm <= 115 else 1.05 if borehole_mm <= 150 else 1.15
    rod_length_m = rod_length * depth_scale
    cr = 0.75 if rod_length_m < 3 else 0.80 if rod_length_m < 4 else 0.85 if rod_length_m < 6 else 0.95 if rod_length_m < 10 else 1.0
    cs = 1.2 if sampler in {"withoutLiners", "nonStandard"} else 1.0
    msf = msf_for_method(msf_method, magnitude)
    rd_magnitude = magnitude if rd_mode == "event" else 7.5

    results: list[dict[str, Any]] = []
    cumulative_total_stress = 0.0
    previous_bottom = 0.0
    for i, row in frame.reset_index(drop=True).iterrows():
        soil_value = row.get("soil_code", "")
        soil = "" if pd.isna(soil_value) else str(soil_value).strip()
        top_display = float(row["top_depth"])
        bottom_display = float(row["bottom_depth"])
        gamma_display = float(row["unit_weight"])
        spt_n = float(row["spt_n"])
        fines = float(row["fines_percent"])
        if not soil:
            raise ValueError(f"Layer {i + 1} needs a soil code.")
        if not all(math.isfinite(x) for x in [top_display, bottom_display, gamma_display, spt_n, fines]):
            raise ValueError(f"Layer {i + 1} has a missing or invalid numeric value.")
        if bottom_display <= top_display:
            raise ValueError(f"Layer {i + 1} bottom depth must be greater than top depth.")
        if i == 0 and abs(top_display) > 1e-6:
            raise ValueError("The first layer must begin at depth zero.")
        if i > 0 and abs(top_display - previous_bottom) > 1e-5:
            raise ValueError(f"Layers must be contiguous and ordered. Check layer {i + 1} top depth.")
        if gamma_display <= 0 or spt_n < 0 or not 0 <= fines <= 100:
            raise ValueError(f"Layer {i + 1} has an out-of-range unit weight, SPT-N, or fines value.")

        top = top_display * depth_scale
        bottom = bottom_display * depth_scale
        z = (top + bottom) / 2.0
        gamma = gamma_display * unit_weight_scale
        sigma_v = cumulative_total_stress + gamma * (z - top)
        pore_pressure = GAMMA_W * max(z - water_table * depth_scale, 0.0)
        sigma_eff = sigma_v - pore_pressure
        if sigma_eff <= 0:
            raise ValueError(f"Effective stress is zero or negative at the midpoint of layer {i + 1}.")

        n60 = spt_n * ce * cb * cr * cs
        cn = min(math.sqrt(PA_KPA / sigma_eff), 1.7)
        n1_60 = cn * n60
        delta_n = math.exp(1.63 + 9.7 / (fines + 0.1) - (15.7 / (fines + 0.1)) ** 2)
        n1_60cs = n1_60 + delta_n
        excluded_by_soil = is_default_excluded(soil)
        included = _as_bool(row.get("analyze", None), default=not excluded_by_soil)
        inclusion_override = excluded_by_soil and included

        crr75 = c_sigma = k_sigma = crr = alpha = beta = rd = csr = fs = trigger_pga = math.nan
        if included and n1_60cs > 0:
            crr75 = math.exp(
                n1_60cs / 14.1
                + (n1_60cs / 126) ** 2
                - (n1_60cs / 23.6) ** 3
                + (n1_60cs / 25.4) ** 4
                - 2.8
            )
            c_sigma = min(1.0 / (18.9 - 2.55 * math.sqrt(n1_60cs)), 0.3)
            k_sigma = min(1.1, 1.0 - c_sigma * math.log(sigma_eff / PA_KPA))
            crr = crr75 * k_sigma * msf
            alpha = -1.012 - 1.126 * math.sin(z / 11.73 + 5.133)
            beta = 0.106 + 0.118 * math.sin(z / 11.28 + 5.142)
            rd = math.exp(alpha + beta * rd_magnitude)
            trigger_pga = crr / (0.65 * (sigma_v / sigma_eff) * rd)
            demand_pga = trigger_pga if triggering_mode else pga
            csr = 0.65 * (sigma_v / sigma_eff) * demand_pga * rd
            fs = crr / csr

        result = {
            "layer": i + 1,
            "soil": soil,
            "top": top_display,
            "bottom": bottom_display,
            "thickness": bottom_display - top_display,
            "mid_depth": z / depth_scale,
            "unit_weight": gamma_display,
            "sigma_v": sigma_v * stress_scale,
            "pore_pressure": pore_pressure * stress_scale,
            "sigma_eff": sigma_eff * stress_scale,
            "spt_n": spt_n,
            "ce": ce,
            "cb": cb,
            "cr": cr,
            "cs": cs,
            "n60": n60,
            "cn": cn,
            "n1_60": n1_60,
            "fines": fines,
            "delta_n": delta_n,
            "n1_60cs": n1_60cs,
            "crr75": crr75,
            "c_sigma": c_sigma,
            "k_sigma": k_sigma,
            "msf": msf,
            "crr": crr,
            "alpha": alpha,
            "beta": beta,
            "rd": rd,
            "csr": csr,
            "fs": fs,
            "trigger_pga": trigger_pga,
            "included": included,
            "excluded_by_soil": excluded_by_soil and not inclusion_override,
            "inclusion_override": inclusion_override,
        }
        results.append(result)
        cumulative_total_stress += gamma * (bottom - top)
        previous_bottom = bottom_display

    included_results = [row for row in results if row["included"]]
    if included_results:
        minimum_fs = min(row["fs"] for row in included_results)
        minimum_trigger_pga = min(row["trigger_pga"] for row in included_results)
        governor = (
            min(included_results, key=lambda row: row["trigger_pga"])
            if triggering_mode
            else min(included_results, key=lambda row: row["fs"])
        )
        governing_layer = governor["layer"]
    else:
        minimum_fs = minimum_trigger_pga = math.nan
        governing_layer = None

    summary = {
        "minimum_fs": minimum_fs,
        "minimum_trigger_pga": minimum_trigger_pga,
        "governing_layer": governing_layer,
        "analysis_mode": analysis_mode,
        "msf_method": msf_method,
        "msf": msf,
    }
    return pd.DataFrame(results), summary


def template_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["SM", 0.0, 2.0, 18.0, 8, 15, True],
            ["SM", 2.0, 5.0, 19.0, 12, 20, True],
            ["CH", 5.0, 8.0, 20.0, 30, 65, False],
        ],
        columns=REQUIRED_COLUMNS + ["analyze"],
    )
