import shutil
import unittest
import stat
from pathlib import Path

from generators.cmg_generator import generate_cmg
from parsers.cmg_parser import parse_cmg
from transformers import transform_raw_to_standard
from utils.target_preflight import evaluate_target_preflight
from utils.project_paths import TMP_TESTS_DIR
from validators import validate_standard_model


ROOT = Path(__file__).resolve().parents[1]
MXDRM005 = ROOT / "inputs" / "cmg" / "IMEX" / "drm" / "mxdrm005.dat"
TMP_DIR = TMP_TESTS_DIR / "ir_upgrade_v1"


def _safe_rmtree(path: Path):
    if not path.exists():
        return

    def _onerror(func, target, exc_info):
        Path(target).chmod(stat.S_IWRITE)
        func(target)

    shutil.rmtree(path, onerror=_onerror)


class TestIRUpgradeV1(unittest.TestCase):
    def test_parse_builds_case_manifest_for_mxdrm005(self):
        raw = parse_cmg(MXDRM005)
        manifest = raw.get("case_manifest", {})
        self.assertEqual(manifest.get("root_file"), "mxdrm005.dat")
        self.assertEqual(
            [item.get("path") for item in manifest.get("static_inputs", [])],
            ["mxdrm005.sip"],
        )
        self.assertEqual(manifest.get("runtime_inputs", []), [])

    def test_parse_builds_ref_values_for_sip_data(self):
        raw = parse_cmg(MXDRM005)
        reservoir = raw.get("reservoir", {})

        self.assertEqual(reservoir.get("porosity", {}).get("type"), "ref")
        self.assertEqual(reservoir.get("porosity", {}).get("dataset"), "POR")
        self.assertEqual(reservoir.get("porosity", {}).get("source_file"), "mxdrm005.sip")

        self.assertEqual(reservoir.get("perm_i", {}).get("type"), "ref")
        self.assertEqual(reservoir.get("perm_i", {}).get("dataset"), "PERMI")
        self.assertEqual(reservoir.get("perm_i", {}).get("source_file"), "mxdrm005.sip")

    def test_transform_and_schema_keep_case_manifest_and_ref(self):
        standard = transform_raw_to_standard(parse_cmg(MXDRM005))
        validate_standard_model(standard, strict=True)

        manifest = standard.get("case_manifest", {})
        self.assertEqual(manifest.get("root_file"), "mxdrm005.dat")
        self.assertEqual(
            [item.get("path") for item in manifest.get("static_inputs", [])],
            ["mxdrm005.sip"],
        )
        self.assertEqual(standard.get("reservoir", {}).get("porosity", {}).get("type"), "ref")

    def test_source_faithful_generation_still_materializes_case_inputs(self):
        standard = transform_raw_to_standard(parse_cmg(MXDRM005))
        if TMP_DIR.exists():
            _safe_rmtree(TMP_DIR)
        TMP_DIR.mkdir(parents=True, exist_ok=True)

        out = TMP_DIR / "mxdrm005_roundtrip.dat"
        content = generate_cmg(standard, output_file=out)

        self.assertTrue(out.exists())
        self.assertTrue((TMP_DIR / "mxdrm005.sip").exists())
        self.assertIn("FILENAMES SIPDATA-IN 'mxdrm005.sip'", content)
        self.assertIn("POR SIP_DATA", content)
        self.assertIn("PERMI SIP_DATA", content)

    def test_structured_backend_can_write_supported_ref_values(self):
        standard = transform_raw_to_standard(parse_cmg(MXDRM005))
        standard["meta"] = {
            **standard.get("meta", {}),
            "source_software": "petrel_eclipse",
            "_cmg_roundtrip_mode": "structured",
        }
        standard["meta"].pop("_cmg_raw_deck_lines", None)
        standard["meta"].pop("_cmg_source_dir", None)
        standard["meta"].pop("_cmg_case_dependencies", None)

        preflight = evaluate_target_preflight(standard, target="cmg")
        self.assertTrue(preflight["ok"], msg=str(preflight))

        if TMP_DIR.exists():
            _safe_rmtree(TMP_DIR)
        TMP_DIR.mkdir(parents=True, exist_ok=True)

        out = TMP_DIR / "mxdrm005_structured.dat"
        content = generate_cmg(standard, output_file=out)

        self.assertTrue(out.exists())
        self.assertTrue((TMP_DIR / "mxdrm005.sip").exists())
        self.assertIn("FILENAMES SIPDATA-IN 'mxdrm005.sip'", content)
        self.assertIn("*POR SIP_DATA", content)
        self.assertIn("*PERMI SIP_DATA", content)
        self.assertIn("*PERMJ *EQUALSI", content)


if __name__ == "__main__":
    unittest.main()
