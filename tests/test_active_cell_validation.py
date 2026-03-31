import unittest
from pathlib import Path

from parsers.cmg_parser import parse_cmg
from transformers import transform_raw_to_standard
from utils.target_preflight import evaluate_target_preflight
from validators import validate_standard_model


ROOT = Path(__file__).resolve().parents[1]
GEO_DIR = ROOT / "inputs" / "cmg" / "IMEX" / "geo"


class TestActiveCellValidation(unittest.TestCase):
    def test_explicit_null_and_pinchout_arrays_are_parsed(self):
        standard = transform_raw_to_standard(parse_cmg(ROOT / "inputs" / "cmg" / "IMEX" / "gro" / "mxgro023.dat"))
        self.assertEqual(standard.get("grid", {}).get("active_cell_mask", {}).get("type"), "scalar")
        self.assertEqual(standard.get("grid", {}).get("active_cell_mask", {}).get("value"), 1.0)
        self.assertEqual(standard.get("grid", {}).get("pinchout_array", {}).get("type"), "scalar")
        self.assertEqual(standard.get("grid", {}).get("pinchout_array", {}).get("value"), 1.0)
        validate_standard_model(standard, strict=True)

    def test_geo_zero_porosity_null_blocks_are_inferred_and_allowed(self):
        for name in ("mxgeo004.dat", "mxgeo006.dat"):
            standard = transform_raw_to_standard(parse_cmg(GEO_DIR / name))
            mask = standard.get("grid", {}).get("active_cell_mask", {})
            self.assertEqual(mask.get("type"), "array", msg=name)
            self.assertEqual(standard.get("grid", {}).get("cell_activity_mode"), "inferred_from_zero_porosity", msg=name)
            validate_standard_model(standard, strict=True)

    def test_zero_porosity_in_active_cells_is_still_blocked(self):
        data = {
            "meta": {
                "source_software": "petrel_eclipse",
                "unit_system": "field",
                "conversion_timestamp": "2026-03-31T00:00:00",
            },
            "grid": {
                "grid_type": "CART",
                "ni": 2,
                "nj": 1,
                "nk": 1,
                "di": {"type": "array", "values": [10.0, 10.0]},
                "dj": {"type": "scalar", "value": 10.0},
                "dk": {"type": "scalar", "value": 5.0},
                "active_cell_mask": {"type": "array", "values": [1.0, 1.0]},
            },
            "reservoir": {
                "porosity": {"type": "array", "values": [0.0, 0.2]},
                "perm_i": {"type": "array", "values": [100.0, 100.0]},
                "perm_j": {"type": "array", "values": [100.0, 100.0]},
                "perm_k": {"type": "array", "values": [10.0, 10.0]},
            },
            "fluid": {
                "model": "BLACKOIL",
                "pvt_table": {"type": "table", "columns": ["p", "rs", "bo", "eg", "viso", "visg"], "rows": [[1000, 100, 1.2, 100, 1.0, 0.02]]},
                "oil_density": {"type": "scalar", "value": 50.0},
                "gas_density": {"type": "scalar", "value": 0.05},
                "water_density": {"type": "scalar", "value": 62.0},
                "water_fvf": {"type": "scalar", "value": 1.0},
                "water_compressibility": {"type": "scalar", "value": 1e-6},
                "water_ref_pressure": {"type": "scalar", "value": 14.7},
                "water_viscosity": {"type": "scalar", "value": 0.5},
            },
            "rockfluid": {
                "swt_table": {"type": "table", "columns": ["sw", "krw", "krow", "pcow"], "rows": [[0.2, 0.0, 1.0, 0.0], [0.8, 1.0, 0.0, 0.0]]},
                "slt_table": {"type": "table", "columns": ["sl", "krg", "krog", "pcog"], "rows": [[0.2, 0.0, 1.0, 0.0], [0.8, 1.0, 0.0, 0.0]]},
            },
            "initial": {},
            "wells": [],
        }

        with self.assertRaises(Exception):
            validate_standard_model(data, strict=True)

        preflight = evaluate_target_preflight(data, target="cmg")
        self.assertFalse(preflight["ok"])
        self.assertTrue(any("active cells with zero porosity" in item for item in preflight["blockers"]))
        self.assertTrue(any(item["reason_type"] == "validation_rule" for item in preflight["issues"]))


if __name__ == "__main__":
    unittest.main()
