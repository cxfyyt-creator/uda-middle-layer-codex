from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from utils.pvt_metadata import apply_pvt_role
from utils.rule_loader import get_loader


def _scalar_obj(value: float, unit: str, *, modifier: Optional[str] = None, source: str = "business_rules") -> Dict[str, Any]:
    obj = {
        "type": "scalar",
        "value": float(value),
        "unit": unit,
        "source": source,
        "confidence": 0.9,
    }
    if modifier:
        obj["modifier"] = modifier
    return obj


def _table_obj(columns: List[str], rows: List[List[float]], *, source: str) -> Dict[str, Any]:
    return {
        "type": "table",
        "columns": columns,
        "rows": rows,
        "source": source,
        "confidence": 0.9,
    }


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
    return apply_pvt_role({
        "type": "table",
        "columns": ["p", "rs", "bo", "eg", "viso", "visg"],
        "rows": merged,
        "source": "business_rules.merge_pvt_saturated_only",
        "confidence": 0.99,
    },
        pvt_form="cmg_pvt_table",
        representation_role="derived_for_cmg",
        preferred_backend="cmg",
        derived_from=["fluid.pvto_table", "fluid.pvdg_table"],
    )


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


def _sanitize_monotonic_prefix(rows: List[List[float]], *, x_index: int = 0) -> List[List[float]]:
    cleaned: List[List[float]] = []
    prev_x: Optional[float] = None
    for row in rows or []:
        if row is None or len(row) <= x_index:
            continue
        try:
            vals = [float(v) for v in row]
            x = float(vals[x_index])
        except (TypeError, ValueError):
            continue
        if prev_x is not None and x < prev_x - 1e-9:
            break
        cleaned.append(vals)
        prev_x = x

    dedup: Dict[float, List[float]] = {}
    for row in cleaned:
        dedup.setdefault(round(float(row[x_index]), 8), row)
    return [dedup[k] for k in sorted(dedup.keys())]


def _merge_swt(rockfluid: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """SWFN(sw,krw,pcow) + SOF3/SOF2 → SWT(sw,krw,krow,pcow)"""
    swfn = rockfluid.get("swfn_table")
    sof3 = rockfluid.get("sof3_table")
    sof2 = rockfluid.get("sof2_table")
    if not swfn:
        return None

    swfn_rows = _sanitize_monotonic_prefix(swfn["rows"], x_index=0)
    sof3_rows = _sanitize_monotonic_prefix(sof3["rows"], x_index=0) if sof3 else None
    sof2_rows = _sanitize_monotonic_prefix(sof2["rows"], x_index=0) if sof2 else None

    if sof3_rows:
        so_x = [r[0] for r in sof3_rows]
        krow_y = [r[1] for r in sof3_rows]
    elif sof2_rows:
        so_x = [r[0] for r in sof2_rows]
        krow_y = [r[1] for r in sof2_rows]
    else:
        so_x = krow_y = None

    rows = []
    for row in swfn_rows:
        if len(row) < 3:
            continue
        sw, krw, pcow = row[0], row[1], row[2]
        if so_x:
            so = 1.0 - sw
            krow = _interp1d(so, so_x, krow_y)
        else:
            krow = max(0.0, 1.0 - sw)
        rows.append([min(1.0, max(0.0, sw)), max(0.0, krw), max(0.0, krow), max(0.0, pcow)])

    rows = _sanitize_monotonic_prefix(rows, x_index=0)

    return {
        "type": "table",
        "columns": ["sw", "krw", "krow", "pcow"],
        "rows": rows,
        "confidence": 0.9,
        "source": "business_rules.merge_rockfluid_tables(swfn+sof3/sof2)",
    }


def _merge_slt(rockfluid: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """优先 SGFN(+SOF3) 生成 SLT；若缺 SGFN 但有 SWFN+SOF2，则构造保底 SLT。"""
    sgfn = rockfluid.get("sgfn_table")
    swfn = rockfluid.get("swfn_table")
    sof3 = rockfluid.get("sof3_table")
    sof2 = rockfluid.get("sof2_table")

    # 路径1：标准 SGFN
    if sgfn:
        sgfn_rows = _sanitize_monotonic_prefix(sgfn["rows"], x_index=0)
        sof3_rows = _sanitize_monotonic_prefix(sof3["rows"], x_index=0) if sof3 else None

        if sof3_rows:
            so_x = [r[0] for r in sof3_rows]
            krog_y = [r[2] for r in sof3_rows]
        else:
            so_x = krog_y = None

        rows = []
        for row in sgfn_rows:
            if len(row) < 3:
                continue
            sg, krg, pcog = row[0], row[1], row[2]
            sl = 1.0 - sg
            if so_x:
                so = 1.0 - sg
                krog = _interp1d(so, so_x, krog_y)
            else:
                krog = sg
            rows.append([min(1.0, max(0.0, sl)), max(0.0, krg), max(0.0, krog), max(0.0, pcog)])

        dedup: Dict[float, List[float]] = {}
        for sl, krg, krog, pcog in rows:
            dedup.setdefault(round(sl, 8), [sl, krg, krog, pcog])
        rows = [dedup[k] for k in sorted(dedup.keys())]
        return {
            "type": "table",
            "columns": ["sl", "krg", "krog", "pcog"],
            "rows": rows,
            "confidence": 0.9,
            "source": "business_rules.merge_rockfluid_tables(sgfn+sof3)",
        }

    # 路径2：保底 SWFN + SOF2
    if swfn and sof2:
        swfn_rows = _sanitize_monotonic_prefix(swfn["rows"], x_index=0)
        sof2_rows = _sanitize_monotonic_prefix(sof2["rows"], x_index=0)
        swc = float(swfn_rows[0][0]) if swfn_rows else 0.0
        sw_x = [float(r[0]) for r in swfn_rows]
        pcow_y = [float(r[2]) for r in swfn_rows]

        rows = []
        for so, krog_raw in sof2_rows:
            sl = min(1.0, max(swc, swc + float(so)))
            krog = min(1.0, max(0.0, float(krog_raw)))
            krg = min(1.0, max(0.0, 1.0 - krog))
            pcow = _interp1d(sl, sw_x, pcow_y) if sw_x else 0.0
            pcog = max(0.0, 0.667 * pcow)
            rows.append([sl, krg, krog, pcog])

        if rows and rows[0][0] > swc:
            pcog0 = max(0.0, 0.667 * (_interp1d(swc, sw_x, pcow_y) if sw_x else 0.0))
            rows.insert(0, [swc, 1.0, 0.0, pcog0])
        if rows and rows[-1][0] < 1.0:
            rows.append([1.0, 0.0, 1.0, 0.0])

        dedup: Dict[float, List[float]] = {}
        for sl, krg, krog, pcog in rows:
            dedup[round(sl, 6)] = [sl, krg, krog, pcog]
        rows = [dedup[k] for k in sorted(dedup.keys())]

        running_krog = 0.0
        running_krg = 1.0
        for row in rows:
            row[2] = max(running_krog, min(1.0, max(0.0, row[2])))
            running_krog = row[2]
            row[1] = min(running_krg, min(1.0, max(0.0, row[1])))
            running_krg = row[1]

        if rows:
            rows[0][2] = 0.0
            rows[0][1] = 1.0
            rows[-1][2] = 1.0
            rows[-1][1] = 0.0

        return {
            "type": "table",
            "columns": ["sl", "krg", "krog", "pcog"],
            "rows": rows,
            "confidence": 0.8,
            "source": "business_rules.merge_rockfluid_tables(swfn+sof2,miscible_fallback)",
        }

    return None


def _sgof_to_slt(rockfluid: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Eclipse/Petrel 的 SGOF(sg, krg, krog, pcog) → CMG SLT(sl, krg, krog, pcog)。"""
    sgof = rockfluid.get("sgof_table")
    if not sgof:
        return None

    rows = []
    for row in sgof.get("rows", []):
        if len(row) < 4:
            continue
        sg, krg, krog, pcog = [float(v) for v in row[:4]]
        sl = 1.0 - sg
        rows.append([
            min(1.0, max(0.0, sl)),
            min(1.0, max(0.0, krg)),
            min(1.0, max(0.0, krog)),
            pcog,
        ])

    if not rows:
        return None

    dedup: Dict[float, List[float]] = {}
    for sl, krg, krog, pcog in rows:
        dedup[round(sl, 8)] = [sl, krg, krog, pcog]
    rows = [dedup[k] for k in sorted(dedup.keys())]

    return {
        "type": "table",
        "columns": ["sl", "krg", "krog", "pcog"],
        "rows": rows,
        "confidence": 0.95,
        "source": "business_rules.merge_rockfluid_tables(sgof->slt)",
    }


def _merge_rockfluid_single(rockfluid: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    swt = rockfluid.get("swt_table") or rockfluid.get("swof_table")
    slt = rockfluid.get("slt_table")

    if not swt:
        swt = _merge_swt(rockfluid)
    if not slt:
        slt = _sgof_to_slt(rockfluid)
    if not slt:
        slt = _merge_slt(rockfluid)

    return swt, slt


def _table_set_count(rockfluid: Dict[str, Any], key: str) -> int:
    sets = rockfluid.get(f"{key}_sets")
    if isinstance(sets, list) and sets:
        return len(sets)
    return 1 if rockfluid.get(key) else 0


def _table_at_index(rockfluid: Dict[str, Any], key: str, index: int) -> Optional[Dict[str, Any]]:
    sets = rockfluid.get(f"{key}_sets")
    if isinstance(sets, list) and 0 <= index < len(sets):
        return sets[index]
    if index == 0:
        return rockfluid.get(key)
    return None


def _build_rockfluid_variant(rockfluid: Dict[str, Any], index: int) -> Dict[str, Any]:
    variant: Dict[str, Any] = {}
    for key in ("swt_table", "slt_table", "swof_table", "sgof_table", "swfn_table", "sgfn_table", "sof2_table", "sof3_table"):
        tbl = _table_at_index(rockfluid, key, index)
        if tbl:
            variant[key] = tbl
    return variant


def _score_monotonic_table(tbl: Optional[Dict[str, Any]], sat_col: int, endpoint_cols: Optional[Tuple[int, int]] = None) -> float:
    if not tbl or tbl.get("type") != "table":
        return -1e9
    rows = tbl.get("rows") or []
    if not rows:
        return -1e9
    try:
        sats = [float(r[sat_col]) for r in rows if len(r) > sat_col]
    except (TypeError, ValueError):
        return -1e9
    score = float(len(rows))
    if all(sats[i] <= sats[i + 1] for i in range(len(sats) - 1)):
        score += 50.0
    if sats:
        if 0.0 <= sats[0] <= 1.0:
            score += 5.0
        if 0.0 <= sats[-1] <= 1.0:
            score += 5.0
    if endpoint_cols and rows:
        lo_col, hi_col = endpoint_cols
        try:
            score -= abs(float(rows[0][lo_col])) * 20.0
            score -= abs(1.0 - float(max(r[hi_col] for r in rows if len(r) > hi_col))) * 20.0
        except (TypeError, ValueError, IndexError):
            pass
    return score


def merge_rockfluid_tables(rockfluid: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    ?????? CMG ???? swt/slt ????
    ????????? swt/slt?????? Eclipse/Petrel ?????????????????
    ????????? swfn/sgfn/sof3 ?????
    ?????????????????CMG ??? backend ??????????????
    """
    keys = ("swt_table", "slt_table", "swof_table", "sgof_table", "swfn_table", "sgfn_table", "sof2_table", "sof3_table")
    max_sets = max((_table_set_count(rockfluid, key) for key in keys), default=0)

    best_pair = _merge_rockfluid_single(rockfluid)
    best_score = _score_monotonic_table(best_pair[0], 0, endpoint_cols=(1, 2)) + _score_monotonic_table(best_pair[1], 0, endpoint_cols=(2, 1))

    if max_sets > 1:
        for idx in range(max_sets):
            variant = _build_rockfluid_variant(rockfluid, idx)
            if not variant:
                continue
            pair = _merge_rockfluid_single(variant)
            score = _score_monotonic_table(pair[0], 0, endpoint_cols=(1, 2)) + _score_monotonic_table(pair[1], 0, endpoint_cols=(2, 1))
            if score > best_score:
                best_pair = pair
                best_score = score

    return best_pair


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
        return _scalar_obj(float(tlmixpar["value"]), "", source="business_rules.derive_miscible_omegasg")

    return _scalar_obj(0.7, "", source="business_rules.derive_miscible_omegasg(default)")


def derive_miscible_minss(fluid: Dict[str, Any], rockfluid: Dict[str, Any]) -> Dict[str, Any]:
    existing = fluid.get("minss")
    if existing:
        return existing

    swfn = rockfluid.get("swfn_table")
    if swfn and swfn.get("rows"):
        swc = float(swfn["rows"][0][0])
        return _scalar_obj(max(0.01, swc), "fraction", source="business_rules.derive_miscible_minss")

    return _scalar_obj(0.05, "fraction", source="business_rules.derive_miscible_minss(default)")


def derive_pbs(initial: Dict[str, Any], fluid: Dict[str, Any]) -> Dict[str, Any]:
    pbs = initial.get("solvent_bubble_point_pressure")
    if pbs:
        return pbs

    pb = initial.get("bubble_point_pressure") or derive_pb(initial, fluid)
    if isinstance(pb, dict) and pb.get("type") == "array":
        values = pb.get("values") or []
        scalar_val = float(values[0]) if values else 0.0
        return _scalar_obj(scalar_val, pb.get("unit", "psia") or "psia", modifier="CON", source="business_rules.derive_pbs")
    if isinstance(pb, dict) and pb.get("value") is not None:
        return _scalar_obj(float(pb["value"]), pb.get("unit", "psia") or "psia", modifier="CON", source="business_rules.derive_pbs")

    return _scalar_obj(0.0, "psia", modifier="CON", source="business_rules.derive_pbs(default)")


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
        p = float(row[0])
        bg = float(row[1])
        visg = float(row[2])
        es = 0.0 if bg == 0 else 1000.0 / bg
        if p <= pbs_value:
            omega_s = 0.0
        elif p_max <= pbs_value:
            omega_s = omegasg
        else:
            omega_s = omegasg * (p - pbs_value) / (p_max - pbs_value)
        rows.append([p, 0.0, es, visg, max(0.0, min(omegasg if omegasg > 0 else 1.0, omega_s))])

    return apply_pvt_role(
        _table_obj(["p", "rss", "es", "viss", "omega_s"], rows, source="business_rules.derive_miscible_pvts"),
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
