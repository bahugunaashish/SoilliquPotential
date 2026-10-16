import math
import unittest

import pandas as pd

from liquefaction import (
    calculate_profile,
    is_default_excluded,
    normalize_import_frame,
    template_frame,
    water_table_depth_from_inputs,
)
from msf_methods import IDRISS_1999, msf_for_method


def calculate(frame, mode="factorOfSafety"):
    return calculate_profile(
        frame,
        units="Metric",
        magnitude=7.5,
        pga=0.3,
        water_table=0.5,
        energy_pct=60,
        borehole_inches=4,
        rod_length=6,
        sampler="withLiners",
        rd_mode="workbook",
        analysis_mode=mode,
    )


class CalculatorTests(unittest.TestCase):
    def test_water_table_depth_and_elevation_inputs_convert_consistently(self):
        depth = water_table_depth_from_inputs(
            "Depth below ground surface", depth_below_surface=2.0
        )
        elevation = water_table_depth_from_inputs(
            "Elevation above MSL",
            ground_surface_elevation=105.0,
            water_table_elevation=103.0,
        )
        above_grade = water_table_depth_from_inputs(
            "Elevation above MSL",
            ground_surface_elevation=105.0,
            water_table_elevation=106.0,
        )
        self.assertEqual(depth, elevation)
        self.assertEqual(above_grade, -1.0)

    def test_template_calculates_stresses_and_defaults_ch_excluded(self):
        results, summary = calculate(template_frame())
        self.assertAlmostEqual(results.loc[0, "mid_depth"], 1.0)
        self.assertGreater(results.loc[0, "sigma_v"], results.loc[0, "sigma_eff"])
        self.assertTrue(results.loc[0, "included"])
        self.assertFalse(results.loc[2, "included"])
        self.assertTrue(math.isfinite(summary["minimum_fs"]))

    def test_trigger_mode_sets_factor_of_safety_to_one(self):
        frame = template_frame().iloc[:2].copy()
        results, _ = calculate(frame, mode="triggerPga")
        self.assertTrue((results["trigger_pga"] > 0).all())
        self.assertTrue(((results["fs"] - 1.0).abs() < 1e-12).all())

    def test_ch_mh_exclusion_and_checkbox_override(self):
        self.assertTrue(is_default_excluded("CH"))
        self.assertTrue(is_default_excluded("MH/Clay"))
        self.assertFalse(is_default_excluded("SM"))
        frame = template_frame().iloc[[2]].copy()
        frame["top_depth"] = [0.0]
        frame["bottom_depth"] = [3.0]
        frame["analyze"] = [True]
        result, _ = calculate(frame)
        self.assertTrue(result.loc[0, "included"])
        self.assertTrue(result.loc[0, "inclusion_override"])

    def test_import_aliases_and_defaults(self):
        source = pd.DataFrame({
            "Soil Type": ["SM", "CH"], "Top": [0, 2], "Bottom": [2, 4],
            "Gamma": [18, 20], "N Value": [10, 25], "Fines": [10, 60],
        })
        normalized = normalize_import_frame(source)
        self.assertEqual(normalized["analyze"].tolist(), [True, False])
        self.assertEqual(normalized.loc[1, "soil_code"], "CH")

    def test_inconsistent_depths_are_rejected(self):
        frame = template_frame().iloc[:2].copy()
        frame.loc[1, "top_depth"] = 2.2
        with self.assertRaisesRegex(ValueError, "contiguous"):
            calculate(frame)

    def test_idriss_1999_is_default_formula_and_capped(self):
        self.assertAlmostEqual(msf_for_method(IDRISS_1999, 7.5), 1.0, places=2)
        self.assertEqual(msf_for_method(IDRISS_1999, 4.5), 1.8)

    def test_digitized_method_interpolates_and_rejects_extrapolation(self):
        self.assertAlmostEqual(msf_for_method("Seed & Idriss (1982)", 6.0), 1.32)
        with self.assertRaisesRegex(ValueError, "digitized only"):
            msf_for_method("Ambraseys (1985)", 5.0)

    def test_profile_uses_selected_msf_method(self):
        frame = template_frame().iloc[:1].copy()
        _, summary = calculate_profile(
            frame,
            units="Metric",
            magnitude=7.5,
            pga=0.3,
            water_table=0.5,
            energy_pct=60,
            borehole_inches=4,
            rod_length=6,
            sampler="withLiners",
            rd_mode="workbook",
            analysis_mode="factorOfSafety",
            msf_method="Seed & Idriss (1982)",
        )
        self.assertEqual(summary["msf_method"], "Seed & Idriss (1982)")
        self.assertAlmostEqual(summary["msf"], msf_for_method("Seed & Idriss (1982)", 7.5))


if __name__ == "__main__":
    unittest.main()
