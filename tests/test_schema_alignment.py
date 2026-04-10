import unittest

from standardizers import normalize_standard_ir
from target_mappers.cmg import build_cmg_target_ir
from target_mappers.petrel import build_petrel_target_ir
from checks import validate_standard_model


class TestSchemaAlignment(unittest.TestCase):
    def test_schema_accepts_timeline_events_and_unparsed_blocks(self):
        data = {
            "uda_version": "1.0.0",
            "meta": {
                "source_software": "petrel_eclipse",
                "source_file": "case.DATA",
                "unit_system": "field",
                "conversion_timestamp": "2026-04-01T00:00:00",
            },
            "case_manifest": {
                "root_file": "case.DATA",
                "source_dir": "inputs/petrel",
                "static_inputs": [],
                "runtime_inputs": [],
                "runtime_outputs": [],
            },
            "grid": {
                "grid_type": "CART",
                "ni": 1,
                "nj": 1,
                "nk": 1,
                "di": {"type": "scalar", "value": 10.0},
                "dj": {"type": "scalar", "value": 10.0},
                "dk": {"type": "scalar", "value": 5.0},
            },
            "reservoir": {
                "porosity": {"type": "scalar", "value": 0.2},
                "perm_i": {"type": "scalar", "value": 100.0},
                "perm_j": {"type": "scalar", "value": 100.0},
                "perm_k": {"type": "scalar", "value": 10.0},
            },
            "fluid": {
                "pvt_table": {
                    "type": "table",
                    "columns": ["p", "rs", "bo", "eg", "viso", "visg"],
                    "rows": [[1000.0, 100.0, 1.2, 100.0, 1.0, 0.02]],
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
                "swt_table": {
                    "type": "table",
                    "columns": ["sw", "krw", "krow", "pcow"],
                    "rows": [[0.2, 0.0, 1.0, 0.0], [0.8, 1.0, 0.0, 0.0]],
                },
                "slt_table": {
                    "type": "table",
                    "columns": ["sl", "krg", "krog", "pcog"],
                    "rows": [[0.2, 0.0, 1.0, 0.0], [0.8, 1.0, 0.0, 0.0]],
                },
            },
            "initial": {
                "ref_depth": {"type": "scalar", "value": 1000.0},
                "ref_pressure": {"type": "scalar", "value": 2000.0},
            },
            "numerical": {},
            "wells": [],
            "timeline_events": [
                {
                    "well_name": "P1",
                    "absolute_days": 10.0,
                    "event_type": "WELL_TARGET_CHANGE",
                    "target": "BHP",
                    "value": 1500.0,
                }
            ],
            "unparsed_blocks": [
                {
                    "line": 99,
                    "text": "UNKNOWN_KW 1 2 3",
                    "reason": "not implemented yet",
                    "source": "petrel",
                }
            ],
        }

        model = validate_standard_model(data, strict=True)

        self.assertEqual(model.case_manifest.root_file, "case.DATA")
        self.assertEqual(len(model.timeline_events), 1)
        self.assertEqual(model.timeline_events[0].well_name, "P1")
        self.assertEqual(len(model.unparsed_blocks), 1)
        self.assertEqual(model.unparsed_blocks[0].line, 99)

    def test_schema_accepts_internal_equalsi_ref(self):
        data = {
            "uda_version": "1.0.0",
            "meta": {
                "source_software": "cmg_imex",
                "source_file": "case.dat",
                "unit_system": "field",
                "conversion_timestamp": "2026-04-08T00:00:00",
            },
            "case_manifest": {
                "root_file": "case.dat",
                "source_dir": "inputs/cmg",
                "static_inputs": [],
                "runtime_inputs": [],
                "runtime_outputs": [],
            },
            "grid": {
                "grid_type": "CART",
                "ni": 1,
                "nj": 1,
                "nk": 1,
                "di": {"type": "scalar", "value": 10.0},
                "dj": {"type": "scalar", "value": 10.0},
                "dk": {"type": "scalar", "value": 5.0},
            },
            "reservoir": {
                "porosity": {
                    "type": "ref",
                    "source_file": "case.sip",
                    "dataset": "POR",
                    "format": "SIP_DATA",
                },
                "perm_i": {
                    "type": "ref",
                    "source_file": "case.sip",
                    "dataset": "PERMI",
                    "format": "SIP_DATA",
                },
                "perm_j": {
                    "type": "ref",
                    "relation": "EQUALSI",
                    "source_key": "perm_i",
                    "source_file": "",
                    "scale": 1.0,
                    "source_format_hint": {"keyword": "*EQUALSI"},
                },
            },
            "fluid": {
                "pvt_table": {
                    "type": "table",
                    "columns": ["p", "rs", "bo", "eg", "viso", "visg"],
                    "rows": [[1000.0, 100.0, 1.2, 100.0, 1.0, 0.02]],
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
                "swt_table": {
                    "type": "table",
                    "columns": ["sw", "krw", "krow", "pcow"],
                    "rows": [[0.2, 0.0, 1.0, 0.0], [0.8, 1.0, 0.0, 0.0]],
                },
                "slt_table": {
                    "type": "table",
                    "columns": ["sl", "krg", "krog", "pcog"],
                    "rows": [[0.2, 0.0, 1.0, 0.0], [0.8, 1.0, 0.0, 0.0]],
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
        }

        model = validate_standard_model(data, strict=True)

        self.assertEqual(model.reservoir.perm_j.type, "ref")
        self.assertEqual(model.reservoir.perm_j.relation, "EQUALSI")
        self.assertEqual(model.reservoir.perm_j.source_key, "perm_i")

    def test_normalize_standard_ir_keeps_target_specific_fields_out(self):
        data = {
            "uda_version": "1.0.0",
            "meta": {
                "source_software": "petrel_eclipse",
                "source_file": "case.DATA",
                "unit_system": "field",
                "conversion_timestamp": "2026-04-08T00:00:00",
            },
            "grid": {
                "grid_type": "RADIAL",
                "ni": 1,
                "nj": 1,
                "nk": 1,
                "di": {"type": "scalar", "value": 10.0},
                "dj": {"type": "scalar", "value": 360.0},
                "dk": {"type": "scalar", "value": 5.0},
            },
            "reservoir": {
                "porosity": {"type": "scalar", "value": 0.2},
                "perm_i": {"type": "scalar", "value": 100.0},
                "perm_k": {"type": "scalar", "value": 10.0},
            },
            "fluid": {
                "pvto_table": {
                    "type": "table",
                    "columns": ["rs", "p", "bo", "viso"],
                    "rows": [[0.1, 1000.0, 1.2, 1.0]],
                },
                "pvdg_table": {
                    "type": "table",
                    "columns": ["p", "bg", "visg"],
                    "rows": [[1000.0, 10.0, 0.02]],
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
                "swfn_table": {
                    "type": "table",
                    "columns": ["sw", "krw", "pcow"],
                    "rows": [[0.2, 0.0, 0.0], [0.8, 1.0, 0.0]],
                },
                "sof2_table": {
                    "type": "table",
                    "columns": ["so", "krog"],
                    "rows": [[0.0, 0.0], [0.8, 1.0]],
                },
            },
            "initial": {
                "ref_pressure": {"type": "scalar", "value": 2000.0},
            },
            "numerical": {},
            "wells": [],
            "timeline_events": [],
            "unparsed_blocks": [],
        }

        standardized = normalize_standard_ir(data)

        self.assertNotIn("pvt_table", standardized["fluid"])
        self.assertIn("oil_compressibility", standardized["fluid"])
        self.assertIn("oil_viscosity_coeff", standardized["fluid"])
        self.assertNotIn("swt_table", standardized["rockfluid"])
        self.assertNotIn("slt_table", standardized["rockfluid"])
        self.assertIn("bubble_point_pressure", standardized["initial"])
        self.assertEqual(standardized["reservoir"]["perm_j"]["value"], 100.0)

    def test_cmg_target_builder_derives_target_specific_fields(self):
        data = {
            "uda_version": "1.0.0",
            "meta": {
                "source_software": "petrel_eclipse",
                "source_file": "case.DATA",
                "unit_system": "field",
                "conversion_timestamp": "2026-04-08T00:00:00",
            },
            "grid": {
                "grid_type": "RADIAL",
                "ni": 1,
                "nj": 1,
                "nk": 1,
                "di": {"type": "scalar", "value": 10.0},
                "dj": {"type": "scalar", "value": 360.0},
                "dk": {"type": "scalar", "value": 5.0},
            },
            "reservoir": {
                "porosity": {"type": "scalar", "value": 0.2},
                "perm_i": {"type": "scalar", "value": 100.0},
                "perm_k": {"type": "scalar", "value": 10.0},
            },
            "fluid": {
                "pvto_table": {
                    "type": "table",
                    "columns": ["rs", "p", "bo", "viso"],
                    "rows": [[0.1, 1000.0, 1.2, 1.0]],
                },
                "pvdg_table": {
                    "type": "table",
                    "columns": ["p", "bg", "visg"],
                    "rows": [[1000.0, 10.0, 0.02]],
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
                "swfn_table": {
                    "type": "table",
                    "columns": ["sw", "krw", "pcow"],
                    "rows": [[0.2, 0.0, 0.0], [0.8, 1.0, 0.0]],
                },
                "sof2_table": {
                    "type": "table",
                    "columns": ["so", "krog"],
                    "rows": [[0.0, 0.0], [0.8, 1.0]],
                },
            },
            "initial": {
                "ref_pressure": {"type": "scalar", "value": 2000.0},
            },
            "numerical": {},
            "wells": [],
            "timeline_events": [],
            "unparsed_blocks": [],
        }

        standardized = normalize_standard_ir(data)
        mapped = build_cmg_target_ir(standardized)

        self.assertIn("pvt_table", mapped["fluid"])
        self.assertIn("swt_table", mapped["rockfluid"])
        self.assertIn("slt_table", mapped["rockfluid"])

    def test_petrel_target_builder_derives_petrel_specific_fields(self):
        data = {
            "uda_version": "1.0.0",
            "meta": {
                "source_software": "cmg_imex",
                "source_file": "case.dat",
                "unit_system": "field",
                "conversion_timestamp": "2026-04-08T00:00:00",
            },
            "grid": {
                "grid_type": "CART",
                "ni": 1,
                "nj": 1,
                "nk": 1,
                "di": {"type": "scalar", "value": 10.0},
                "dj": {"type": "scalar", "value": 10.0},
                "dk": {"type": "scalar", "value": 5.0},
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
        }

        standardized = normalize_standard_ir(data)
        mapped = build_petrel_target_ir(standardized)

        self.assertIn("pvto_table", mapped["fluid"])
        self.assertIn("pvdg_table", mapped["fluid"])
        self.assertIn("rock_ref_pressure", mapped["fluid"])
        self.assertIn("rock_compressibility", mapped["fluid"])


if __name__ == "__main__":
    unittest.main()
