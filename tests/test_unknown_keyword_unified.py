import shutil
import unittest
from pathlib import Path
from textwrap import dedent
from uuid import uuid4

from infra.project_paths import TMP_TESTS_DIR
from source_readers.cmg import parse_cmg
from source_readers.petrel import parse_petrel


class TestUnknownKeywordUnified(unittest.TestCase):
    def _tmp_file(self, text: str, name: str) -> Path:
        tmpdir = TMP_TESTS_DIR / f"unknown_kw_{uuid4().hex}"
        tmpdir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(tmpdir, ignore_errors=True))
        src = tmpdir / name
        src.write_text(dedent(text).strip() + "\n", encoding="utf-8")
        return src

    def test_petrel_unknown_keyword_records_structured_payload(self):
        src = self._tmp_file(
            """
            RUNSPEC
            DIMENS
            1 1 1 /
            GRID
            FOO
            1 2 3 /
            END
            """,
            "case.DATA",
        )

        raw = parse_petrel(src)

        self.assertIn("FOO", raw["unknown_keywords"])
        entry = raw["unknown_keywords"]["FOO"][0]
        self.assertEqual(entry["source"], "petrel")
        self.assertEqual(entry["line"], 5)
        self.assertIn("FOO", entry["raw_content"])
        self.assertEqual(entry["values"], [1.0, 2.0, 3.0])

        block = raw["unparsed_blocks"][0]
        self.assertEqual(block["source"], "petrel")
        self.assertEqual(block["keyword"], "FOO")

    def test_cmg_unknown_keyword_records_structured_payload(self):
        src = self._tmp_file(
            """
            *GRID *CART 1 1 1
            *FOO 1 2 3
            *POR *CON 0.2
            """,
            "case.dat",
        )

        raw = parse_cmg(src)

        self.assertIn("*FOO", raw["unknown_keywords"])
        entry = raw["unknown_keywords"]["*FOO"][0]
        self.assertEqual(entry["source"], "cmg")
        self.assertEqual(entry["line"], 2)
        self.assertIn("*FOO", entry["raw_content"])

        block = raw["unparsed_blocks"][0]
        self.assertEqual(block["source"], "cmg")
        self.assertEqual(block["keyword"], "*FOO")
        self.assertIn("*FOO", block["raw_content"])


if __name__ == "__main__":
    unittest.main()
