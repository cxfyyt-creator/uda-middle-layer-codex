from __future__ import annotations

from typing import Any, Dict, List


_TARGET_CRITICAL_PREFIXES = {
    "cmg": [
        "fluid.pvt_table",
        "fluid.pvts_table",
        "fluid.pvto_table",
        "fluid.pvdg_table",
        "rockfluid.swt_table",
        "rockfluid.slt_table",
        "initial.ref_pressure",
        "initial.ref_depth",
    ],
    "petrel": [
        "fluid.pvt_table",
        "fluid.pvto_table",
        "fluid.pvdg_table",
        "rockfluid.swof_table",
        "rockfluid.sgof_table",
        "rockfluid.swt_table",
        "rockfluid.slt_table",
        "initial.ref_pressure",
        "initial.ref_depth",
    ],
}


def _collect_confidence_items(node: Any, path: str = "") -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if isinstance(node, dict):
        if node.get("type") in ("scalar", "array", "table") and "confidence" in node:
            items.append(
                {
                    "path": path or "$",
                    "confidence": float(node.get("confidence", 1.0)),
                    "type": node.get("type"),
                    "source": node.get("source", ""),
                }
            )
        for key, value in node.items():
            child_path = f"{path}.{key}" if path else key
            items.extend(_collect_confidence_items(value, child_path))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            child_path = f"{path}[{i}]" if path else f"[{i}]"
            items.extend(_collect_confidence_items(value, child_path))
    return items


def _is_critical_path(path: str, target: str) -> bool:
    prefixes = _TARGET_CRITICAL_PREFIXES.get(target.lower(), [])
    path_no_index = path.replace("[", ".").replace("]", "")
    return any(path_no_index.startswith(prefix) for prefix in prefixes)


def evaluate_confidence(
    data: Dict[str, Any],
    *,
    target: str,
    warning_threshold: float = 0.9,
    block_threshold: float = 0.5,
) -> Dict[str, Any]:
    items = _collect_confidence_items(data)
    warnings: List[str] = []
    blockers: List[str] = []
    low_items: List[Dict[str, Any]] = []

    for item in items:
        conf = item["confidence"]
        path = item["path"]
        critical = _is_critical_path(path, target)
        if conf < warning_threshold:
            low_items.append({**item, "critical": critical})
        if critical and conf < block_threshold:
            blockers.append(f"{path} confidence={conf:.2f}")
        elif conf < warning_threshold:
            level = "critical" if critical else "non-critical"
            warnings.append(f"{path} confidence={conf:.2f} ({level})")

    return {
        "warnings": warnings,
        "blockers": blockers,
        "low_confidence_items": low_items,
        "checked_item_count": len(items),
        "warning_threshold": warning_threshold,
        "block_threshold": block_threshold,
        "target": target,
    }
