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


def scan_cmg_case_dependencies(raw_lines: List[str] | None, source_dir: str | Path | None = None) -> Dict[str, Any]:
    runtime_inputs: List[Dict[str, Any]] = []
    ignored_lines: List[Dict[str, Any]] = []

    if not isinstance(raw_lines, list):
        return {
            "runtime_inputs": runtime_inputs,
            "ignored_lines": ignored_lines,
            "missing_runtime_inputs": [],
        }

    src_root = Path(source_dir) if source_dir else None
    seen_runtime: set[tuple[str, str]] = set()

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
