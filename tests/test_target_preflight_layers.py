import unittest
from pathlib import Path

from source_readers.cmg import parse_cmg
from standardizers import build_standard_ir
from checks.readiness import evaluate_target_readiness


ROOT = Path(__file__).resolve().parents[1]
MXDRM005 = ROOT / "inputs" / "cmg" / "IMEX" / "drm" / "mxdrm005.dat"


class TestTargetPreflightLayers(unittest.TestCase):
    def test_preflight_returns_layered_structure(self):
        standard = build_standard_ir(parse_cmg(MXDRM005))
        preflight = evaluate_target_readiness(standard, target="cmg")

        self.assertTrue(preflight["ok"], msg=str(preflight))
        self.assertIn("layers", preflight)
        self.assertIn("reason_summary", preflight)
        for layer in ("format_coverage", "generator_capability", "validation_rule", "completeness"):
            self.assertIn(layer, preflight["layers"])
        self.assertGreaterEqual(preflight["reason_summary"]["generator_capability"]["warnings"], 1)
        self.assertEqual(preflight["layers"]["generator_capability"]["blockers"], [])

    def test_preflight_classifies_failure_types(self):
        data = {
            "meta": {"unit_system": "field", "source_software": "petrel_eclipse"},
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
                    "source_file": "model.ext",
                    "dataset": "PORO",
                    "format": "CUSTOM_REF",
                }
            },
            "fluid": {"model": "BLACKOIL"},
            "rockfluid": {},
            "unknown_keywords": {"FOO": []},
        }

        preflight = evaluate_target_readiness(data, target="cmg")

        self.assertFalse(preflight["ok"])
        self.assertTrue(any(item["reason_type"] == "format_coverage" for item in preflight["issues"]))
        self.assertTrue(any(item["reason_type"] == "generator_capability" for item in preflight["issues"]))
        self.assertTrue(any(item["reason_type"] == "ir_expression" for item in preflight["issues"]))
        self.assertTrue(any("structured backend does not yet support ref values" in item for item in preflight["blockers"]))
        self.assertGreaterEqual(preflight["reason_summary"]["format_coverage"]["warnings"], 1)
        self.assertGreaterEqual(preflight["reason_summary"]["generator_capability"]["blockers"], 1)
        self.assertGreaterEqual(preflight["reason_summary"]["ir_expression"]["blockers"], 1)
        self.assertIn("当前主要卡点", preflight["headline"])
        self.assertIn("生成器", preflight["plain_message"])
        self.assertIn("ref", preflight["next_action"])


if __name__ == "__main__":
    unittest.main()
