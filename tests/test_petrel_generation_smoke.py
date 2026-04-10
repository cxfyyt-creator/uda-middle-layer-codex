import shutil
import unittest
from pathlib import Path

from target_writers.petrel import generate_petrel
from infra.project_paths import TMP_TESTS_DIR


TMP_DIR = TMP_TESTS_DIR / "petrel_generation_smoke"


class TestPetrelGenerationSmoke(unittest.TestCase):
    def setUp(self):
        if TMP_DIR.exists():
            shutil.rmtree(TMP_DIR)
        TMP_DIR.mkdir(parents=True, exist_ok=True)

    def test_generate_petrel_writes_output_and_reports(self):
        data = {
            "meta": {
                "source_software": "petrel_eclipse",
                "source_file": "smoke_case.DATA",
                "unit_system": "field",
                "start_date": "2026-01-01",
            },
            "grid": {
                "grid_type": "CART",
                "ni": 1,
                "nj": 1,
                "nk": 1,
                "di": {"type": "scalar", "value": 10.0},
                "dj": {"type": "scalar", "value": 10.0},
                "dk": {"type": "scalar", "value": 5.0},
                "depth_ref_block": {"type": "scalar", "value": 1000.0, "i": 1, "j": 1, "k": 1},
            },
            "reservoir": {
                "porosity": {"type": "scalar", "value": 0.2},
                "perm_i": {"type": "scalar", "value": 100.0},
                "perm_j": {"type": "scalar", "value": 100.0},
                "perm_k": {"type": "scalar", "value": 10.0},
            },
            "fluid": {
                "model": "BLACKOIL",
                "pvto_table": {
                    "type": "table",
                    "columns": ["rs", "p", "bo", "viso"],
                    "rows": [[100.0, 2000.0, 1.2, 1.0]],
                },
                "pvdg_table": {
                    "type": "table",
                    "columns": ["p", "bg", "visg"],
                    "rows": [[2000.0, 0.01, 0.02]],
                },
                "oil_density": {"type": "scalar", "value": 50.0},
                "gas_density": {"type": "scalar", "value": 0.05},
                "water_density": {"type": "scalar", "value": 62.0},
                "water_fvf": {"type": "scalar", "value": 1.0},
                "water_compressibility": {"type": "scalar", "value": 1e-6},
                "water_ref_pressure": {"type": "scalar", "value": 14.7},
                "water_viscosity": {"type": "scalar", "value": 0.5},
            },
            "rockfluid": {
                "swof_table": {
                    "type": "table",
                    "columns": ["sw", "krw", "krow", "pcow"],
                    "rows": [[0.2, 0.0, 1.0, 0.0], [0.8, 1.0, 0.0, 0.0]],
                },
                "sgof_table": {
                    "type": "table",
                    "columns": ["sg", "krg", "krog", "pcog"],
                    "rows": [[0.0, 0.0, 1.0, 0.0], [0.8, 1.0, 0.0, 0.0]],
                },
            },
            "initial": {
                "ref_depth": {"type": "scalar", "value": 1000.0},
                "ref_pressure": {"type": "scalar", "value": 2000.0},
            },
            "numerical": {},
            "wells": [],
            "timeline_events": [],
            "unparsed_blocks": [],
            "uda_version": "1.0.0",
        }

        report_dir = TMP_DIR / "reports"
        out = TMP_DIR / "smoke_case_converted.DATA"
        content = generate_petrel(data, output_file=out, report_dir=report_dir)

        self.assertTrue(out.exists())
        self.assertIn("RUNSPEC", content)
        self.assertIn("PROPS", content)
        self.assertTrue((report_dir / "in_memory_json.generate_petrel.report.md").exists())
        self.assertTrue((report_dir / "in_memory_json.generate_petrel.report.json").exists())

    def test_generate_petrel_can_split_cmg_pvt_table(self):
        data = {
            "meta": {
                "source_software": "cmg_imex",
                "source_file": "cmg_case.dat",
                "unit_system": "field",
                "start_date": "2026-01-01",
            },
            "grid": {
                "grid_type": "CART",
                "ni": 1,
                "nj": 1,
                "nk": 1,
                "di": {"type": "scalar", "value": 10.0},
                "dj": {"type": "scalar", "value": 10.0},
                "dk": {"type": "scalar", "value": 5.0},
                "depth_ref_block": {"type": "scalar", "value": 1000.0, "i": 1, "j": 1, "k": 1},
            },
            "reservoir": {
                "porosity": {"type": "scalar", "value": 0.2},
                "perm_i": {"type": "scalar", "value": 100.0},
                "perm_j": {"type": "scalar", "value": 100.0},
                "perm_k": {"type": "scalar", "value": 10.0},
                "rock_ref_pressure": {"type": "scalar", "value": 3000.0},
                "rock_compressibility": {"type": "scalar", "value": 1e-6},
            },
            "fluid": {
                "model": "BLACKOIL",
                "pvt_table": {
                    "type": "table",
                    "columns": ["p", "rs", "bo", "eg", "viso", "visg"],
                    "rows": [[2000.0, 100.0, 1.2, 100.0, 1.0, 0.02]],
                },
                "oil_density": {"type": "scalar", "value": 50.0},
                "gas_density": {"type": "scalar", "value": 0.05},
                "water_density": {"type": "scalar", "value": 62.0},
                "water_fvf": {"type": "scalar", "value": 1.0},
                "water_compressibility": {"type": "scalar", "value": 1e-6},
                "water_ref_pressure": {"type": "scalar", "value": 14.7},
                "water_viscosity": {"type": "scalar", "value": 0.5},
            },
            "rockfluid": {
                "swof_table": {
                    "type": "table",
                    "columns": ["sw", "krw", "krow", "pcow"],
                    "rows": [[0.2, 0.0, 1.0, 0.0], [0.8, 1.0, 0.0, 0.0]],
                },
                "sgof_table": {
                    "type": "table",
                    "columns": ["sg", "krg", "krog", "pcog"],
                    "rows": [[0.0, 0.0, 1.0, 0.0], [0.8, 1.0, 0.0, 0.0]],
                },
            },
            "initial": {
                "ref_depth": {"type": "scalar", "value": 1000.0},
                "ref_pressure": {"type": "scalar", "value": 2000.0},
            },
            "numerical": {},
            "wells": [],
            "timeline_events": [],
            "unparsed_blocks": [],
            "uda_version": "1.0.0",
        }

        out = TMP_DIR / "cmg_case_converted.DATA"
        content = generate_petrel(data, output_file=out, report_dir=TMP_DIR / "reports_split")

        self.assertTrue(out.exists())
        self.assertIn("PVTO", content)
        self.assertIn("PVDG", content)
        self.assertIn("ROCK", content)


if __name__ == "__main__":
    unittest.main()
