from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List


_RUNTIME_PATTERNS = [
    ("SIPDATA-IN", re.compile(r"(?i)\bSIPDATA-IN\b\s+['\"]([^'\"]+)['\"]")),
    ("BINDATA-IN", re.compile(r"(?i)\bBINDATA-IN\b\s+[\'\"]([^\'\"]+)[\'\"]")),
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
        line = str(raw)
        matched_runtime = False

        for dependency_type, pattern in _RUNTIME_PATTERNS:
            for match in pattern.finditer(line):
                relpath = match.group(1).strip()
                if not relpath:
                    continue
                key = (dependency_type.upper(), relpath)
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
