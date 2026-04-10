from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional


def should_reverse_k_layers(grid: Dict[str, Any]) -> bool:
    kdir = str(grid.get("kdir", "")).upper()
    return kdir != "DOWN"


def reorder_k_array(values: List[float], reverse: bool) -> List[float]:
    return list(reversed(values)) if reverse else list(values)


def _scaled_value_object(obj: Dict[str, Any], scale: float, *, source: str, source_key: str) -> Dict[str, Any]:
    out = deepcopy(obj)
    obj_type = out.get("type")
    if obj_type == "scalar":
        out["value"] = float(out.get("value", 0.0)) * scale
    elif obj_type == "array":
        out["values"] = [float(value) * scale for value in (out.get("values") or [])]
    elif obj_type == "ref":
        if abs(float(scale) - 1.0) >= 1e-12:
            out["scale"] = float(scale)
        out["source_key"] = source_key
    else:
        return out

    hint = dict(out.get("source_format_hint") or {})
    hint.update({
        "software": "cmg_imex",
        "keyword": "*EQUALSI",
        "source_key": source_key,
        "scale": float(scale),
    })
    out["source_format_hint"] = hint
    out["source"] = source
    out["confidence"] = min(float(obj.get("confidence", 0.9)), 0.99)
    return out


def resolve_equalsi_references(section: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(section, dict):
        return section

    def _is_equalsi_ref(obj: Dict[str, Any]) -> bool:
        obj_type = str(obj.get("type") or "")
        relation = str(obj.get("relation") or "").upper()
        return obj_type in {"ref", "reference"} and relation == "EQUALSI"

    resolved = dict(section)
    changed = True
    while changed:
        changed = False
        for key, obj in list(resolved.items()):
            if not isinstance(obj, dict):
                continue
            if not _is_equalsi_ref(obj):
                continue

            source_key = obj.get("source_key")
            if not source_key:
                continue
            source_obj = resolved.get(source_key)
            if not isinstance(source_obj, dict):
                continue
            if _is_equalsi_ref(source_obj):
                continue

            scale = float(obj.get("scale", 1.0) or 1.0)
            resolved[key] = _scaled_value_object(
                source_obj,
                scale,
                source=f"domain_logic.reference_logic.resolve_equalsi_references({source_key})",
                source_key=str(source_key),
            )
            changed = True
    return resolved


def apply_radial_perm_j(grid: Dict[str, Any], reservoir: Dict[str, Any]) -> Dict[str, Any]:
    if str(grid.get("grid_type", "CART")).upper() != "RADIAL":
        return reservoir
    if reservoir.get("perm_j") is None and reservoir.get("perm_i") is not None:
        reservoir = {**reservoir}
        reservoir["perm_j"] = reservoir["perm_i"]
    return reservoir


def compute_depth_from_tops(grid: Dict[str, Any], strategy: str = "default") -> Optional[Dict[str, Any]]:
    tops_obj = grid.get("tops_ref")
    dk_obj = grid.get("dk")
    if not tops_obj or not dk_obj:
        return None

    tops = tops_obj.get("value") if tops_obj.get("type") == "scalar" else (tops_obj.get("values") or [None])[0]
    dks = dk_obj.get("values") if dk_obj.get("type") == "array" else [dk_obj.get("value")]
    if tops is None or not dks:
        return None

    tops = float(tops)
    dks = [float(value) for value in dks]
    if strategy == "kdir_down":
        depth = tops + dks[0] / 2.0
    else:
        depth = tops + sum(dks) - dks[-1] / 2.0

    return {
        "type": "scalar",
        "value": depth,
        "unit": "ft",
        "i": 1,
        "j": 1,
        "k": 1,
        "source": "domain_logic.reference_logic.compute_depth_from_tops",
        "confidence": 0.99,
    }
