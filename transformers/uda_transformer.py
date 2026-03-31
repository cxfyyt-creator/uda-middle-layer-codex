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
    resolve_equalsi_references,
)


def _infer_active_cell_mask(raw: Dict[str, Any], grid: Dict[str, Any], reservoir: Dict[str, Any]) -> Dict[str, Any]:
    if grid.get("active_cell_mask") is not None:
        return grid

    meta = raw.get("meta", {}) or {}
    raw_lines = meta.get("_cmg_raw_deck_lines") or []
    if not isinstance(raw_lines, list) or not raw_lines:
        return grid

    has_null_block_hint = any(
        phrase in str(line).lower()
        for line in raw_lines
        for phrase in ("null block", "null blocks", "zero value porosity grid", "zero value porosity grids")
    )
    if not has_null_block_hint:
        return grid

    porosity = reservoir.get("porosity") or {}
    if not (isinstance(porosity, dict) and porosity.get("type") == "array" and isinstance(porosity.get("values"), list)):
        return grid

    values = porosity.get("values") or []
    if not values or not any(float(v) == 0.0 for v in values):
        return grid

    inferred = {
        "type": "array",
        "values": [0.0 if float(v) == 0.0 else 1.0 for v in values],
        "unit": "",
        "grid_order": porosity.get("grid_order", "IJK"),
        "confidence": min(float(porosity.get("confidence", 0.8) or 0.8), 0.8),
        "source": "transformer.infer_active_cell_mask_from_zero_porosity",
        "source_format_hint": {
            "software": "cmg_imex",
            "policy": "zero_porosity_null_block",
        },
    }
    grid = dict(grid)
    grid["active_cell_mask"] = inferred
    grid["cell_activity_mode"] = "inferred_from_zero_porosity"
    return grid


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
    reservoir = resolve_equalsi_references(dict(raw.get("reservoir", {})))
    reservoir = apply_radial_perm_j(grid, reservoir)
    grid = _infer_active_cell_mask(raw, grid, reservoir)
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
        meta={
            **dict(raw.get("meta", {})),
            **({"_total_sim_time": raw.get("_total_sim_time")} if raw.get("_total_sim_time") is not None else {}),
        },
        case_manifest=dict(raw.get("case_manifest", {})),
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
