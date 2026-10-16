# SoilliquPotential

An interactive Streamlit application for preliminary, SPT-based liquefaction triggering screening from a single boring log.

## Features

- Edit the boring log directly in the browser, or choose a layer count to expand the table.
- View a color-coded soil column with layer thicknesses drawn to scale. Layers with the same soil code use the same color.
- Enter data in metric or English units.
- Choose whether to enter groundwater as depth below ground surface or as ground-surface and water-table elevations above mean sea level (MSL). The app converts either choice to water-table depth for stress calculations.
- Apply SPT energy, borehole diameter, rod-length, and sampler corrections, then calculate normalized SPT values, fines adjustment, resistance, demand, factor of safety, and triggering PGA.
- Analyze at a user-entered design PGA, or solve for triggering PGA at a factor of safety of 1.0.
- Select the Idriss (1999) MSF equation by default, or compare it with digitized MSF curves from the supplied reference figure.
- Exclude any layer with its Analyze checkbox. CH and MH soil codes start excluded and can be included by checking the box.
- Import a boring log from CSV or Excel and download a matching import template.
- Download the layer results as CSV.

## Run locally

Python 3.10 or later is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

On Windows, activate the environment with `.venv\\Scripts\\activate`.

## Import format

Use one row per layer, ordered from shallow to deep. Required columns:

| Column | Meaning |
| --- | --- |
| `soil_code` | Soil classification code, such as SM or CH |
| `top_depth` | Layer top depth from ground surface |
| `bottom_depth` | Layer bottom depth from ground surface |
| `unit_weight` | Bulk unit weight |
| `spt_n` | Measured SPT-N value |
| `fines_percent` | Fines content as a percentage from 0 to 100 |

The optional `analyze` column accepts true or false. The first layer must start at zero depth and layer boundaries must be contiguous. The imported values must use the unit system selected in the sidebar. The app also recognizes common header alternatives such as `soil_type`, `top`, `bottom`, `gamma`, `n_value`, and `fines`.

For the groundwater input, depth is measured downward from the ground surface (zero at grade). Elevation mode uses elevations relative to MSL, with elevations increasing upward; the app computes water-table depth as ground-surface elevation minus water-table elevation. Therefore, a negative calculated depth means the water table is above ground surface.

## Calculation notes

The app is intended for preliminary screening. Check the entered SPT equipment corrections, groundwater assumptions, soil susceptibility, and project criteria before using results in design. Review the calculation method and its applicability with a qualified geotechnical engineer.

## Project files

- `app.py` — Streamlit user interface
- `liquefaction.py` — calculation and import logic
- `msf_methods.py` — MSF equations and approximate digitized curve points
- `assets/msf_reference_figure.png` — user-provided MSF reference figure
- `tests/` — calculation tests

Digitized MSF methods are approximate visual readings from the reference figure and use linear interpolation between chart-read points. The app shows the source figure and its citation alongside the comparison chart.
