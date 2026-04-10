from __future__ import annotations

from typing import Any


def _normalize_ref_dict(obj: dict[str, Any]) -> dict[str, Any]:
    out = dict(obj)
    obj_type = str(out.get("type") or "")

    if obj_type == "reference":
        out["type"] = "ref"

    if out.get("type") != "ref":
        return out

    relation = str(out.get("relation") or "").upper()
    if relation == "EQUALSI":
        out.setdefault("source_file", "")
        out.setdefault("required", False)
        hint = dict(out.get("source_format_hint") or {})
        hint.setdefault("software", "cmg_imex")
        hint.setdefault("keyword", "*EQUALSI")
        if "scale" in out and "scale" not in hint:
            hint["scale"] = out.get("scale")
        out["source_format_hint"] = hint

    return out


def normalize_ir_refs(node: Any) -> Any:
    if isinstance(node, list):
        return [normalize_ir_refs(item) for item in node]

    if isinstance(node, dict):
        normalized = {key: normalize_ir_refs(value) for key, value in node.items()}
        return _normalize_ref_dict(normalized)

    return node
