from __future__ import annotations

from typing import Any, Dict, List

from ir_contracts.standard_ir import StandardModel


def assemble_standard_model(
    standardized: Dict[str, Any],
    raw: Dict[str, Any],
    timeline_events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    meta = dict(standardized.get("meta", {}))
    if raw.get("_total_sim_time") is not None:
        meta["_total_sim_time"] = raw["_total_sim_time"]

    model = StandardModel(
        meta=meta,
        case_manifest=dict(standardized.get("case_manifest", {})),
        grid=dict(standardized.get("grid", {})),
        reservoir=dict(standardized.get("reservoir", {})),
        fluid=dict(standardized.get("fluid", {})),
        rockfluid=dict(standardized.get("rockfluid", {})),
        initial=dict(standardized.get("initial", {})),
        numerical=dict(standardized.get("numerical", {})),
        wells=list(raw.get("wells", [])),
        timeline_events=timeline_events,
        unparsed_blocks=list(raw.get("unparsed_blocks", [])),
    )
    return model.to_dict()
