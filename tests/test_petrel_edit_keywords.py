import shutil
import unittest
from pathlib import Path
from textwrap import dedent
from uuid import uuid4

from infra.project_paths import TMP_TESTS_DIR
from source_readers.petrel import parse_petrel


class TestPetrelEditKeywords(unittest.TestCase):
    def _parse_text(self, text, name="case.DATA"):
        tmpdir = TMP_TESTS_DIR / f"petrel_edit_{uuid4().hex}"
        tmpdir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(tmpdir, ignore_errors=True))
        src = tmpdir / name
        src.write_text(dedent(text).strip() + "\n", encoding="utf-8")
        return parse_petrel(src)

    def test_unquoted_equals_copy_multiply(self):
        raw = self._parse_text(
            """
            RUNSPEC
            DIMENS
            13 1 1 /
            GRID
            EQUALS
            TOPS 6100 1 13 1 1 1 1 /
            PORO 0.18 1 13 1 1 1 1 /
            NTG 1.00 1 13 1 1 1 1 /
            DZ 32 1 13 1 1 1 1 /
            PERMX 500 1 13 1 1 1 1 /
            /
            COPY
            PERMX PERMY /
            PERMX PERMZ /
            /
            MULTIPLY
            PERMZ 0.2 1 13 1 1 1 1 /
            /
            END
            """
        )

        self.assertEqual(raw["grid"]["tops_ref"]["type"], "scalar")
        self.assertAlmostEqual(raw["grid"]["tops_ref"]["value"], 6100.0)
        self.assertAlmostEqual(raw["grid"]["dk"]["value"], 32.0)
        self.assertAlmostEqual(raw["reservoir"]["porosity"]["value"], 0.18)
        self.assertAlmostEqual(raw["reservoir"]["ntg"]["value"], 1.0)
        self.assertAlmostEqual(raw["reservoir"]["perm_i"]["value"], 500.0)
        self.assertAlmostEqual(raw["reservoir"]["perm_j"]["value"], 500.0)
        self.assertAlmostEqual(raw["reservoir"]["perm_k"]["value"], 100.0)

    def test_equals_inherits_previous_box(self):
        raw = self._parse_text(
            """
            RUNSPEC
            DIMENS
            2 1 3 /
            GRID
            EQUALS
            DZ 10 1 2 1 1 1 1 /
            PORO 0.10 /
            DZ 20 1 2 1 1 2 2 /
            PORO 0.20 /
            DZ 30 1 2 1 1 3 3 /
            PORO 0.30 /
            /
            END
            """
        )

        self.assertEqual(raw["grid"]["dk"]["type"], "array")
        self.assertEqual(raw["grid"]["dk"]["values"], [10.0, 20.0, 30.0])
        self.assertEqual(raw["reservoir"]["porosity"]["type"], "array")
        self.assertEqual(raw["reservoir"]["porosity"]["values"], [0.1, 0.2, 0.3])

    def test_copy_and_multiply_full_layer_subrange(self):
        raw = self._parse_text(
            """
            RUNSPEC
            DIMENS
            1 1 3 /
            GRID
            EQUALS
            PERMX 100 1 1 1 1 1 3 /
            PERMZ 10 1 1 1 1 1 3 /
            /
            COPY
            PERMX PERMZ 1 1 1 1 2 3 /
            /
            MULTIPLY
            PERMZ 0.5 1 1 1 1 3 3 /
            /
            END
            """
        )

        self.assertEqual(raw["reservoir"]["perm_k"]["type"], "array")
        self.assertEqual(raw["reservoir"]["perm_k"]["values"], [10.0, 100.0, 50.0])


if __name__ == "__main__":
    unittest.main()
