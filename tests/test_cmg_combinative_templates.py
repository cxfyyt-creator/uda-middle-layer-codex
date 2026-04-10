import unittest
from datetime import datetime
from pathlib import Path
import re

from target_writers.cmg import generate_cmg
from source_readers.cmg import parse_cmg
from standardizers import build_standard_ir
from infra.project_paths import TMP_TESTS_DIR


ROOT = Path(__file__).resolve().parents[1]
INPUTS_DIR = ROOT / "inputs" / "cmg" / "IMEX" / "cmb"
TMP_ROOT = TMP_TESTS_DIR / "cmg_combinative" / datetime.now().strftime("run_%Y%m%d_%H%M%S_%f")


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

                standard = build_standard_ir(raw)
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
