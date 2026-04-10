from __future__ import annotations

from typing import Any, Dict

from target_mappers.cmg.pvt_mapping import build_cmg_pvt_table
from target_mappers.cmg.rockfluid_mapping import build_cmg_rockfluid_tables


def build_cmg_target_ir(data: Dict[str, Any]) -> Dict[str, Any]:
    prepared = dict(data)
    fluid = dict(prepared.get("fluid", {}))
    rockfluid = dict(prepared.get("rockfluid", {}))

    pvt = build_cmg_pvt_table(fluid)
    if pvt:
        fluid["pvt_table"] = pvt

    swt, slt = build_cmg_rockfluid_tables(rockfluid)
    if swt:
        rockfluid["swt_table"] = swt
    if slt:
        rockfluid["slt_table"] = slt

    prepared["fluid"] = fluid
    prepared["rockfluid"] = rockfluid
    return prepared
