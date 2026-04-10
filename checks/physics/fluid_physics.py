from __future__ import annotations

from typing import Any, Dict, List


def _rows(obj: Any) -> list[list[Any]]:
    if isinstance(obj, dict) and obj.get("type") == "table":
        return obj.get("rows") or []
    return []


def _is_monotonic_non_decreasing(values: list[float]) -> bool:
    return all(values[i] <= values[i + 1] for i in range(len(values) - 1))


def check_pvt_table_physics(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    fluid = data.get("fluid", {}) or {}

    pvt = fluid.get("pvt_table")
    rows = _rows(pvt)
    if rows:
        ps = [float(r[0]) for r in rows if len(r) >= 1]
        if ps and not _is_monotonic_non_decreasing(ps):
            warnings.append("fluid.pvt_table pressure column is not monotonic non-decreasing")

    pvto = fluid.get("pvto_table")
    rows = _rows(pvto)
    if rows:
        by_rs: Dict[float, list[float]] = {}
        for row in rows:
            if len(row) >= 2:
                by_rs.setdefault(float(row[0]), []).append(float(row[1]))
        for rs, ps in by_rs.items():
            if not _is_monotonic_non_decreasing(ps):
                warnings.append(f"fluid.pvto_table pressures are not monotonic inside rs={rs}")

    pvdg = fluid.get("pvdg_table")
    rows = _rows(pvdg)
    if rows:
        ps = [float(r[0]) for r in rows if len(r) >= 1]
        if ps and not _is_monotonic_non_decreasing(ps):
            warnings.append("fluid.pvdg_table pressure column is not monotonic non-decreasing")

    pvts = fluid.get("pvts_table")
    rows = _rows(pvts)
    if rows:
        ps = [float(r[0]) for r in rows if len(r) >= 1]
        if ps and not _is_monotonic_non_decreasing(ps):
            warnings.append("fluid.pvts_table pressure column is not monotonic non-decreasing")


def check_blackoil_validation(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    fluid = data.get("fluid", {}) or {}
    initial = data.get("initial", {}) or {}

    for key in ("oil_density", "gas_density", "water_density"):
        obj = fluid.get(key)
        if isinstance(obj, dict) and obj.get("value") is not None and float(obj.get("value", 0.0)) <= 0:
            blockers.append(f"fluid.{key} must be positive")
    if isinstance(fluid.get("gas_gravity"), dict) and fluid["gas_gravity"].get("value") is not None:
        if float(fluid["gas_gravity"].get("value", 0.0)) <= 0:
            blockers.append("fluid.gas_gravity must be positive")
    if isinstance(initial.get("goc_depth"), dict) and isinstance(initial.get("woc_depth"), dict):
        if float(initial["goc_depth"]["value"]) >= float(initial["woc_depth"]["value"]):
            blockers.append("initial.goc_depth should be shallower than initial.woc_depth")
