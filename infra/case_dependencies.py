from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List


_RUNTIME_PATTERNS = [
    ("SIPDATA-IN", re.compile(r"(?i)\bSIPDATA-IN\b\s+['\"]([^'\"]+)['\"]")),
    ("BINDATA-IN", re.compile(r"(?i)\bBINDATA-IN\b\s+[\'\"]([^\'\"]+)[\'\"]")),
    ("*FLXB-IN", re.compile(r"(?i)\*FLXB-IN\b\s+['\"]([^'\"]+)['\"]")),
    ("FLXB-IN", re.compile(r"(?i)\bFLXB-IN\b\s+['\"]([^'\"]+)['\"]")),
    ("*INCLUDE", re.compile(r"(?i)\*INCLUDE\s+['\"]([^'\"]+)['\"]")),
    ("INCLUDE", re.compile(r"(?i)\bINCLUDE\b\s+['\"]([^'\"]+)['\"]")),
]

_RUNTIME_OUTPUT_PATTERNS = [
    ("*FLXB-OUT", re.compile(r"(?i)\*FLXB-OUT\b")),
    ("FLXB-OUT", re.compile(r"(?i)\bFLXB-OUT\b")),
]

_NON_RUNTIME_HINTS = [
    re.compile(r"(?i)\bFILENAMES\b"),
    re.compile(r"(?i)\*OUTPUT\b"),
    re.compile(r"(?i)\*INDEX-OUT\b"),
    re.compile(r"(?i)\*MAIN-RESULTS-OUT\b"),
    re.compile(r"(?i)\*CASEID\b"),
    re.compile(r"(?i)\*WRST\b"),
]

_STATIC_INPUT_TYPES = {"SIPDATA-IN", "BINDATA-IN", "INCLUDE"}
_RUNTIME_INPUT_TYPES = {"FLXB-IN"}
_DEFAULT_RUNTIME_OUTPUT_SPECS = [
    ("SIM-OUT", ".out", "simulator_text_output"),
    ("SR3-OUT", ".sr3", "simulator_binary_output"),
    ("RSTR-SR3-OUT", ".rstr.sr3", "restart_output"),
]


def _strip_cmg_comments(line: str) -> str:
    text = str(line).rstrip()
    if not text:
        return ""
    idx = text.find("**")
    if idx >= 0:
        text = text[:idx]
    return text.rstrip()


def _normalize_dependency_type(value: str | None) -> str:
    return str(value or "").upper().lstrip("*")


def _normalize_case_item(entry: Dict[str, Any]) -> Dict[str, Any]:
    kind = _normalize_dependency_type(entry.get("type"))
    item = {
        "kind": kind,
        "path": entry.get("path", ""),
        "source_path": entry.get("source_path"),
        "exists": entry.get("exists"),
        "required": bool(entry.get("required_for_runtime", True)),
        "line": entry.get("line"),
    }
    for extra_key in (
        "producer_case",
        "producer_case_source_path",
        "producer_case_exists",
        "producer_artifact",
        "generated_artifact",
        "output_role",
    ):
        if extra_key in entry:
            item[extra_key] = entry.get(extra_key)
    return item


def _infer_runtime_producer(
    dependency_type: str,
    relpath: str,
    source_dir: str | Path | None,
) -> Dict[str, Any]:
    kind = _normalize_dependency_type(dependency_type)
    if kind != "FLXB-IN":
        return {}

    ref_path = Path(relpath)
    stem = ref_path.stem
    producer_case = f"{stem}.dat"
    producer: Dict[str, Any] = {
        "producer_case": producer_case,
        "producer_artifact": f"{stem}_converted{ref_path.suffix}",
    }
    if source_dir is not None:
        producer_case_path = Path(source_dir) / producer_case
        producer["producer_case_source_path"] = str(producer_case_path)
        producer["producer_case_exists"] = producer_case_path.exists()
    return producer


def _infer_runtime_output(
    dependency_type: str,
    *,
    line: int,
    root_file: str | Path | None,
) -> Dict[str, Any] | None:
    kind = _normalize_dependency_type(dependency_type)
    if kind != "FLXB-OUT" or root_file is None:
        return None

    root_path = Path(root_file)
    output_path = f"{root_path.stem}.flxb"
    return {
        "type": dependency_type,
        "path": output_path,
        "line": line,
        "required_for_runtime": False,
        "producer_case": root_path.name,
        "producer_case_source_path": str(root_path),
        "producer_case_exists": root_path.exists(),
        "producer_artifact": f"{root_path.stem}_converted.flxb",
        "generated_artifact": f"{root_path.stem}_converted.flxb",
        "output_role": "runtime_output",
    }


def _default_runtime_outputs(root_file: str | Path | None) -> List[Dict[str, Any]]:
    if root_file is None:
        return []

    root_path = Path(root_file)
    outputs: List[Dict[str, Any]] = []
    for kind, suffix, role in _DEFAULT_RUNTIME_OUTPUT_SPECS:
        outputs.append({
            "type": kind,
            "path": f"{root_path.stem}{suffix}",
            "line": None,
            "required_for_runtime": False,
            "producer_case": root_path.name,
            "producer_case_source_path": str(root_path),
            "producer_case_exists": root_path.exists(),
            "producer_artifact": f"{root_path.stem}_converted{suffix}",
            "generated_artifact": f"{root_path.stem}_converted{suffix}",
            "output_role": role,
        })
    return outputs


def scan_cmg_case_dependencies(
    raw_lines: List[str] | None,
    source_dir: str | Path | None = None,
    root_file: str | Path | None = None,
) -> Dict[str, Any]:
    runtime_inputs: List[Dict[str, Any]] = []
    runtime_outputs: List[Dict[str, Any]] = []
    ignored_lines: List[Dict[str, Any]] = []

    if not isinstance(raw_lines, list):
        return {
            "runtime_inputs": runtime_inputs,
            "runtime_outputs": runtime_outputs,
            "ignored_lines": ignored_lines,
            "missing_runtime_inputs": [],
        }

    src_root = Path(source_dir) if source_dir else None
    seen_runtime: set[tuple[str, str]] = set()
    seen_outputs: set[tuple[str, str]] = set()

    for lineno, raw in enumerate(raw_lines, start=1):
        line = _strip_cmg_comments(str(raw))
        if not line.strip():
            continue
        matched_runtime = False

        for dependency_type, pattern in _RUNTIME_PATTERNS:
            for match in pattern.finditer(line):
                relpath = match.group(1).strip()
                if not relpath:
                    continue
                key = (dependency_type.upper().lstrip("*"), relpath)
                if key in seen_runtime:
                    matched_runtime = True
                    continue
                seen_runtime.add(key)
                entry: Dict[str, Any] = {
                    "type": dependency_type,
                    "path": relpath,
                    "line": lineno,
                    "required_for_runtime": True,
                }
                if src_root is not None:
                    src_path = Path(relpath)
                    if not src_path.is_absolute():
                        src_path = src_root / src_path
                    entry["source_path"] = str(src_path)
                    entry["exists"] = src_path.exists()
                entry.update(_infer_runtime_producer(dependency_type, relpath, src_root))
                runtime_inputs.append(entry)
                matched_runtime = True

        for dependency_type, pattern in _RUNTIME_OUTPUT_PATTERNS:
            for match in pattern.finditer(line):
                output = _infer_runtime_output(
                    dependency_type,
                    line=lineno,
                    root_file=root_file,
                )
                if not output:
                    matched_runtime = True
                    continue
                key = (_normalize_dependency_type(dependency_type), str(output.get("path", "")))
                if key in seen_outputs or not output.get("path"):
                    matched_runtime = True
                    continue
                seen_outputs.add(key)
                runtime_outputs.append(output)
                matched_runtime = True

        if matched_runtime:
            continue

        if any(pattern.search(line) for pattern in _NON_RUNTIME_HINTS):
            ignored_lines.append({
                "line": lineno,
                "text": line.strip(),
                "reason": "non-runtime control/output metadata",
            })

    missing_runtime_inputs = [
        item for item in runtime_inputs
        if item.get("exists") is False
    ]

    return {
        "runtime_inputs": runtime_inputs,
        "runtime_outputs": runtime_outputs,
        "ignored_lines": ignored_lines,
        "missing_runtime_inputs": missing_runtime_inputs,
    }


def build_cmg_case_manifest(
    filepath: str | Path | None,
    dependencies: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    path = Path(filepath) if filepath else None
    deps = dependencies or {}
    manifest: Dict[str, Any] = {
        "root_file": path.name if path else "",
        "source_dir": str(path.parent) if path else "",
        "static_inputs": [],
        "runtime_inputs": [],
        "runtime_outputs": [],
    }

    for raw_item in deps.get("runtime_inputs", []) or []:
        item = _normalize_case_item(raw_item)
        kind = item.get("kind", "")
        if kind in _STATIC_INPUT_TYPES:
            manifest["static_inputs"].append(item)
        elif kind in _RUNTIME_INPUT_TYPES:
            manifest["runtime_inputs"].append(item)
        else:
            manifest["runtime_inputs"].append(item)

    for raw_item in deps.get("runtime_outputs", []) or []:
        item = _normalize_case_item(raw_item)
        if item.get("path"):
            manifest["runtime_outputs"].append(item)

    seen_outputs = {
        (str(item.get("kind", "")), str(item.get("path", "")))
        for item in manifest["runtime_outputs"]
        if item.get("path")
    }
    for raw_item in _default_runtime_outputs(path):
        item = _normalize_case_item(raw_item)
        key = (str(item.get("kind", "")), str(item.get("path", "")))
        if key in seen_outputs or not item.get("path"):
            continue
        seen_outputs.add(key)
        manifest["runtime_outputs"].append(item)

    return manifest


def collect_case_input_files(data: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    if not isinstance(data, dict):
        return []

    manifest = data.get("case_manifest", {}) or {}
    items: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for bucket in ("static_inputs", "runtime_inputs"):
        for raw_item in manifest.get(bucket, []) or []:
            item = _normalize_case_item(raw_item)
            key = (str(item.get("kind", "")), str(item.get("path", "")))
            if key in seen or not item.get("path"):
                continue
            seen.add(key)
            items.append(item)

    if items:
        return items

    meta = data.get("meta", {}) or {}
    deps = meta.get("_cmg_case_dependencies", {}) or {}
    for raw_item in deps.get("runtime_inputs", []) or []:
        item = _normalize_case_item(raw_item)
        key = (str(item.get("kind", "")), str(item.get("path", "")))
        if key in seen or not item.get("path"):
            continue
        seen.add(key)
        items.append(item)
    return items


def collect_case_output_files(data: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    if not isinstance(data, dict):
        return []

    manifest = data.get("case_manifest", {}) or {}
    items: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for raw_item in manifest.get("runtime_outputs", []) or []:
        item = _normalize_case_item(raw_item)
        key = (str(item.get("kind", "")), str(item.get("path", "")))
        if key in seen or not item.get("path"):
            continue
        seen.add(key)
        items.append(item)

    if items:
        return items

    meta = data.get("meta", {}) or {}
    deps = meta.get("_cmg_case_dependencies", {}) or {}
    for raw_item in deps.get("runtime_outputs", []) or []:
        item = _normalize_case_item(raw_item)
        key = (str(item.get("kind", "")), str(item.get("path", "")))
        if key in seen or not item.get("path"):
            continue
        seen.add(key)
        items.append(item)
    return items


def analyze_case_assembly(cases: List[Dict[str, Any]] | None) -> Dict[str, Any]:
    if not isinstance(cases, list):
        return {"ok": True, "case_count": 0, "resolved_links": 0, "missing_links": 0, "cases": []}

    normalized_cases: List[Dict[str, Any]] = []
    outputs_by_case: Dict[str, List[Dict[str, Any]]] = {}
    outputs_by_path: Dict[str, List[Dict[str, Any]]] = {}
    outputs_by_artifact: Dict[str, List[Dict[str, Any]]] = {}

    for data in cases:
        if not isinstance(data, dict):
            continue
        manifest = data.get("case_manifest", {}) or {}
        root_file = str(manifest.get("root_file") or "")
        runtime_inputs = [
            _normalize_case_item(item)
            for item in (manifest.get("runtime_inputs", []) or [])
            if isinstance(item, dict) and item.get("path")
        ]
        runtime_outputs = collect_case_output_files(data)
        case_entry = {
            "root_file": root_file,
            "runtime_inputs": runtime_inputs,
            "runtime_outputs": runtime_outputs,
        }
        normalized_cases.append(case_entry)
        if root_file:
            outputs_by_case[root_file] = runtime_outputs
        for item in runtime_outputs:
            path = str(item.get("path") or "")
            artifact = str(item.get("generated_artifact") or item.get("producer_artifact") or "")
            if path:
                outputs_by_path.setdefault(path, []).append({"case": root_file, "item": item})
            if artifact:
                outputs_by_artifact.setdefault(artifact, []).append({"case": root_file, "item": item})

    resolved_links = 0
    missing_links = 0
    results: List[Dict[str, Any]] = []

    for case in normalized_cases:
        links: List[Dict[str, Any]] = []
        missing: List[Dict[str, Any]] = []
        for item in case["runtime_inputs"]:
            producer_case = str(item.get("producer_case") or "")
            producer_artifact = str(item.get("producer_artifact") or "")
            path = str(item.get("path") or "")

            candidates: List[Dict[str, Any]] = []
            if producer_case and producer_case in outputs_by_case:
                candidates.extend(
                    {"case": producer_case, "item": output}
                    for output in outputs_by_case[producer_case]
                )
            if path:
                candidates.extend(outputs_by_path.get(path, []))
            if producer_artifact:
                candidates.extend(outputs_by_artifact.get(producer_artifact, []))

            matched = None
            for candidate in candidates:
                if candidate.get("case") == case.get("root_file"):
                    continue
                output_item = candidate.get("item") or {}
                output_path = str(output_item.get("path") or "")
                output_artifact = str(output_item.get("generated_artifact") or output_item.get("producer_artifact") or "")
                if producer_case and candidate.get("case") != producer_case:
                    continue
                if path and output_path == path:
                    matched = candidate
                    break
                if producer_artifact and output_artifact == producer_artifact:
                    matched = candidate
                    break

            if matched:
                resolved_links += 1
                output_item = matched.get("item") or {}
                links.append({
                    "input_path": path,
                    "consumer_case": case.get("root_file", ""),
                    "producer_case": matched.get("case", ""),
                    "producer_output_path": output_item.get("path"),
                    "producer_artifact": output_item.get("generated_artifact") or output_item.get("producer_artifact"),
                    "status": "resolved_by_declared_output",
                })
            else:
                missing_links += 1
                missing.append({
                    "input_path": path,
                    "consumer_case": case.get("root_file", ""),
                    "producer_case": producer_case,
                    "producer_artifact": producer_artifact,
                    "status": "unresolved",
                })

        results.append({
            "root_file": case.get("root_file", ""),
            "ok": not missing,
            "resolved_links": links,
            "missing_links": missing,
        })

    return {
        "ok": missing_links == 0,
        "case_count": len(results),
        "resolved_links": resolved_links,
        "missing_links": missing_links,
        "cases": results,
    }
