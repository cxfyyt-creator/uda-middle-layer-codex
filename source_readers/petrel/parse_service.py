from __future__ import annotations

import json
from pathlib import Path

from infra.project_paths import PARSER_REPORTS_DIR
from infra.reporting import write_report_bundle
from source_readers.petrel.reader_pipeline import PetrelParser


def parse_petrel(filepath, output_json=None, report_dir=PARSER_REPORTS_DIR):
    r = PetrelParser(filepath).parse()
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
        ("井数量", len(r.get("wells", []))),
        ("PVTO 行数", len(r.get("fluid", {}).get("pvto_table", {}).get("rows", []))),
        ("PVDG 行数", len(r.get("fluid", {}).get("pvdg_table", {}).get("rows", []))),
        ("未知关键字数", len(unknown)),
        ("累计模拟天数", f"{r.get('_total_sim_time', 0.0):.2f}"),
    ]

    md_path, json_path = write_report_bundle(
        report_dir=report_dir,
        source_name=Path(filepath).name,
        report_type="parse_petrel",
        title="Petrel 解析报告",
        summary_items=summary,
        warnings=warnings,
        errors=[],
        details={
            "unknown_keywords": unknown,
            "start_date": r.get("meta", {}).get("start_date"),
            "unit_system": r.get("meta", {}).get("unit_system"),
        },
    )
    r["_parse_report"] = {"md": str(md_path), "json": str(json_path)}
    return r
