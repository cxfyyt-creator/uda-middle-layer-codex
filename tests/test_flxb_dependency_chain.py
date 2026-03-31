import shutil
import unittest
from pathlib import Path

from generators.cmg_generator import generate_cmg
from parsers.cmg_parser import parse_cmg
from transformers import transform_raw_to_standard
from utils.project_paths import TMP_TESTS_DIR
from utils.target_preflight import evaluate_target_preflight


ROOT = Path(__file__).resolve().parents[1]
GEO_DIR = ROOT / "inputs" / "cmg" / "IMEX" / "geo"
TMP_DIR = TMP_TESTS_DIR / "flxb_dependency_chain"


class TestFlxbDependencyChain(unittest.TestCase):
    def test_manifest_keeps_flxb_upstream_producer_hint(self):
        standard = transform_raw_to_standard(parse_cmg(GEO_DIR / "mxgeo008.dat"))
        runtime_inputs = standard.get("case_manifest", {}).get("runtime_inputs", [])
        self.assertTrue(runtime_inputs)
        target = next(item for item in runtime_inputs if item.get("path") == "mxgeo007.flxb")
        self.assertEqual(target.get("producer_case"), "mxgeo007.dat")
        self.assertEqual(target.get("producer_artifact"), "mxgeo007_converted.flxb")
        self.assertTrue(target.get("producer_case_exists"))

    def test_preflight_reports_upstream_flxb_context(self):
        standard = transform_raw_to_standard(parse_cmg(GEO_DIR / "mxgeo008.dat"))
        preflight = evaluate_target_preflight(standard, target="cmg")
        self.assertFalse(preflight["ok"])
        self.assertTrue(any("mxgeo007.flxb" in item and "mxgeo007.dat" in item for item in preflight["blockers"]))

    def test_generation_can_resolve_flxb_from_upstream_converted_artifact(self):
        standard = transform_raw_to_standard(parse_cmg(GEO_DIR / "mxgeo008.dat"))
        if TMP_DIR.exists():
            shutil.rmtree(TMP_DIR)
        TMP_DIR.mkdir(parents=True, exist_ok=True)

        (TMP_DIR / "mxgeo007_converted.flxb").write_text("dummy flux boundary", encoding="utf-8")
        out = TMP_DIR / "mxgeo008_converted.dat"
        generate_cmg(standard, output_file=out)

        self.assertTrue(out.exists())
        self.assertTrue((TMP_DIR / "mxgeo007.flxb").exists())


if __name__ == "__main__":
    unittest.main()
