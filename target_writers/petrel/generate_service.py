import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from target_writers.petrel.writer_pipeline import PetrelWriter
else:
    from .writer_pipeline import PetrelWriter

from checks.readiness import append_capped_prefixed_warnings, run_generation_gate, write_generation_report
from infra.ir_normalization import normalize_ir_refs
from infra.project_paths import GENERATOR_REPORTS_DIR, JSON_OUTPUT_DIR, PETREL_OUTPUT_DIR
from standardizers import normalize_standard_ir
from target_mappers.petrel import build_petrel_target_ir


def generate_petrel(data_or_json, output_file=None, report_dir=GENERATOR_REPORTS_DIR):
    source_name = str(data_or_json) if isinstance(data_or_json, (str, Path)) else "in_memory_json"
    if isinstance(data_or_json, (str, Path)):
        with open(data_or_json, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = data_or_json
    data = normalize_ir_refs(data)
    data = normalize_standard_ir(data)
    data = build_petrel_target_ir(data)
    gate = run_generation_gate(
        data,
        target="petrel",
        target_label="Petrel",
        source_name=source_name,
        report_dir=report_dir,
        report_type="generate_petrel",
        title="Petrel generation report",
        failed_summary_items=[
            ("output_file", "(not written)"),
            ("line_count", 0),
            ("well_count", len(data.get("wells", []))),
            ("grid_type", data.get("grid", {}).get("grid_type", "unknown")),
        ],
    )
    preflight = gate["preflight"]
    confidence_check = gate["confidence_check"]
    content = PetrelWriter().generate(data)
    out_path = None
    if output_file:
        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
    warnings = []
    if not data.get("wells"):
        warnings.append("no wells found; SCHEDULE may contain only static content")
    append_capped_prefixed_warnings(warnings, prefix="preflight", items=list(preflight["warnings"]))
    append_capped_prefixed_warnings(warnings, prefix="low confidence", items=list(confidence_check["warnings"]))
    summary = [
        ("output_file", str(out_path) if out_path else "(not written)"),
        ("line_count", len(content.splitlines())),
        ("well_count", len(data.get("wells", []))),
        ("grid_type", data.get("grid", {}).get("grid_type", "CART")),
    ]
    write_generation_report(
        data,
        report_dir=report_dir,
        source_name=source_name,
        report_type="generate_petrel",
        title="Petrel generation report",
        summary_items=summary,
        warnings=warnings,
        errors=[],
        details={
            "has_swof": bool(data.get("rockfluid", {}).get("swof_table")),
            "has_sgof": bool(data.get("rockfluid", {}).get("sgof_table")),
            "has_swt": bool(data.get("rockfluid", {}).get("swt_table")),
            "has_slt": bool(data.get("rockfluid", {}).get("slt_table")),
            "preflight": preflight,
            "confidence_check": confidence_check,
        },
    )
    return content


if __name__ == "__main__":
    default_json = JSON_OUTPUT_DIR / "mxspe001_parsed.json"
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else default_json
    out_dir = PETREL_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(src).stem.replace("_parsed", "")
    out = out_dir / f"{stem}_converted.DATA"
    generate_petrel(src, str(out))
    print(f"Petrel file written: {out}")
