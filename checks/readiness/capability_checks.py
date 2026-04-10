from __future__ import annotations

from typing import Any, Dict, List

from infra.case_dependencies import collect_case_input_files


def _iter_ref_paths(obj: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        if obj.get("type") == "ref":
            found.append(prefix or "<root>")
        for key, value in obj.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            found.extend(_iter_ref_paths(value, child))
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            child = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            found.extend(_iter_ref_paths(value, child))
    return found


def _get_nested_value(data: Any, path: str) -> Any:
    current = data
    token = ""
    i = 0
    while i < len(path):
        ch = path[i]
        if ch == ".":
            if token:
                if not isinstance(current, dict):
                    return None
                current = current.get(token)
                token = ""
            i += 1
            continue
        if ch == "[":
            if token:
                if not isinstance(current, dict):
                    return None
                current = current.get(token)
                token = ""
            end = path.find("]", i)
            if end < 0:
                return None
            if not isinstance(current, list):
                return None
            try:
                current = current[int(path[i + 1:end])]
            except (ValueError, IndexError):
                return None
            i = end + 1
            continue
        token += ch
        i += 1

    if token:
        if not isinstance(current, dict):
            return None
        current = current.get(token)
    return current


def _is_supported_cmg_ref(obj: Any) -> bool:
    if not isinstance(obj, dict) or obj.get("type") != "ref":
        return False

    hint = obj.get("source_format_hint") or {}
    if str(hint.get("keyword", "")).upper() == "*EQUALSI":
        return True

    ref_format = str(obj.get("format", "")).upper()
    return ref_format in {"SIP_DATA", "BINARY_DATA"}


def check_schedule_support(data: Dict[str, Any], blockers: List[str], warnings: List[str], *, target: str) -> None:
    timeline_events = data.get("timeline_events", []) or []
    if not timeline_events:
        return

    if target == "cmg":
        supported_targets = {"RATE", "ORAT", "WRAT", "GRAT", "ORATE", "WRATE", "GRATE", "STO", "STG", "STW", "BHP"}
        approximation_counts: Dict[str, int] = {}
        for idx, event in enumerate(timeline_events):
            target_name = str(event.get("target") or "RATE").upper()
            if target_name not in supported_targets:
                blockers.append(f"timeline_events[{idx}] target={target_name} is not supported by current CMG backend")
            if target_name in {"BHP", "ORAT", "WRAT", "GRAT", "ORATE", "WRATE", "GRATE"}:
                approximation_counts[target_name] = approximation_counts.get(target_name, 0) + 1
        for target_name, count in sorted(approximation_counts.items()):
            warnings.append(f"{count} timeline events with target={target_name} will be mapped to current CMG ALTER schedule backend")

    if target == "petrel":
        for idx, event in enumerate(timeline_events):
            if event.get("event_type") != "WELL_TARGET_CHANGE":
                warnings.append(f"timeline_events[{idx}] may not be exported cleanly to Petrel")


def check_case_runtime_dependencies(data: Dict[str, Any], blockers: List[str], warnings: List[str], *, target: str) -> None:
    if target != "cmg":
        return

    inputs = collect_case_input_files(data)
    if inputs:
        warnings.append(f"cmg case inputs detected: {len(inputs)}")

    for item in inputs:
        if item.get("exists") is False and item.get("required", True):
            path = item.get("path") or item.get("source_path") or "<unknown>"
            producer_case = item.get("producer_case")
            producer_artifact = item.get("producer_artifact")
            if producer_case or producer_artifact:
                detail = []
                if producer_case:
                    detail.append(f"upstream case {producer_case}")
                if producer_artifact:
                    detail.append(f"expected artifact {producer_artifact}")
                blockers.append(f"missing required CMG runtime input: {path} ({', '.join(detail)})")
            else:
                blockers.append(f"missing required CMG runtime input: {path}")


def check_ref_support(data: Dict[str, Any], blockers: List[str], warnings: List[str], *, target: str) -> None:
    ref_paths = _iter_ref_paths(data)
    if not ref_paths:
        return

    warnings.append(f"ir ref values detected: {len(ref_paths)}")

    if target == "cmg":
        unsupported: list[str] = []
        for path in ref_paths:
            obj = _get_nested_value(data, path)
            if not _is_supported_cmg_ref(obj):
                unsupported.append(path)
        if not unsupported:
            return
        ref_paths = unsupported

    sample = ", ".join(ref_paths[:5])
    blockers.append(
        "structured backend does not yet support ref values: "
        + sample
        + (f" (+{len(ref_paths) - 5} more)" if len(ref_paths) > 5 else "")
    )
