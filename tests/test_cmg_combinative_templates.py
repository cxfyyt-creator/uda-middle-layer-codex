import unittest
from datetime import datetime
from pathlib import Path
import re

from generators.cmg_generator import generate_cmg
from parsers.cmg_parser import parse_cmg
from transformers import transform_raw_to_standard


ROOT = Path(__file__).resolve().parents[1]
INPUTS_DIR = ROOT / "inputs" / "cmg"
TMP_ROOT = ROOT / ".tmp_tests" / "cmg_combinative" / datetime.now().strftime("run_%Y%m%d_%H%M%S_%f")


CASES = {
    "mxcmb001.dat": [
        "*NORM *PRESS 1000.0",
        "*AIM *THRESH 0.25 .25",
        "*SOLVER PARASOL",
        "*PNTHRDS 1",
        "*COMBINATIVE ON",
    ],
    "mxcmb003.dat": [
        "*MAXCHANGE *SATUR 0.10",
        "*PRECC 0.001",
        "*SOLVER PARASOL",
        "*FGMRES OFF",
        "*COMB-DRS ALL 0.0",
        "*AMG-ITERMAX 1",
        "*AMG-SMOOTHER GS 2",
    ],
    "mxcmb004.dat": [
        "*MAXCHANGE *SATUR 0.10",
        "*PRECC 0.001",
        "*SOLVER PARASOL",
        "*COMB-DRS *RSCAL",
        "*AMG-SETUP-FREQ STRUCTURE",
        "*AMG-EPS 0.5",
        "*AMG-KRYLOV F-GMRES",
        "*AMG-SMOOTHER JACOBI 1 0.5",
    ],
}


class TestCMGCombinativeTemplates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)

    def test_combinative_directives_roundtrip(self):
        for filename, markers in CASES.items():
            with self.subTest(filename=filename):
                src = INPUTS_DIR / filename
                tmpdir = TMP_ROOT / src.stem
                tmpdir.mkdir(parents=True, exist_ok=True)

                raw = parse_cmg(src, report_dir=tmpdir / "reports" / "parsers")
                self.assertFalse(raw.get("unknown_keywords"), f"{filename} still has unknown keywords")
                self.assertFalse(raw.get("unparsed_blocks"), f"{filename} still has unparsed blocks")

                standard = transform_raw_to_standard(raw)
                out = tmpdir / f"{src.stem}_roundtrip.dat"
                content = generate_cmg(
                    standard,
                    output_file=out,
                    report_dir=tmpdir / "reports" / "generators",
                )

                self.assertTrue(out.exists(), f"{filename} did not produce roundtrip dat")
                normalized_content = re.sub(r"\s+", " ", content)
                for marker in markers:
                    normalized_marker = re.sub(r"\s+", " ", marker)
                    self.assertIn(normalized_marker, normalized_content, f"{filename} missing marker: {marker}")


if __name__ == "__main__":
    unittest.main()
