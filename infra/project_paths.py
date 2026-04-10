from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Unified output root
OUTPUT_DIR = PROJECT_ROOT / "output"

# Generated files
GENERATED_DIR = OUTPUT_DIR / "generated"
JSON_OUTPUT_DIR = GENERATED_DIR / "json"
CMG_OUTPUT_DIR = GENERATED_DIR / "cmg"
PETREL_OUTPUT_DIR = GENERATED_DIR / "petrel"
REPORTS_DIR = GENERATED_DIR / "reports"
PARSER_REPORTS_DIR = REPORTS_DIR / "source_readers"
GENERATOR_REPORTS_DIR = REPORTS_DIR / "target_writers"

# User-facing deliveries and temporary test products
DELIVERABLES_DIR = OUTPUT_DIR / "deliverables"
TMP_TESTS_DIR = OUTPUT_DIR / "tmp_tests"
