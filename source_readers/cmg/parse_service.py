from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from infra.project_paths import PARSER_REPORTS_DIR
from infra.reporting import write_report_bundle
from source_readers.cmg.reader_pipeline import CMGParser


def parse_cmg(filepath, output_json=None, report_dir=PARSER_REPORTS_DIR):
    r = CMGParser(filepath).parse()
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(r, f, indent=2, ensure_ascii=False)

    unknown = r.get("unknown_keywords", {}) or {}
    warnings = []
    if unknown:
        warnings.append(f"存在未注册关键字 {len(unknown)} 个，请补充 keyword_registry.yaml")

    summary = [
        ("网格", f"{r.get('grid', {}).get('ni')} x {r.get('grid', {}).get('nj')} x {r.get('grid', {}).get('nk')}"),
        ("K层方向", r.get("grid", {}).get("kdir", "(未指定，CMG默认)")),
        ("井数量", len(r.get("wells", []))),
        ("PVT 行数", len(r.get("fluid", {}).get("pvt_table", {}).get("rows", []))),
        ("SWT 行数", len(r.get("rockfluid", {}).get("swt_table", {}).get("rows", []))),
        ("未知关键字数", len(unknown)),
        ("运行依赖文件", len((r.get("meta", {}).get("_cmg_case_dependencies", {}) or {}).get("runtime_inputs", []))),
    ]

    md_path, json_path = write_report_bundle(
        report_dir=report_dir,
        source_name=Path(filepath).name,
        report_type="parse_cmg",
        title="CMG 解析报告",
        summary_items=summary,
        warnings=warnings,
        errors=[],
        details={
            "unknown_keywords": unknown,
            "start_date": r.get("meta", {}).get("start_date"),
            "unit_system": r.get("meta", {}).get("unit_system"),
            "kdir": r.get("grid", {}).get("kdir"),
            "case_dependencies": r.get("meta", {}).get("_cmg_case_dependencies", {}),
        },
    )
    r["_parse_report"] = {"md": str(md_path), "json": str(json_path)}
    return r
