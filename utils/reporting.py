from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_stem(name: str) -> str:
    p = Path(str(name))
    return p.stem or "report"


def write_report_bundle(
    report_dir: str | Path,
    source_name: str,
    report_type: str,
    title: str,
    summary_items: Iterable[Tuple[str, Any]],
    warnings: List[str] | None = None,
    errors: List[str] | None = None,
    details: Dict[str, Any] | None = None,
) -> Tuple[Path, Path]:
    """写出人类可读 Markdown + 机器可读 JSON 报告。"""
    out_dir = Path(report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = _safe_stem(source_name)
    md_path = out_dir / f"{stem}.{report_type}.report.md"
    json_path = out_dir / f"{stem}.{report_type}.report.json"

    warnings = warnings or []
    errors = errors or []
    details = details or {}

    payload = {
        "title": title,
        "report_type": report_type,
        "source_name": str(source_name),
        "created_at": _now(),
        "summary": [{"name": k, "value": v} for k, v in summary_items],
        "warnings": warnings,
        "errors": errors,
        "details": details,
    }

    lines: List[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- 生成时间: {payload['created_at']}")
    lines.append(f"- 源文件: {source_name}")
    lines.append(f"- 报告类型: {report_type}")
    lines.append("")

    lines.append("## 概览")
    for k, v in summary_items:
        lines.append(f"- {k}: {v}")
    lines.append("")

    lines.append("## 警告")
    if warnings:
        for w in warnings:
            lines.append(f"- {w}")
    else:
        lines.append("- 无")
    lines.append("")

    lines.append("## 错误")
    if errors:
        for e in errors:
            lines.append(f"- {e}")
    else:
        lines.append("- 无")
    lines.append("")

    lines.append("## 详细信息")
    if details:
        lines.append("```json")
        lines.append(json.dumps(details, ensure_ascii=False, indent=2))
        lines.append("```")
    else:
        lines.append("- 无")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return md_path, json_path
