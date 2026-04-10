from __future__ import annotations

from typing import Any, Dict

from target_mappers.petrel.pvt_mapping import build_petrel_pvt_tables


def build_petrel_target_ir(data: Dict[str, Any]) -> Dict[str, Any]:
    prepared = dict(data)
    reservoir = dict(prepared.get("reservoir", {}))
    fluid = dict(prepared.get("fluid", {}))

    pvto, pvdg = build_petrel_pvt_tables(fluid)
    if pvto:
        fluid["pvto_table"] = pvto
    if pvdg:
        fluid["pvdg_table"] = pvdg

    if not fluid.get("rock_ref_pressure") and reservoir.get("rock_ref_pressure"):
        fluid["rock_ref_pressure"] = reservoir["rock_ref_pressure"]
    if not fluid.get("rock_compressibility") and reservoir.get("rock_compressibility"):
        fluid["rock_compressibility"] = reservoir["rock_compressibility"]

    prepared["reservoir"] = reservoir
    prepared["fluid"] = fluid
    return prepared
