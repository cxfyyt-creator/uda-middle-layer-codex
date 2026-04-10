from __future__ import annotations

from typing import Any, Dict

from domain_logic import (
    apply_radial_perm_j,
    derive_pb,
    enrich_miscible_model,
    ensure_co_cvo,
    resolve_equalsi_references,
)
from infra.ir_normalization import normalize_ir_refs


def infer_active_cell_mask(raw: Dict[str, Any], grid: Dict[str, Any], reservoir: Dict[str, Any]) -> Dict[str, Any]:
    if grid.get("active_cell_mask") is not None:
        return grid

    meta = raw.get("meta", {}) or {}
    if not meta.get("_cmg_null_block_hint"):
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


def normalize_standard_sections(data: Dict[str, Any]) -> Dict[str, Any]:
    data = normalize_ir_refs(data)

    meta = dict(data.get("meta", {}))
    grid = dict(data.get("grid", {}))
    reservoir = resolve_equalsi_references(dict(data.get("reservoir", {})))
    reservoir = apply_radial_perm_j(grid, reservoir)
    grid = infer_active_cell_mask(data, grid, reservoir)
    fluid = dict(data.get("fluid", {}))
    rockfluid = dict(data.get("rockfluid", {}))
    initial = dict(data.get("initial", {}))

    co_obj, cvo_obj = ensure_co_cvo(fluid)
    fluid.setdefault("oil_compressibility", co_obj)
    fluid.setdefault("oil_viscosity_coeff", cvo_obj)

    initial.setdefault("bubble_point_pressure", derive_pb(initial, fluid))
    fluid, initial = enrich_miscible_model(fluid, rockfluid, initial, meta)

    normalized = dict(data)
    normalized["meta"] = meta
    normalized["grid"] = grid
    normalized["reservoir"] = reservoir
    normalized["fluid"] = fluid
    normalized["rockfluid"] = rockfluid
    normalized["initial"] = initial
    return normalized
