from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict

from infra.case_dependencies import collect_case_input_files


def _runtime_alias_candidates(ref: str, item: Dict[str, Any] | None = None) -> list[Path]:
    ref_path = Path(ref)
    candidates: list[Path] = []
    producer_artifact = item.get("producer_artifact") if isinstance(item, dict) else None
    if producer_artifact:
        candidates.append(Path(producer_artifact))
    if ref_path.suffix:
        default_candidate = ref_path.with_name(f"{ref_path.stem}_converted{ref_path.suffix}")
        if default_candidate not in candidates:
            candidates.append(default_candidate)
    return candidates


def materialize_case_input_files(data: Dict[str, Any] | None, output_file: str | Path | None) -> Dict[str, list[Any]]:
    summary: Dict[str, list[Any]] = {
        "copied": [],
        "aliased": [],
        "existing": [],
        "missing": [],
        "resolved_paths": [],
    }
    if not isinstance(data, dict) or not output_file:
        return summary

    dst_root = Path(output_file).parent
    input_items = collect_case_input_files(data)
    if not input_items:
        return summary

    for item in input_items:
        ref = item.get("path")
        if not ref:
            continue
        ref_path = Path(ref)
        dst_path = dst_root / ref_path
        if dst_path.exists():
            summary["existing"].append(ref)
            summary["resolved_paths"].append(ref)
            continue

        src_path = Path(item.get("source_path") or ref)
        if src_path.exists():
            if str(src_path.resolve()) == str(dst_path.resolve()):
                summary["existing"].append(ref)
                summary["resolved_paths"].append(ref)
                continue
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)
            summary["copied"].append({"path": ref, "source": str(src_path)})
            summary["resolved_paths"].append(ref)
            continue

        aliased = False
        for candidate_rel in _runtime_alias_candidates(ref, item):
            candidate_path = dst_root / candidate_rel
            if not candidate_path.exists():
                continue
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate_path, dst_path)
            summary["aliased"].append({"path": ref, "source": candidate_path.name})
            summary["resolved_paths"].append(ref)
            aliased = True
            break

        if aliased:
            continue

        summary["missing"].append(ref)

    return summary
