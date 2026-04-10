from __future__ import annotations

from typing import Any, Dict, List, Optional

from domain_logic.common import convert_by_rule, factor
from infra.pvt_metadata import apply_pvt_role


def build_cmg_pvt_table(fluid: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    pvt = fluid.get("pvt_table")
    if pvt:
        rows = sorted(pvt.get("rows", []), key=lambda row: row[0])
        return {**pvt, "rows": rows}

    pvto = fluid.get("pvto_table")
    pvdg = fluid.get("pvdg_table")
    if not pvto or not pvdg:
        return None

    rs_scale = factor("eclipse_rs_to_cmg_rs", 1000.0)
    pvdg_rows = sorted(pvdg.get("rows", []), key=lambda row: row[0])
    pvdg_p = [row[0] for row in pvdg_rows]
    pvdg_bg = [row[1] for row in pvdg_rows]
    pvdg_visg = [row[2] for row in pvdg_rows]

    def interp(px: float, xs: List[float], ys: List[float]) -> float:
        if not xs:
            return 0.0
        if px <= xs[0]:
            return ys[0]
        if px >= xs[-1]:
            return ys[-1]
        for idx in range(len(xs) - 1):
            if xs[idx] <= px <= xs[idx + 1]:
                t = (px - xs[idx]) / (xs[idx + 1] - xs[idx])
                return ys[idx] + t * (ys[idx + 1] - ys[idx])
        return ys[-1]

    seen_rs = set()
    merged = []
    for row in pvto.get("rows", []):
        if len(row) < 4:
            continue
        rs_e, pressure, bo, viso = float(row[0]), float(row[1]), float(row[2]), float(row[3])
        key = round(rs_e, 10)
        if key in seen_rs:
            continue
        seen_rs.add(key)

        rs_cmg = rs_e * rs_scale
        bg = interp(pressure, pvdg_p, pvdg_bg)
        visg = interp(pressure, pvdg_p, pvdg_visg)
        eg = convert_by_rule(bg, "eclipse_bg_to_cmg_eg", context={"bg_eclipse": bg})
        merged.append([pressure, rs_cmg, bo, eg, viso, visg])

    merged.sort(key=lambda row: row[0])
    return apply_pvt_role(
        {
            "type": "table",
            "columns": ["p", "rs", "bo", "eg", "viso", "visg"],
            "rows": merged,
            "source": "target_mappers.cmg.pvt_mapping.build_cmg_pvt_table",
            "confidence": 0.99,
        },
        pvt_form="cmg_pvt_table",
        representation_role="derived_for_cmg",
        preferred_backend="cmg",
        derived_from=["fluid.pvto_table", "fluid.pvdg_table"],
    )
