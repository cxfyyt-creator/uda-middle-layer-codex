import unittest
import shutil
from pathlib import Path

from generators.cmg_generator import generate_cmg
from parsers.cmg_parser import parse_cmg
from transformers import transform_raw_to_standard
from utils.cmg_case_dependencies import scan_cmg_case_dependencies
from utils.project_paths import TMP_TESTS_DIR


ROOT = Path(__file__).resolve().parents[1]
INPUTS_DIR = ROOT / "inputs" / "cmg"
TMP_DIR = TMP_TESTS_DIR / "cmg_source_faithful"


class TestCMGSourceFaithfulRoundtrip(unittest.TestCase):
    def test_mxdrm001_roundtrip_preserves_original_deck(self):
        src = INPUTS_DIR / "mxdrm001.dat"
        raw = parse_cmg(src)
        deps = raw.get("meta", {}).get("_cmg_case_dependencies", {})
        self.assertEqual(deps.get("runtime_inputs", []), [])
        self.assertTrue(deps.get("ignored_lines"))
        standard = transform_raw_to_standard(raw)
        content = generate_cmg(standard)
        expected = src.read_text(encoding="utf-8", errors="ignore")
        self.assertEqual(content, expected)

    def test_mxdrm005_roundtrip_preserves_sip_and_vari_keywords(self):
        src = INPUTS_DIR / "mxdrm005.dat"
        raw = parse_cmg(src)
        deps = raw.get("meta", {}).get("_cmg_case_dependencies", {})
        self.assertEqual([item.get("path") for item in deps.get("runtime_inputs", [])], ["mxdrm005.sip"])
        self.assertEqual(deps.get("missing_runtime_inputs", []), [])
        standard = transform_raw_to_standard(raw)
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        out = TMP_DIR / "mxdrm005_roundtrip.dat"
        content = generate_cmg(standard, output_file=out)
        self.assertTrue((TMP_DIR / "mxdrm005.sip").exists())
        self.assertIn("FILENAMES SIPDATA-IN 'mxdrm005.sip'", content)
        self.assertIn("POR SIP_DATA", content)
        self.assertIn("PERMI SIP_DATA", content)
        self.assertIn("*GRID *VARI 13 14 11", content)

    def test_missing_runtime_dependency_is_blocked(self):
        src = INPUTS_DIR / "mxdrm005.dat"
        tmpdir = TMP_DIR / "missing_runtime_case"
        if tmpdir.exists():
            shutil.rmtree(tmpdir)
        tmpdir.mkdir(parents=True, exist_ok=True)
        dat_copy = tmpdir / "mxdrm005.dat"
        dat_copy.write_text(src.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")

        raw = parse_cmg(dat_copy)
        deps = raw.get("meta", {}).get("_cmg_case_dependencies", {})
        self.assertEqual([item.get("path") for item in deps.get("missing_runtime_inputs", [])], ["mxdrm005.sip"])

        standard = transform_raw_to_standard(raw)
        with self.assertRaisesRegex(ValueError, "missing required CMG runtime input: mxdrm005.sip"):
            generate_cmg(standard, output_file=tmpdir / "mxdrm005_roundtrip.dat")

    def test_scan_detects_flxb_runtime_inputs_but_ignores_commented_lines(self):
        deps = scan_cmg_case_dependencies(
            [
                "** *FLXB-IN 'commented.flxb'",
                "   *FLXB-IN 'active.flxb'   ** trailing comment",
                " *INCLUDE 'child.inc'",
            ],
            source_dir=TMP_DIR,
        )
        self.assertEqual(
            [item.get("path") for item in deps.get("runtime_inputs", [])],
            ["active.flxb", "child.inc"],
        )
        self.assertEqual(
            [item.get("path") for item in deps.get("missing_runtime_inputs", [])],
            ["active.flxb", "child.inc"],
        )

    def test_missing_flxb_dependency_can_be_resolved_from_converted_alias(self):
        src = INPUTS_DIR / "geo" / "mxgeo008.dat"
        raw = parse_cmg(src)
        deps = raw.get("meta", {}).get("_cmg_case_dependencies", {})
        self.assertIn("mxgeo007.flxb", [item.get("path") for item in deps.get("missing_runtime_inputs", [])])

        standard = transform_raw_to_standard(raw)
        tmpdir = TMP_DIR / "geo_flxb_alias_case"
        if tmpdir.exists():
            shutil.rmtree(tmpdir)
        tmpdir.mkdir(parents=True, exist_ok=True)
        (tmpdir / "mxgeo007_converted.flxb").write_text("dummy flux boundary", encoding="utf-8")

        out = tmpdir / "mxgeo008_converted.dat"
        generate_cmg(standard, output_file=out)

        self.assertTrue(out.exists())
        self.assertTrue((tmpdir / "mxgeo007.flxb").exists())


if __name__ == "__main__":
    unittest.main()
