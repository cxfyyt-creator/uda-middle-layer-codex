import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from target_writers.cmg.writer_pipeline import CMGWriter
else:
    from .writer_pipeline import CMGWriter

from infra.case_dependencies import collect_case_input_files, collect_case_output_files
from infra.case_materialization import materialize_case_input_files
from checks.readiness import (
    append_capped_prefixed_warnings,
    run_generation_gate,
    write_generation_report,
)
from infra.ir_normalization import normalize_ir_refs
from infra.project_paths import CMG_OUTPUT_DIR, GENERATOR_REPORTS_DIR, JSON_OUTPUT_DIR
from standardizers import normalize_standard_ir
from target_mappers.cmg import build_cmg_target_ir


def generate_cmg(data_or_json, output_file=None, report_dir=GENERATOR_REPORTS_DIR):
    source_name = str(data_or_json) if isinstance(data_or_json, (str, Path)) else "in_memory_json"
    if isinstance(data_or_json, (str, Path)):
        with open(data_or_json, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = data_or_json
    data = normalize_ir_refs(data)
    data = normalize_standard_ir(data)
    data = build_cmg_target_ir(data)
    writer = CMGWriter()
    out_path = Path(output_file) if output_file else None
    runtime_resolution = {
        "copied": [],
        "aliased": [],
        "existing": [],
        "missing": [],
        "resolved_paths": [],
    }
    if out_path and isinstance(data, dict):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_resolution = materialize_case_input_files(data, out_path)

    resolved_runtime_paths = set(runtime_resolution.get("resolved_paths", []))

    def _runtime_path_from_blocker(text):
        prefix = "missing required CMG runtime input: "
        raw = str(text)
        if not raw.startswith(prefix):
            return None
        path = raw[len(prefix):]
        if " (" in path:
            path = path.split(" (", 1)[0]
        return path

    def _filter_preflight_blockers(preflight):
        effective_blockers = []
        for item in preflight.get("issues", []):
            if item.get("severity") != "blocker":
                continue
            message = str(item.get("message", ""))
            runtime_path = _runtime_path_from_blocker(message)
            if runtime_path and runtime_path in resolved_runtime_paths:
                continue
            effective_blockers.append(message)
        return effective_blockers

    gate = run_generation_gate(
        data,
        target="cmg",
        target_label="CMG",
        source_name=source_name,
        report_dir=report_dir,
        report_type="generate_cmg",
        title="CMG generation report",
        failed_summary_items=[
            ("output_file", "(not written)"),
            ("line_count", 0),
            ("well_count", len(data.get("wells", [])) if isinstance(data, dict) else 0),
            ("grid_type", data.get("grid", {}).get("grid_type", "unknown") if isinstance(data, dict) else "unknown"),
        ],
        failure_details={"runtime_resolution": runtime_resolution},
        preflight_blocker_filter=_filter_preflight_blockers,
    )
    preflight = gate["preflight"]
    confidence_check = gate["confidence_check"]

    content = writer.generate(data)

    if output_file:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
    warnings = []
    wells = data.get("wells", []) if isinstance(data, dict) else []
    meta = data.get("meta", {}) if isinstance(data, dict) else {}
    deps = meta.get("_cmg_case_dependencies", {}) if isinstance(meta, dict) else {}
    case_manifest = data.get("case_manifest", {}) if isinstance(data, dict) else {}
    if not wells:
        warnings.append("no wells found; WELL DATA section may be empty")
    runtime_inputs = collect_case_input_files(data) if isinstance(data, dict) else []
    runtime_outputs = collect_case_output_files(data) if isinstance(data, dict) else []
    missing_runtime = [item for item in runtime_inputs if item.get("exists") is False]
    if runtime_resolution["resolved_paths"]:
        resolved = set(runtime_resolution["resolved_paths"])
        missing_runtime = [item for item in missing_runtime if item.get("path") not in resolved]
    if runtime_inputs:
        warnings.append(f"cmg case runtime inputs detected: {len(runtime_inputs)}")
    if runtime_outputs:
        warnings.append(f"cmg case runtime outputs declared: {len(runtime_outputs)}")
    if runtime_resolution["copied"]:
        warnings.append(f"copied runtime inputs: {len(runtime_resolution['copied'])}")
    if runtime_resolution["aliased"]:
        warnings.append(f"created runtime aliases: {len(runtime_resolution['aliased'])}")
    for item in missing_runtime:
        warnings.append(f"missing cmg runtime input: {item.get('path')}")
    append_capped_prefixed_warnings(warnings, prefix="preflight", items=list(preflight["warnings"]))
    append_capped_prefixed_warnings(warnings, prefix="low confidence", items=list(confidence_check["warnings"]))

    summary = [
        ("output_file", str(out_path) if out_path else "(not written)"),
        ("line_count", len(content.splitlines())),
        ("well_count", len(wells)),
        ("grid_type", data.get("grid", {}).get("grid_type", "CART") if isinstance(data, dict) else "unknown"),
    ]
    write_generation_report(
        data,
        report_dir=report_dir,
        source_name=source_name,
        report_type="generate_cmg",
        title="CMG generation report",
        summary_items=summary,
        warnings=warnings,
        errors=[],
        details={
            "has_pvto_table": bool(data.get("fluid", {}).get("pvto_table")) if isinstance(data, dict) else False,
            "has_pvdg_table": bool(data.get("fluid", {}).get("pvdg_table")) if isinstance(data, dict) else False,
            "has_pvt_table": bool(data.get("fluid", {}).get("pvt_table")) if isinstance(data, dict) else False,
            "case_manifest": case_manifest if isinstance(data, dict) else {},
            "case_dependencies": deps if isinstance(data, dict) else {},
            "runtime_outputs": runtime_outputs,
            "runtime_resolution": runtime_resolution,
            "preflight": preflight,
            "confidence_check": confidence_check,
        },
    )
    return content


if __name__ == "__main__":
    default_json = JSON_OUTPUT_DIR / "SPE2_CHAP_parsed.json"
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else default_json
    out_dir = CMG_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(src).stem.replace("_parsed", "")
    out = out_dir / f"{stem}_converted.dat"
    generate_cmg(src, str(out))
    print(f"CMG file written: {out}")
