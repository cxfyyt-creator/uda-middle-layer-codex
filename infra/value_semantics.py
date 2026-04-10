from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def distribution_from_modifier(modifier: Optional[str], *, value_type: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    mod = str(modifier or "").upper().lstrip("*")
    mapping = {
        "CON": ("constant", None),
        "KVAR": ("by_layer", "k"),
        "IVAR": ("by_axis", "i"),
        "JVAR": ("by_axis", "j"),
        "ALL": ("full_grid", None),
    }
    if mod in mapping:
        return mapping[mod]
    if value_type == "scalar":
        return "constant", None
    return None, None


def modifier_from_distribution(obj: Any) -> Optional[str]:
    if not isinstance(obj, dict):
        return None

    distribution = str(obj.get("distribution") or "").lower()
    axis = str(obj.get("axis") or "").lower()

    if distribution == "constant":
        return "CON"
    if distribution == "by_layer":
        return "KVAR"
    if distribution == "by_axis":
        return {"i": "IVAR", "j": "JVAR", "k": "KVAR"}.get(axis)
    if distribution == "full_grid":
        return "ALL"
    return None


def apply_value_semantics(
    obj: Dict[str, Any],
    *,
    value_type: Optional[str] = None,
    modifier: Optional[str] = None,
    software: Optional[str] = None,
    keyword: Optional[str] = None,
    distribution: Optional[str] = None,
    axis: Optional[str] = None,
    format_hint: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    inferred_distribution, inferred_axis = distribution_from_modifier(modifier, value_type=value_type)

    if distribution is None:
        distribution = inferred_distribution
    if axis is None:
        axis = inferred_axis

    if distribution and "distribution" not in obj:
        obj["distribution"] = distribution
    if axis and "axis" not in obj:
        obj["axis"] = axis

    hint: Dict[str, Any] = {}
    if isinstance(obj.get("source_format_hint"), dict):
        hint.update(obj["source_format_hint"])
    if software:
        hint.setdefault("software", software)
    if keyword:
        hint.setdefault("keyword", keyword)
    if modifier:
        hint.setdefault("modifier", str(modifier).upper().lstrip("*"))
    if format_hint:
        hint.update(format_hint)

    if hint:
        obj["source_format_hint"] = hint
    return obj
