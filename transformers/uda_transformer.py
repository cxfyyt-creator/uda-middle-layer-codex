from __future__ import annotations

from typing import Any, Dict, List

from models.standard_model import StandardModel
from business_rules import (
    apply_radial_perm_j,
    derive_pb,
    enrich_miscible_model,
    ensure_co_cvo,
    merge_pvt_saturated_only,
    merge_rockfluid_tables,
)


def _build_timeline_events(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for well in raw.get("wells", []):
        well_name = well.get("well_name", "UNKNOWN")
        for ev in well.get("alter_schedule", []):
            event = {
                "well_name": well_name,
                "absolute_days": float(ev.get("time", 0.0)),
                "event_type": "WELL_TARGET_CHANGE",
            }
            if "rate" in ev:
                event["target"] = "RATE"
                event["value"] = ev.get("rate")
            else:
                event["target"] = ev.get("target", "ORATE")
                event["value"] = ev.get("value")
            events.append(event)
    events.sort(key=lambda x: x.get("absolute_days", 0.0))
    return events


def transform_raw_to_standard(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Raw AST -> UDA Standard Model (v1 minimal).

    当前阶段以最小侵入方式引入 Transformer：
    - 承接原有 business_rules（PVT/相渗/补全）
    - 生成 timeline_events（absolute_days）
    - 统一增加 uda_version / unparsed_blocks
    """
    grid = dict(raw.get("grid", {}))
    reservoir = apply_radial_perm_j(grid, dict(raw.get("reservoir", {})))
    fluid = dict(raw.get("fluid", {}))
    rockfluid = dict(raw.get("rockfluid", {}))
    initial = dict(raw.get("initial", {}))

    merged_pvt = merge_pvt_saturated_only(fluid)
    if merged_pvt:
        fluid["pvt_table"] = merged_pvt

    swt, slt = merge_rockfluid_tables(rockfluid)
    if swt and not rockfluid.get("swt_table"):
        rockfluid["swt_table"] = swt
    if slt and not rockfluid.get("slt_table"):
        rockfluid["slt_table"] = slt

    co_obj, cvo_obj = ensure_co_cvo(fluid)
    fluid.setdefault("oil_compressibility", co_obj)
    fluid.setdefault("oil_viscosity_coeff", cvo_obj)

    initial.setdefault("bubble_point_pressure", derive_pb(initial, fluid))
    fluid, initial = enrich_miscible_model(fluid, rockfluid, initial, raw.get("meta", {}))

    model = StandardModel(
        meta=dict(raw.get("meta", {})),
        grid=grid,
        reservoir=reservoir,
        fluid=fluid,
        rockfluid=rockfluid,
        initial=initial,
        numerical=dict(raw.get("numerical", {})),
        wells=list(raw.get("wells", [])),
        timeline_events=_build_timeline_events(raw),
        unparsed_blocks=list(raw.get("unparsed_blocks", [])),
    )

    return model.to_dict()
