from __future__ import annotations

from typing import Any, List


def _get_field(obj: Any, key: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def extract_numeric_values(value_obj: Any) -> List[float]:
    if value_obj is None:
        return []

    value_type = _get_field(value_obj, "type")
    if value_type == "scalar":
        value = _get_field(value_obj, "value")
        try:
            return [float(value)]
        except (TypeError, ValueError):
            return []

    if value_type == "array":
        values = _get_field(value_obj, "values") or []
        out: List[float] = []
        for value in values:
            try:
                out.append(float(value))
            except (TypeError, ValueError):
                continue
        return out

    return []


def build_active_mask(grid: Any) -> List[bool]:
    if grid is None:
        return []

    active_values = extract_numeric_values(_get_field(grid, "active_cell_mask"))
    pinch_values = extract_numeric_values(_get_field(grid, "pinchout_array"))
    size = max(len(active_values), len(pinch_values))
    if size == 0:
        return []

    mask = [True] * size
    if active_values:
        if len(active_values) == 1 and size > 1:
            active_values = active_values * size
        for idx, value in enumerate(active_values[:size]):
            mask[idx] = mask[idx] and value > 0.0

    if pinch_values:
        if len(pinch_values) == 1 and size > 1:
            pinch_values = pinch_values * size
        for idx, value in enumerate(pinch_values[:size]):
            mask[idx] = mask[idx] and value > 0.0

    return mask


def collect_porosity_physics_issues(grid: Any, reservoir: Any) -> List[str]:
    porosity = _get_field(reservoir, "porosity")
    porosity_values = extract_numeric_values(porosity)
    if not porosity_values:
        return []

    active_mask = build_active_mask(grid)
    out_of_range: List[float] = []
    zero_active = 0

    for idx, value in enumerate(porosity_values):
        if value < 0.0 or value > 0.60:
            out_of_range.append(value)
            continue
        is_active = active_mask[idx] if idx < len(active_mask) else True
        if value == 0.0 and is_active:
            zero_active += 1

    issues: List[str] = []
    if out_of_range:
        issues.append(f"reservoir.porosity has values out of [0,0.60]: {out_of_range[:5]}")
    if zero_active:
        issues.append(f"reservoir.porosity has {zero_active} active cells with zero porosity")
    return issues
