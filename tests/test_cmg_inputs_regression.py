import unittest
from datetime import datetime
from pathlib import Path

from generators.cmg_generator import generate_cmg
from parsers.cmg_parser import parse_cmg
from transformers import transform_raw_to_standard
from validators import validate_standard_model


ROOT = Path(__file__).resolve().parents[1]
INPUTS_DIR = ROOT / "inputs" / "cmg"
TMP_ROOT = ROOT / ".tmp_tests" / "cmg_regression" / datetime.now().strftime("run_%Y%m%d_%H%M%S_%f")


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

                standard = transform_raw_to_standard(raw)
                validate_standard_model(standard, strict=True)

                self.assertEqual(len(standard.get("wells", [])), expected["wells"])

                fluid = standard.get("fluid", {})
                rockfluid = standard.get("rockfluid", {})

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
