import unittest
from datetime import datetime
from pathlib import Path

from target_writers.cmg import generate_cmg
from source_readers.cmg import parse_cmg
from standardizers import build_standard_ir
from target_mappers.cmg import build_cmg_target_ir
from infra.project_paths import TMP_TESTS_DIR
from checks import validate_standard_model


ROOT = Path(__file__).resolve().parents[1]
INPUTS_DIR = ROOT / "inputs" / "cmg" / "IMEX" / "spe"
TMP_ROOT = TMP_TESTS_DIR / "cmg_regression" / datetime.now().strftime("run_%Y%m%d_%H%M%S_%f")


CASES = {
    "mxspe001.dat": {"wells": 2, "pvt_rows": 10},
    "mxspe002.dat": {"wells": 1, "pvt_rows": 14},
    "mxspe005.dat": {"wells": 3, "pvt_rows": 14, "pvts_rows": 14, "must_contain": ["*PERMJ *EQUALSI"]},
    "mxspe009.dat": {"wells": 26, "zg_rows": 12, "must_contain": ["*PERMJ *EQUALSI", "*PERMK *EQUALSI * 0.01"]},
    "mxspe010.dat": {"wells": 2, "pvt_rows": 2, "slt_rows": 35},
}


class TestCMGInputsRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)

    def test_inputs_cmg_parse_transform_generate(self):
        for filename, expected in CASES.items():
            with self.subTest(filename=filename):
                src = INPUTS_DIR / filename
                tmpdir = TMP_ROOT / src.stem
                tmpdir.mkdir(parents=True, exist_ok=True)

                raw = parse_cmg(src, report_dir=tmpdir / "reports" / "parsers")
                self.assertFalse(raw.get("unknown_keywords"), f"{filename} still has unknown keywords")
                self.assertFalse(raw.get("unparsed_blocks"), f"{filename} still has unparsed blocks")

                standard = build_standard_ir(raw)
                validate_standard_model(standard, strict=True)
                cmg_target = build_cmg_target_ir(standard)

                self.assertEqual(len(standard.get("wells", [])), expected["wells"])

                fluid = cmg_target.get("fluid", {})
                rockfluid = cmg_target.get("rockfluid", {})

                if "pvt_rows" in expected:
                    self.assertEqual(len(fluid.get("pvt_table", {}).get("rows", [])), expected["pvt_rows"])
                if "pvts_rows" in expected:
                    self.assertEqual(len(fluid.get("pvts_table", {}).get("rows", [])), expected["pvts_rows"])
                if "zg_rows" in expected:
                    self.assertEqual(len(fluid.get("zg_table", {}).get("rows", [])), expected["zg_rows"])
                if "slt_rows" in expected:
                    self.assertEqual(len(rockfluid.get("slt_table", {}).get("rows", [])), expected["slt_rows"])

                out = tmpdir / f"{src.stem}_roundtrip.dat"
                content = generate_cmg(
                    standard,
                    output_file=out,
                    report_dir=tmpdir / "reports" / "generators",
                )
                self.assertTrue(out.exists(), f"{filename} did not produce roundtrip dat")
                self.assertIn("*MODEL", content)
                for marker in expected.get("must_contain", []):
                    self.assertIn(marker, content, f"{filename} missing marker: {marker}")


if __name__ == "__main__":
    unittest.main()
