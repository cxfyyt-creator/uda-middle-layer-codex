import shutil
import unittest
from pathlib import Path

from target_writers.cmg import generate_cmg
from source_readers.cmg import parse_cmg
from standardizers import build_standard_ir
from infra.case_materialization import materialize_case_input_files
from infra.case_dependencies import analyze_case_assembly
from infra.project_paths import TMP_TESTS_DIR
from checks.readiness import evaluate_target_readiness


ROOT = Path(__file__).resolve().parents[1]
GEO_DIR = ROOT / "inputs" / "cmg" / "IMEX" / "geo"
TMP_DIR = TMP_TESTS_DIR / "flxb_dependency_chain"


class TestFlxbDependencyChain(unittest.TestCase):
    def test_case_assembly_detects_declared_upstream_link(self):
        producer = build_standard_ir(parse_cmg(GEO_DIR / "mxgeo007.dat"))
        consumer = build_standard_ir(parse_cmg(GEO_DIR / "mxgeo008.dat"))
        assembly = analyze_case_assembly([producer, consumer])

        self.assertTrue(assembly["ok"])
        self.assertEqual(assembly["resolved_links"], 1)
        target = next(item for item in assembly["cases"] if item.get("root_file") == "mxgeo008.dat")
        self.assertTrue(target["ok"])
        self.assertEqual(target["resolved_links"][0]["producer_case"], "mxgeo007.dat")
        self.assertEqual(target["resolved_links"][0]["producer_artifact"], "mxgeo007_converted.flxb")

    def test_case_assembly_reports_missing_upstream_case(self):
        consumer = build_standard_ir(parse_cmg(GEO_DIR / "mxgeo008.dat"))
        assembly = analyze_case_assembly([consumer])

        self.assertFalse(assembly["ok"])
        self.assertEqual(assembly["missing_links"], 1)
        target = assembly["cases"][0]
        self.assertFalse(target["ok"])
        self.assertEqual(target["missing_links"][0]["producer_case"], "mxgeo007.dat")

    def test_manifest_keeps_flxb_runtime_output_for_producer_case(self):
        standard = build_standard_ir(parse_cmg(GEO_DIR / "mxgeo007.dat"))
        runtime_outputs = standard.get("case_manifest", {}).get("runtime_outputs", [])
        self.assertTrue(runtime_outputs)
        target = next(item for item in runtime_outputs if item.get("path") == "mxgeo007.flxb")
        self.assertEqual(target.get("producer_case"), "mxgeo007.dat")
        self.assertEqual(target.get("generated_artifact"), "mxgeo007_converted.flxb")
        self.assertTrue(any(item.get("path") == "mxgeo007.sr3" for item in runtime_outputs))

    def test_manifest_keeps_flxb_upstream_producer_hint(self):
        standard = build_standard_ir(parse_cmg(GEO_DIR / "mxgeo008.dat"))
        runtime_inputs = standard.get("case_manifest", {}).get("runtime_inputs", [])
        self.assertTrue(runtime_inputs)
        target = next(item for item in runtime_inputs if item.get("path") == "mxgeo007.flxb")
        self.assertEqual(target.get("producer_case"), "mxgeo007.dat")
        self.assertEqual(target.get("producer_artifact"), "mxgeo007_converted.flxb")
        self.assertTrue(target.get("producer_case_exists"))

    def test_preflight_reports_upstream_flxb_context(self):
        standard = build_standard_ir(parse_cmg(GEO_DIR / "mxgeo008.dat"))
        preflight = evaluate_target_readiness(standard, target="cmg")
        self.assertFalse(preflight["ok"])
        self.assertTrue(any("mxgeo007.flxb" in item and "mxgeo007.dat" in item for item in preflight["blockers"]))
        self.assertIn("当前主要卡点", preflight["headline"])
        self.assertIn("运行时依赖文件", preflight["plain_message"])

    def test_generation_can_resolve_flxb_from_upstream_converted_artifact(self):
        standard = {
            "meta": {
                "source_software": "cmg_imex",
                "source_file": "mxgeo008.dat",
                "unit_system": "field",
                "conversion_timestamp": "2026-03-31T00:00:00",
            },
            "case_manifest": {
                "root_file": "mxgeo008.dat",
                "source_dir": str(GEO_DIR),
                "static_inputs": [],
                "runtime_inputs": [
                    {
                        "kind": "FLXB-IN",
                        "path": "mxgeo007.flxb",
                        "required": True,
                        "producer_case": "mxgeo007.dat",
                        "producer_artifact": "mxgeo007_converted.flxb",
                        "exists": False,
                    }
                ],
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
                "pvt_table": {"type": "table", "columns": ["p", "rs", "bo", "eg", "viso", "visg"], "rows": [[1000.0, 100.0, 1.2, 100.0, 1.0, 0.02]]},
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
        if TMP_DIR.exists():
            shutil.rmtree(TMP_DIR)
        TMP_DIR.mkdir(parents=True, exist_ok=True)

        (TMP_DIR / "mxgeo007_converted.flxb").write_text("dummy flux boundary", encoding="utf-8")
        out = TMP_DIR / "mxgeo008_converted.dat"
        generate_cmg(standard, output_file=out)

        self.assertTrue(out.exists())
        self.assertTrue((TMP_DIR / "mxgeo007.flxb").exists())

    def test_case_materialization_can_resolve_flxb_from_upstream_converted_artifact(self):
        standard = {
            "case_manifest": {
                "root_file": "mxgeo008.dat",
                "source_dir": str(GEO_DIR),
                "static_inputs": [],
                "runtime_inputs": [
                    {
                        "kind": "FLXB-IN",
                        "path": "mxgeo007.flxb",
                        "required": True,
                        "producer_case": "mxgeo007.dat",
                        "producer_artifact": "mxgeo007_converted.flxb",
                        "exists": False,
                    }
                ],
                "runtime_outputs": [],
            }
        }
        if TMP_DIR.exists():
            shutil.rmtree(TMP_DIR)
        TMP_DIR.mkdir(parents=True, exist_ok=True)

        (TMP_DIR / "mxgeo007_converted.flxb").write_text("dummy flux boundary", encoding="utf-8")
        summary = materialize_case_input_files(standard, TMP_DIR / "mxgeo008_converted.dat")

        self.assertEqual(summary["missing"], [])
        self.assertEqual(summary["resolved_paths"], ["mxgeo007.flxb"])
        self.assertTrue((TMP_DIR / "mxgeo007.flxb").exists())


if __name__ == "__main__":
    unittest.main()
