from __future__ import annotations

import hashlib
import html
from io import BytesIO

import pandas as pd
import streamlit as st

from liquefaction import (
    REQUIRED_COLUMNS,
    calculate_profile,
    is_default_excluded,
    normalize_import_frame,
    template_frame,
)

st.set_page_config(page_title="SoilliquPotential", page_icon="🪨", layout="wide")

PALETTE = [
    "#3B82F6", "#E98B35", "#27A889", "#A56CC1", "#D65A71",
    "#5D9C76", "#D0A52F", "#64748B", "#D277A8", "#42A7B8",
]


def color_for_soil(code: str) -> str:
    digest = hashlib.sha256(str(code).strip().upper().encode("utf-8")).digest()
    return PALETTE[int.from_bytes(digest[:2], "big") % len(PALETTE)]


def default_frame() -> pd.DataFrame:
    return template_frame()


def init_state() -> None:
    if "layer_frame" not in st.session_state:
        st.session_state.layer_frame = default_frame()
        st.session_state.soil_snapshot = st.session_state.layer_frame["soil_code"].tolist()
    if "layer_count" not in st.session_state:
        st.session_state.layer_count = len(st.session_state.layer_frame)
    if "analysis_result" not in st.session_state:
        st.session_state.analysis_result = None


def clean_code(value) -> str:
    return "" if pd.isna(value) else str(value).strip().upper()


def remove_blank_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    present = frame[REQUIRED_COLUMNS].copy()
    present["soil_code"] = present["soil_code"].fillna("").astype(str).str.strip()
    empty = present.isna() | present.eq("")
    return frame.loc[~empty.all(axis=1)].copy()


def reset_editor(frame: pd.DataFrame) -> None:
    st.session_state.layer_frame = frame[REQUIRED_COLUMNS + ["analyze"]].copy().reset_index(drop=True)
    st.session_state.soil_snapshot = st.session_state.layer_frame["soil_code"].fillna("").astype(str).tolist()
    # Sync the widget on the next rerun, before its number_input is created.
    st.session_state._pending_layer_count = len(st.session_state.layer_frame)
    st.session_state.pop("layer_editor", None)
    st.session_state.analysis_result = None


def resize_layers(count: int, units: str) -> pd.DataFrame:
    frame = st.session_state.layer_frame.copy()
    count = max(1, min(50, int(count)))
    if count < len(frame):
        frame = frame.iloc[:count].copy()
    while len(frame) < count:
        top = 0.0 if frame.empty else float(frame.iloc[-1]["bottom_depth"])
        thickness = 2.0 if units == "Metric" else 5.0
        frame.loc[len(frame)] = {
            "soil_code": "SM",
            "top_depth": top,
            "bottom_depth": top + thickness,
            "unit_weight": 18.0 if units == "Metric" else 115.0,
            "spt_n": 10.0,
            "fines_percent": 10.0,
            "analyze": True,
        }
    return frame.reset_index(drop=True)


def on_layer_count_change(units: str) -> None:
    frame = resize_layers(st.session_state.layer_count, units)
    st.session_state.layer_frame = frame
    st.session_state.soil_snapshot = frame["soil_code"].fillna("").astype(str).tolist()
    st.session_state.pop("layer_editor", None)
    st.session_state.analysis_result = None


def on_table_change() -> None:
    edited = st.session_state.layer_editor.copy().drop(columns=["thickness"], errors="ignore")
    edited = remove_blank_rows(edited)
    previous = st.session_state.get("soil_snapshot", [])
    if "analyze" not in edited.columns:
        edited["analyze"] = True
    for i, code in enumerate(edited.get("soil_code", [])):
        old_code = previous[i] if i < len(previous) else ""
        if clean_code(code) != clean_code(old_code) and is_default_excluded(code):
            edited.at[i, "analyze"] = False
    edited = edited[REQUIRED_COLUMNS + ["analyze"]].reset_index(drop=True)
    st.session_state.layer_frame = edited
    st.session_state.soil_snapshot = edited["soil_code"].fillna("").astype(str).tolist()
    st.session_state.layer_count = len(edited)
    st.session_state.analysis_result = None
    display = edited.copy()
    display["thickness"] = display["bottom_depth"] - display["top_depth"]
    st.session_state.layer_editor = display


def template_for_units(units: str) -> pd.DataFrame:
    frame = template_frame()
    if units == "English":
        frame["top_depth"] /= 0.3048
        frame["bottom_depth"] /= 0.3048
        frame["unit_weight"] /= 0.157087463
    return frame


def excel_template_bytes(units: str) -> bytes:
    frame = template_for_units(units)
    guide = pd.DataFrame(
        {
            "Instructions": [
                "SoilliquPotential boring-log import template",
                "Use one row per layer, ordered from shallow to deep.",
                "The first layer must start at depth zero; adjacent layer boundaries must meet.",
                "Required columns: soil_code, top_depth, bottom_depth, unit_weight, spt_n, fines_percent.",
                "The analyze column is optional. CH/MH layers default to excluded; set analyze to TRUE to override.",
                "Use the same units in the file and app: m and kN/m3, or ft and pcf.",
            ]
        }
    )
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        guide.to_excel(writer, sheet_name="Read me", index=False)
        frame.to_excel(writer, sheet_name="Boring Log", index=False)
    return buffer.getvalue()


def read_uploaded_file(uploaded) -> pd.DataFrame:
    name = uploaded.name.lower()
    if name.endswith(".csv"):
        return normalize_import_frame(pd.read_csv(uploaded))
    if name.endswith(".xlsx"):
        sheets = pd.read_excel(uploaded, sheet_name=None)
        if "Boring Log" in sheets:
            return normalize_import_frame(sheets["Boring Log"])
        for candidate in sheets.values():
            try:
                return normalize_import_frame(candidate)
            except ValueError:
                continue
        raise ValueError("No worksheet has the required boring-log columns.")
    raise ValueError("Choose a .xlsx or .csv file.")


def render_profile(frame: pd.DataFrame, depth_unit: str) -> None:
    valid = frame.dropna(subset=["top_depth", "bottom_depth"]).copy()
    valid["thickness"] = valid["bottom_depth"] - valid["top_depth"]
    valid = valid[valid["thickness"] > 0]
    total_depth = float(valid["bottom_depth"].max()) if not valid.empty else 0.0
    st.markdown(
        """
        <style>
        .soil-profile { display:flex; flex-direction:column; width:100%; max-width:230px;
          height:420px; border:1px solid #cad4d8; border-radius:5px; overflow:hidden;
          background:#fff; margin:.4rem auto; }
        .soil-segment { flex-basis:0; display:flex; align-items:center; justify-content:center;
          color:white; font-weight:700; font-size:.8rem; text-shadow:0 1px 2px #344;
          border-bottom:1px solid rgba(255,255,255,.65); min-height:2px; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    if valid.empty:
        st.info("Enter layer depths to see the scaled soil profile.")
        return
    segments = []
    for _, row in valid.iterrows():
        soil = html.escape(str(row["soil_code"]))
        top = float(row["top_depth"])
        bottom = float(row["bottom_depth"])
        thickness = float(row["thickness"])
        color = color_for_soil(soil)
        label = f"<span>{soil}</span>" if thickness / total_depth >= 0.07 else ""
        title = html.escape(f"{soil}: {top:g} to {bottom:g} {depth_unit}")
        segments.append(
            f'<div class="soil-segment" title="{title}" style="flex-grow:{thickness};background:{color}">{label}</div>'
        )
    st.markdown(f'<div class="soil-profile">{"".join(segments)}</div>', unsafe_allow_html=True)
    st.caption(f"Profile depth: {total_depth:g} {depth_unit} · layer thicknesses drawn to scale")
    codes = list(dict.fromkeys(valid["soil_code"].fillna("").astype(str).tolist()))
    legend = "　".join(
        f'<span style="white-space:nowrap"><i style="display:inline-block;width:10px;height:10px;'
        f'background:{color_for_soil(code)};border-radius:2px;margin-right:4px"></i>{html.escape(code)}</span>'
        for code in codes
    )
    st.markdown(legend, unsafe_allow_html=True)


def display_results(results: pd.DataFrame, summary: dict, units: str) -> None:
    triggering = summary["analysis_mode"] == "triggerPga"
    col1, col2, col3 = st.columns(3)
    if triggering:
        col1.metric("Governing triggering PGA", f'{summary["minimum_trigger_pga"]:.3f} g')
        col2.metric("Factor of safety at trigger", "1.00")
        col3.metric("Governing layer", str(summary["governing_layer"] or "—"))
    else:
        col1.metric("Minimum factor of safety", f'{summary["minimum_fs"]:.2f}')
        col2.metric("Lowest triggering PGA", f'{summary["minimum_trigger_pga"]:.3f} g')
        col3.metric("Governing layer", str(summary["governing_layer"] or "—"))

    labels = {
        "mid_depth": f"Mid-depth ({'m' if units == 'Metric' else 'ft'})",
        "unit_weight": f"Unit weight ({'kN/m³' if units == 'Metric' else 'pcf'})",
        "sigma_v": f"Total stress ({'kPa' if units == 'Metric' else 'psf'})",
        "pore_pressure": f"Pore pressure ({'kPa' if units == 'Metric' else 'psf'})",
        "sigma_eff": f"Effective stress ({'kPa' if units == 'Metric' else 'psf'})",
        "n1_60": "(N1)60",
        "delta_n": "Δ(N1)60",
        "n1_60cs": "(N1)60cs",
        "crr75": "CRR 7.5",
        "c_sigma": "Cσ",
        "k_sigma": "Kσ",
        "crr": "CRR M, σ′v",
        "rd": "rd",
        "csr": "CSR",
        "fs": "Factor of safety",
        "trigger_pga": "Trigger PGA (g)",
        "included": "Included",
    }
    view = results.copy()
    view["included"] = view.apply(
        lambda row: "Yes · override" if row["inclusion_override"] else "Yes"
        if row["included"]
        else "No · CH/MH default"
        if row["excluded_by_soil"]
        else "No",
        axis=1,
    )
    view = view.rename(columns=labels)
    st.dataframe(view, use_container_width=True, hide_index=True)
    st.download_button(
        "Download results as CSV",
        results.to_csv(index=False).encode("utf-8"),
        file_name="soilliqupotential-results.csv",
        mime="text/csv",
    )


init_state()
if "_pending_layer_count" in st.session_state:
    st.session_state.layer_count = st.session_state.pop("_pending_layer_count")

st.title("SoilliquPotential")
st.caption("SPT-based liquefaction triggering screening from a layer-by-layer boring log.")
st.info(
    "Engineering screening tool. Review field corrections, susceptibility decisions, "
    "groundwater assumptions, and project requirements before design use."
)

with st.sidebar:
    st.header("Analysis inputs")
    units = st.selectbox("Unit system", ["Metric", "English"])
    analysis_mode = st.radio(
        "Analysis objective",
        ["factorOfSafety", "triggerPga"],
        format_func=lambda value: "Factor of safety at design PGA"
        if value == "factorOfSafety"
        else "Triggering PGA at FS = 1",
    )
    magnitude = st.number_input("Earthquake magnitude, Mw", 3.0, 9.5, 7.5, 0.1)
    st.caption("MSF method: Idriss (1999) relationship for sand, as presented by Boulanger & Idriss (2014), Eq. 2.17.")
    st.latex(r"\mathrm{MSF} = \min\left(6.9e^{-M_w/4} - 0.058,\;1.8\right)")
    st.markdown(
        "[Open Boulanger & Idriss (2014) report](https://faculty.engineering.ucdavis.edu/boulanger/wp-content/uploads/sites/71/2014/09/Boulanger_Idriss_CPT_and_SPT_Liq_triggering_CGM-14-01_20141.pdf)"
    )
    pga_disabled = analysis_mode == "triggerPga"
    pga = st.number_input("Design surface PGA (g)", 0.01, 2.0, 0.30, 0.01, disabled=pga_disabled)
    depth_unit = "m" if units == "Metric" else "ft"
    weight_unit = "kN/m³" if units == "Metric" else "pcf"
    water_table = st.number_input(f"Water table depth ({depth_unit})", 0.0, 10000.0, 1.5, 0.1)
    st.caption(
        "Triggering-PGA mode solves for the surface acceleration that gives "
        "factor of safety 1.0 in each included layer."
        if pga_disabled
        else "Factor of safety will be checked at the entered design PGA."
    )
    st.divider()
    st.subheader("SPT equipment corrections")
    energy_pct = st.number_input("Hammer energy ratio (%)", 1.0, 150.0, 60.0, 1.0)
    borehole_label = st.selectbox(
        "Borehole diameter",
        ["4 in / 102 mm", "6 in / 152 mm", "8 in / 203 mm"],
    )
    borehole_inches = {"4 in / 102 mm": 4.0, "6 in / 152 mm": 6.0, "8 in / 203 mm": 8.0}[borehole_label]
    rod_length = st.number_input(
        f"SPT rod length ({depth_unit})",
        min_value=0.1,
        max_value=1000.0,
        value=6.0 if units == "Metric" else 20.0,
        step=0.5,
    )
    sampler = st.selectbox(
        "Sampler setup",
        ["withLiners", "withoutLiners", "nonStandard"],
        format_func=lambda value: {
            "withLiners": "Standard sampler with liners",
            "withoutLiners": "Standard sampler without liners",
            "nonStandard": "Non-standard sampler",
        }[value],
    )
    rd_mode = st.selectbox(
        "Depth-reduction magnitude",
        ["workbook", "event"],
        format_func=lambda value: "Workbook formula (Mw = 7.5)"
        if value == "workbook"
        else "Use entered earthquake magnitude",
    )
    st.caption(
        "Correction factors: "
        f"CE {energy_pct / 60:.2f} · "
        f"CB {1.0 if borehole_inches == 4 else 1.05 if borehole_inches == 6 else 1.15:.2f}"
    )

st.subheader("Boring log")
left, right = st.columns([1.4, 1], vertical_alignment="bottom")
with left:
    layer_count = st.number_input(
        "Number of layers",
        min_value=1,
        max_value=50,
        step=1,
        key="layer_count",
        on_change=on_layer_count_change,
        args=(units,),
        help="Set the number of layers; new rows are appended at the current profile bottom.",
    )
with right:
    uploaded = st.file_uploader("Import Excel or CSV", type=["xlsx", "csv"])

if uploaded is not None:
    import_col1, import_col2 = st.columns([1, 2])
    with import_col1:
        if st.button("Import file into table", use_container_width=True):
            try:
                imported = read_uploaded_file(uploaded)
                if len(imported) > 50:
                    raise ValueError("The app supports up to 50 layers.")
                reset_editor(imported)
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    with import_col2:
        st.caption("The file must use the selected unit system. The import replaces the current boring log.")

template = template_for_units(units)
csv_bytes = template.to_csv(index=False).encode("utf-8")
excel_bytes = excel_template_bytes(units)
template_col1, template_col2, _ = st.columns([1, 1, 2])
template_col1.download_button("Download CSV template", csv_bytes, "soilliqupotential-template.csv", "text/csv")
template_col2.download_button(
    "Download Excel template",
    excel_bytes,
    "soilliqupotential-template.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
with st.expander("Import format instructions"):
    st.markdown(
        "Use one row per layer, from shallow to deep, with these required columns: "
        "soil_code, top_depth, bottom_depth, unit_weight, spt_n, and fines_percent. "
        "The optional analyze column accepts true or false. CH and MH codes are excluded by default; "
        "set analyze to true to override. Start the first layer at zero depth and keep adjacent "
        "layer boundaries contiguous. Use the same units selected in the sidebar."
    )

frame = st.session_state.layer_frame.copy()
frame["thickness"] = frame["bottom_depth"] - frame["top_depth"]
edited = st.data_editor(
    frame,
    key="layer_editor",
    on_change=on_table_change,
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    disabled=["thickness"],
    column_config={
        "soil_code": st.column_config.TextColumn("Soil code", required=True),
        "top_depth": st.column_config.NumberColumn(f"Top depth ({depth_unit})", min_value=0.0, step=0.1, format="%.2f"),
        "bottom_depth": st.column_config.NumberColumn(f"Bottom depth ({depth_unit})", min_value=0.0, step=0.1, format="%.2f"),
        "thickness": st.column_config.NumberColumn(f"Thickness ({depth_unit})", format="%.2f"),
        "unit_weight": st.column_config.NumberColumn(f"Unit weight ({weight_unit})", min_value=0.1, step=0.5),
        "spt_n": st.column_config.NumberColumn("SPT-N", min_value=0.0, step=1.0),
        "fines_percent": st.column_config.NumberColumn("Fines (%)", min_value=0.0, max_value=100.0, step=1.0),
        "analyze": st.column_config.CheckboxColumn("Analyze", help="CH/MH are off by default. Check to include or uncheck any layer to exclude."),
    },
)
edited = edited.drop(columns=["thickness"], errors="ignore")
edited = remove_blank_rows(edited)
if "analyze" not in edited.columns:
    edited["analyze"] = True
st.session_state.layer_frame = edited[REQUIRED_COLUMNS + ["analyze"]].reset_index(drop=True)
st.session_state.soil_snapshot = st.session_state.layer_frame["soil_code"].fillna("").astype(str).tolist()

profile_col, _ = st.columns([1, 1.4])
with profile_col:
    st.subheader("Scaled soil profile")
    render_profile(st.session_state.layer_frame, depth_unit)

st.caption("The Analyze checkbox is per layer. Uncheck any layer to omit it from the liquefaction-triggering summary.")
run = st.button("Calculate liquefaction potential", type="primary", use_container_width=True)
if run:
    try:
        results, summary = calculate_profile(
            st.session_state.layer_frame,
            units=units,
            magnitude=float(magnitude),
            pga=float(pga),
            water_table=float(water_table),
            energy_pct=float(energy_pct),
            borehole_inches=borehole_inches,
            rod_length=float(rod_length),
            sampler=sampler,
            rd_mode=rd_mode,
            analysis_mode=analysis_mode,
        )
        st.session_state.analysis_result = (results, summary, units)
    except Exception as exc:
        st.error(str(exc))

if st.session_state.analysis_result is not None:
    st.subheader("Layer-by-layer results")
    results, summary, result_units = st.session_state.analysis_result
    display_results(results, summary, result_units)

with st.expander("Calculation scope and assumptions"):
    st.markdown(
        "The app calculates total vertical stress and hydrostatic pore pressure at each layer midpoint, "
        "then applies the SPT energy, borehole, rod-length, and sampler corrections; overburden "
        "normalization; fines correction; CRR and stress adjustments; magnitude scaling; and depth "
        "reduction. For the standard analysis it reports factor of safety at the design PGA. In "
        "triggering-PGA mode it solves the demand corresponding to factor of safety 1.0. CH/MH soil "
        "codes are excluded by default, and the Analyze checkbox allows a visible user override. "
        "This is a preliminary screening calculation, not a substitute for project-specific "
        "geotechnical review."
    )
