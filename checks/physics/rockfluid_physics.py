from __future__ import annotations

from typing import Any, Dict, List


def _rows(obj: Any) -> list[list[Any]]:
    if isinstance(obj, dict) and obj.get("type") == "table":
        return obj.get("rows") or []
    return []


def _is_monotonic_non_decreasing(values: list[float]) -> bool:
    return all(values[i] <= values[i + 1] for i in range(len(values) - 1))


def check_relperm_table_physics(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    rockfluid = data.get("rockfluid", {}) or {}
    table_specs = [
        ("rockfluid.swt_table", rockfluid.get("swt_table"), 0),
        ("rockfluid.slt_table", rockfluid.get("slt_table"), 0),
        ("rockfluid.swof_table", rockfluid.get("swof_table"), 0),
        ("rockfluid.sgof_table", rockfluid.get("sgof_table"), 0),
        ("rockfluid.swfn_table", rockfluid.get("swfn_table"), 0),
        ("rockfluid.sgfn_table", rockfluid.get("sgfn_table"), 0),
        ("rockfluid.sof2_table", rockfluid.get("sof2_table"), 0),
        ("rockfluid.sof3_table", rockfluid.get("sof3_table"), 0),
    ]

    for name, tbl, sat_col in table_specs:
        rows = _rows(tbl)
        if not rows:
            continue
        sats = [float(r[sat_col]) for r in rows if len(r) > sat_col]
        if sats and not _is_monotonic_non_decreasing(sats):
            warnings.append(f"{name} saturation column is not monotonic non-decreasing")
        for idx, sat in enumerate(sats):
            if not (0.0 <= sat <= 1.0):
                blockers.append(f"{name}.rows[{idx}] saturation value {sat} out of [0,1]")
