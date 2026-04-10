from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from domain_logic.common import scalar_obj, table_obj
from infra.pvt_metadata import apply_pvt_role


def derive_co_from_pvto(fluid: Dict[str, Any]) -> float:
    pvto = fluid.get("pvto_table")
    if not pvto:
        return 0.0
    by_rs: Dict[float, List[List[float]]] = {}
    for row in pvto.get("rows", []):
        if len(row) < 4:
            continue
        rs = float(row[0])
        by_rs.setdefault(rs, []).append([float(value) for value in row[:4]])

    candidates = []
    for rows in by_rs.values():
        rows.sort(key=lambda row: row[1])
        if len(rows) < 2:
            continue
        p1, bo1 = rows[0][1], rows[0][2]
        p2, bo2 = rows[1][1], rows[1][2]
        if p2 > p1 and bo1 > 0 and bo2 > 0:
            co = abs((1.0 / bo1 - 1.0 / bo2) / (p2 - p1))
            if co > 0:
                candidates.append(co)
    if not candidates:
        return 0.0
    return sum(candidates) / len(candidates)


def derive_cvo(_: Dict[str, Any]) -> float:
    return 0.0


def ensure_co_cvo(fluid: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    co_obj = fluid.get("oil_compressibility")
    cvo_obj = fluid.get("oil_viscosity_coeff")

    if not co_obj:
        co_obj = {"type": "scalar", "value": derive_co_from_pvto(fluid), "unit": "1/psi"}
    if not cvo_obj:
        cvo_obj = {"type": "scalar", "value": derive_cvo(fluid), "unit": "1/psi"}

    return co_obj, cvo_obj


def derive_pb(initial: Dict[str, Any], fluid: Dict[str, Any]) -> Dict[str, Any]:
    pb = initial.get("bubble_point_pressure")
    if pb:
        return pb

    rsvd = initial.get("rsvd_table")
    pvto = fluid.get("pvto_table")
    if rsvd and pvto and rsvd.get("rows") and pvto.get("rows"):
        rs = float(rsvd["rows"][0][1])
        pvto_rows = sorted(pvto["rows"], key=lambda row: abs(float(row[0]) - rs))
        if pvto_rows:
            return {
                "type": "scalar",
                "value": float(pvto_rows[0][1]),
                "unit": "psia",
                "modifier": "CON",
            }

    if initial.get("ref_pressure"):
        return {
            "type": "scalar",
            "value": float(initial["ref_pressure"]["value"]),
            "unit": "psia",
            "modifier": "CON",
        }

    return {"type": "scalar", "value": 0.0, "unit": "psia", "modifier": "CON"}


def is_miscible_model(fluid: Dict[str, Any], meta: Optional[Dict[str, Any]] = None) -> bool:
    model = str(fluid.get("model", "")).upper()
    if model.startswith("MIS"):
        return True
    if meta and str(meta.get("model_type", "")).lower() == "miscible":
        return True
    return False


def derive_miscible_omegasg(fluid: Dict[str, Any]) -> Dict[str, Any]:
    existing = fluid.get("omegasg")
    if existing:
        return existing

    tlmixpar = fluid.get("tlmixpar")
    if isinstance(tlmixpar, dict) and tlmixpar.get("value") is not None:
        return scalar_obj(float(tlmixpar["value"]), "", source="domain_logic.fluid_logic.derive_miscible_omegasg")

    return scalar_obj(0.7, "", source="domain_logic.fluid_logic.derive_miscible_omegasg(default)")


def derive_miscible_minss(fluid: Dict[str, Any], rockfluid: Dict[str, Any]) -> Dict[str, Any]:
    existing = fluid.get("minss")
    if existing:
        return existing

    swfn = rockfluid.get("swfn_table")
    if swfn and swfn.get("rows"):
        swc = float(swfn["rows"][0][0])
        return scalar_obj(max(0.01, swc), "fraction", source="domain_logic.fluid_logic.derive_miscible_minss")

    return scalar_obj(0.05, "fraction", source="domain_logic.fluid_logic.derive_miscible_minss(default)")


def derive_pbs(initial: Dict[str, Any], fluid: Dict[str, Any]) -> Dict[str, Any]:
    pbs = initial.get("solvent_bubble_point_pressure")
    if pbs:
        return pbs

    pb = initial.get("bubble_point_pressure") or derive_pb(initial, fluid)
    if isinstance(pb, dict) and pb.get("type") == "array":
        values = pb.get("values") or []
        scalar_val = float(values[0]) if values else 0.0
        return scalar_obj(
            scalar_val,
            pb.get("unit", "psia") or "psia",
            modifier="CON",
            source="domain_logic.fluid_logic.derive_pbs",
        )
    if isinstance(pb, dict) and pb.get("value") is not None:
        return scalar_obj(
            float(pb["value"]),
            pb.get("unit", "psia") or "psia",
            modifier="CON",
            source="domain_logic.fluid_logic.derive_pbs",
        )

    return scalar_obj(0.0, "psia", modifier="CON", source="domain_logic.fluid_logic.derive_pbs(default)")


def derive_miscible_pvts(fluid: Dict[str, Any], initial: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    existing = fluid.get("pvts_table")
    if existing and existing.get("rows"):
        return existing

    pvdg = fluid.get("pvdg_table")
    if not pvdg or not pvdg.get("rows"):
        return None

    omegasg = float(derive_miscible_omegasg(fluid).get("value", 0.0))
    pbs = derive_pbs(initial, fluid)
    pbs_value = float(pbs.get("value", 0.0)) if isinstance(pbs, dict) else 0.0
    p_max = max(float(row[0]) for row in pvdg["rows"])

    rows: List[List[float]] = []
    for row in pvdg["rows"]:
        if len(row) < 3:
            continue
        pressure = float(row[0])
        bg = float(row[1])
        visg = float(row[2])
        es = 0.0 if bg == 0 else 1000.0 / bg
        if pressure <= pbs_value:
            omega_s = 0.0
        elif p_max <= pbs_value:
            omega_s = omegasg
        else:
            omega_s = omegasg * (pressure - pbs_value) / (p_max - pbs_value)
        rows.append([pressure, 0.0, es, visg, max(0.0, min(omegasg if omegasg > 0 else 1.0, omega_s))])

    return apply_pvt_role(
        table_obj(["p", "rss", "es", "viss", "omega_s"], rows, source="domain_logic.fluid_logic.derive_miscible_pvts"),
        pvt_form="cmg_pvts_table",
        representation_role="derived_for_cmg",
        preferred_backend="cmg",
        derived_from=["fluid.pvdg_table", "initial.bubble_point_pressure"],
    )


def enrich_miscible_model(
    fluid: Dict[str, Any],
    rockfluid: Dict[str, Any],
    initial: Dict[str, Any],
    meta: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if not is_miscible_model(fluid, meta):
        return fluid, initial

    fluid = dict(fluid)
    initial = dict(initial)

    fluid.setdefault("omegasg", derive_miscible_omegasg(fluid))
    fluid.setdefault("minss", derive_miscible_minss(fluid, rockfluid))

    pvts = derive_miscible_pvts(fluid, initial)
    if pvts:
        fluid.setdefault("pvts_table", pvts)

    initial.setdefault("solvent_bubble_point_pressure", derive_pbs(initial, fluid))
    return fluid, initial
