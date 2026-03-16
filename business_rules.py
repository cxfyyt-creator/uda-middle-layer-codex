from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from utils.rule_loader import get_loader


def _factor(rule_name: str, default: float = 1.0) -> float:
    rl = get_loader()
    rule = rl.unit_rule(rule_name) or {}
    f = rule.get("factor")
    return default if f is None else float(f)


def convert_by_rule(value: float, rule_name: str, *, context: Optional[Dict[str, Any]] = None) -> float:
    rl = get_loader()
    rule = rl.unit_rule(rule_name) or {}
    f = rule.get("factor")
    if f is not None:
        return float(value) * float(f)
    formula = str(rule.get("formula", "")).strip().lower()
    ctx = context or {}
    if rule_name == "eclipse_bg_to_cmg_eg" or "1000.0 /" in formula:
        bg = float(ctx.get("bg_eclipse", value))
        return 0.0 if bg == 0 else 1000.0 / bg
    return float(value)


def merge_pvt_saturated_only(fluid: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    pvt = fluid.get("pvt_table")
    if pvt:
        rows = sorted(pvt.get("rows", []), key=lambda r: r[0])
        return {**pvt, "rows": rows}

    pvto = fluid.get("pvto_table")
    pvdg = fluid.get("pvdg_table")
    if not pvto or not pvdg:
        return None

    rs_scale = _factor("eclipse_rs_to_cmg_rs", 1000.0)
    pvdg_rows = sorted(pvdg.get("rows", []), key=lambda r: r[0])
    pvdg_p = [r[0] for r in pvdg_rows]
    pvdg_bg = [r[1] for r in pvdg_rows]
    pvdg_visg = [r[2] for r in pvdg_rows]

    def interp(px: float, xs: List[float], ys: List[float]) -> float:
        if not xs:
            return 0.0
        if px <= xs[0]:
            return ys[0]
        if px >= xs[-1]:
            return ys[-1]
        for i in range(len(xs) - 1):
            if xs[i] <= px <= xs[i + 1]:
                t = (px - xs[i]) / (xs[i + 1] - xs[i])
                return ys[i] + t * (ys[i + 1] - ys[i])
        return ys[-1]

    seen_rs = set()
    merged = []
    for row in pvto.get("rows", []):
        if len(row) < 4:
            continue
        rs_e, p, bo, viso = float(row[0]), float(row[1]), float(row[2]), float(row[3])
        key = round(rs_e, 10)
        if key in seen_rs:
            continue
        seen_rs.add(key)

        rs_cmg = rs_e * rs_scale
        bg = interp(p, pvdg_p, pvdg_bg)
        visg = interp(p, pvdg_p, pvdg_visg)
        eg = convert_by_rule(bg, "eclipse_bg_to_cmg_eg", context={"bg_eclipse": bg})
        merged.append([p, rs_cmg, bo, eg, viso, visg])

    merged.sort(key=lambda r: r[0])
    return {
        "type": "table",
        "columns": ["p", "rs", "bo", "eg", "viso", "visg"],
        "rows": merged,
        "source": "business_rules.merge_pvt_saturated_only",
        "confidence": 0.99,
    }


def _interp1d(x: float, xs: List[float], ys: List[float]) -> float:
    if len(xs) < 2:
        return ys[0] if ys else 0.0
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            t = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + t * (ys[i + 1] - ys[i])
    return ys[-1]


def _merge_swt(rockfluid: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """SWFN(sw,krw,pcow) + SOF3(so,krow,krog) → SWT(sw,krw,krow,pcow)"""
    swfn = rockfluid.get("swfn_table")
    sof3 = rockfluid.get("sof3_table")
    if not swfn:
        return None

    swfn_rows = swfn["rows"]
    sof3_rows = sof3["rows"] if sof3 else None

    if sof3_rows:
        sof3_so = [r[0] for r in sof3_rows]
        sof3_krow = [r[1] for r in sof3_rows]
    else:
        sof3_so = sof3_krow = None

    rows = []
    for row in swfn_rows:
        sw, krw, pcow = row[0], row[1], row[2]
        if sof3_so:
            so = 1.0 - sw
            krow = _interp1d(so, sof3_so, sof3_krow)
        else:
            krow = 1.0 - sw
        rows.append([sw, krw, krow, pcow])

    return {
        "type": "table",
        "columns": ["sw", "krw", "krow", "pcow"],
        "rows": rows,
        "confidence": 0.9,
        "source": "business_rules.merge_rockfluid_tables(swfn+sof3)",
    }


def _merge_slt(rockfluid: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """SGFN(sg,krg,pcog) + SOF3(so,krow,krog) → SLT(sl,krg,krog,pcog)"""
    sgfn = rockfluid.get("sgfn_table")
    sof3 = rockfluid.get("sof3_table")
    if not sgfn:
        return None

    sgfn_rows = sgfn["rows"]
    sof3_rows = sof3["rows"] if sof3 else None

    if sof3_rows:
        sof3_so = [r[0] for r in sof3_rows]
        sof3_krog = [r[2] for r in sof3_rows]
    else:
        sof3_so = sof3_krog = None

    rows = []
    for row in sgfn_rows:
        sg, krg, pcog = row[0], row[1], row[2]
        sl = 1.0 - sg
        if sof3_so:
            so = 1.0 - sg
            krog = _interp1d(so, sof3_so, sof3_krog)
        else:
            krog = sg
        rows.append([sl, krg, krog, pcog])

    rows.sort(key=lambda r: r[0])
    return {
        "type": "table",
        "columns": ["sl", "krg", "krog", "pcog"],
        "rows": rows,
        "confidence": 0.9,
        "source": "business_rules.merge_rockfluid_tables(sgfn+sof3)",
    }


def merge_rockfluid_tables(rockfluid: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    统一返回 CMG 所需 swt/slt 表。
    优先使用已有 swt/slt（或 swof/sgof），否则尝试由 swfn/sgfn/sof3 合并。
    """
    swt = rockfluid.get("swt_table") or rockfluid.get("swof_table")
    slt = rockfluid.get("slt_table") or rockfluid.get("sgof_table")

    if not swt:
        swt = _merge_swt(rockfluid)
    if not slt:
        slt = _merge_slt(rockfluid)

    return swt, slt


def derive_co_from_pvto(fluid: Dict[str, Any]) -> float:
    pvto = fluid.get("pvto_table")
    if not pvto:
        return 0.0
    by_rs: Dict[float, List[List[float]]] = {}
    for row in pvto.get("rows", []):
        if len(row) < 4:
            continue
        rs = float(row[0])
        by_rs.setdefault(rs, []).append([float(x) for x in row[:4]])

    candidates = []
    for _, rows in by_rs.items():
        rows.sort(key=lambda r: r[1])
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
        co_val = derive_co_from_pvto(fluid)
        co_obj = {"type": "scalar", "value": co_val, "unit": "1/psi"}

    if not cvo_obj:
        cvo_val = derive_cvo(fluid)
        cvo_obj = {"type": "scalar", "value": cvo_val, "unit": "1/psi"}

    return co_obj, cvo_obj


def derive_pb(initial: Dict[str, Any], fluid: Dict[str, Any]) -> Dict[str, Any]:
    pb = initial.get("bubble_point_pressure")
    if pb:
        return pb

    rsvd = initial.get("rsvd_table")
    pvto = fluid.get("pvto_table")

    if rsvd and pvto and rsvd.get("rows") and pvto.get("rows"):
        rs = float(rsvd["rows"][0][1])
        pvto_rows = sorted(pvto["rows"], key=lambda r: abs(float(r[0]) - rs))
        if pvto_rows:
            return {"type": "scalar", "value": float(pvto_rows[0][1]), "unit": "psia", "modifier": "CON"}

    if initial.get("ref_pressure"):
        return {"type": "scalar", "value": float(initial["ref_pressure"]["value"]), "unit": "psia", "modifier": "CON"}

    return {"type": "scalar", "value": 0.0, "unit": "psia", "modifier": "CON"}


def should_reverse_k_layers(grid: Dict[str, Any]) -> bool:
    kdir = str(grid.get("kdir", "")).upper()
    return kdir != "DOWN"


def reorder_k_array(values: List[float], reverse: bool) -> List[float]:
    return list(reversed(values)) if reverse else list(values)


def apply_radial_perm_j(grid: Dict[str, Any], reservoir: Dict[str, Any]) -> Dict[str, Any]:
    if str(grid.get("grid_type", "CART")).upper() != "RADIAL":
        return reservoir
    if reservoir.get("perm_j") is None and reservoir.get("perm_i") is not None:
        reservoir = {**reservoir}
        reservoir["perm_j"] = reservoir["perm_i"]
    return reservoir


def compute_depth_from_tops(grid: Dict[str, Any], strategy: str = "default") -> Optional[Dict[str, Any]]:
    tops_obj = grid.get("tops_ref")
    dk_obj = grid.get("dk")
    if not tops_obj or not dk_obj:
        return None

    tops = tops_obj.get("value") if tops_obj.get("type") == "scalar" else (tops_obj.get("values") or [None])[0]
    dks = dk_obj.get("values") if dk_obj.get("type") == "array" else [dk_obj.get("value")]
    if tops is None or not dks:
        return None

    tops = float(tops)
    dks = [float(v) for v in dks]

    if strategy == "kdir_down":
        depth = tops + dks[0] / 2.0
    else:
        depth = tops + sum(dks) - dks[-1] / 2.0

    return {
        "type": "scalar",
        "value": depth,
        "unit": "ft",
        "i": 1,
        "j": 1,
        "k": 1,
        "source": "business_rules.compute_depth_from_tops",
        "confidence": 0.99,
    }
