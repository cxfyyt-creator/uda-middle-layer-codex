from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _interp1d(x: float, xs: List[float], ys: List[float]) -> float:
    if len(xs) < 2:
        return ys[0] if ys else 0.0
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for idx in range(len(xs) - 1):
        if xs[idx] <= x <= xs[idx + 1]:
            t = (x - xs[idx]) / (xs[idx + 1] - xs[idx])
            return ys[idx] + t * (ys[idx + 1] - ys[idx])
    return ys[-1]


def _sanitize_monotonic_prefix(rows: List[List[float]], *, x_index: int = 0) -> List[List[float]]:
    cleaned: List[List[float]] = []
    prev_x: Optional[float] = None
    for row in rows or []:
        if row is None or len(row) <= x_index:
            continue
        try:
            vals = [float(value) for value in row]
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
    return [dedup[key] for key in sorted(dedup.keys())]


def _build_swt_table(rockfluid: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    swfn = rockfluid.get("swfn_table")
    sof3 = rockfluid.get("sof3_table")
    sof2 = rockfluid.get("sof2_table")
    if not swfn:
        return None

    swfn_rows = _sanitize_monotonic_prefix(swfn["rows"], x_index=0)
    sof3_rows = _sanitize_monotonic_prefix(sof3["rows"], x_index=0) if sof3 else None
    sof2_rows = _sanitize_monotonic_prefix(sof2["rows"], x_index=0) if sof2 else None

    if sof3_rows:
        so_x = [row[0] for row in sof3_rows]
        krow_y = [row[1] for row in sof3_rows]
    elif sof2_rows:
        so_x = [row[0] for row in sof2_rows]
        krow_y = [row[1] for row in sof2_rows]
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
        "source": "target_mappers.cmg.rockfluid_mapping.build_cmg_rockfluid_tables(swfn+sof3/sof2)",
    }


def _build_slt_from_sgfn(rockfluid: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sgfn = rockfluid.get("sgfn_table")
    sof3 = rockfluid.get("sof3_table")
    if not sgfn:
        return None

    sgfn_rows = _sanitize_monotonic_prefix(sgfn["rows"], x_index=0)
    sof3_rows = _sanitize_monotonic_prefix(sof3["rows"], x_index=0) if sof3 else None

    if sof3_rows:
        so_x = [row[0] for row in sof3_rows]
        krog_y = [row[2] for row in sof3_rows]
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
    rows = [dedup[key] for key in sorted(dedup.keys())]
    return {
        "type": "table",
        "columns": ["sl", "krg", "krog", "pcog"],
        "rows": rows,
        "confidence": 0.9,
        "source": "target_mappers.cmg.rockfluid_mapping.build_cmg_rockfluid_tables(sgfn+sof3)",
    }


def _build_slt_miscible_fallback(rockfluid: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    swfn = rockfluid.get("swfn_table")
    sof2 = rockfluid.get("sof2_table")
    if not (swfn and sof2):
        return None

    swfn_rows = _sanitize_monotonic_prefix(swfn["rows"], x_index=0)
    sof2_rows = _sanitize_monotonic_prefix(sof2["rows"], x_index=0)
    swc = float(swfn_rows[0][0]) if swfn_rows else 0.0
    sw_x = [float(row[0]) for row in swfn_rows]
    pcow_y = [float(row[2]) for row in swfn_rows]

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
    rows = [dedup[key] for key in sorted(dedup.keys())]

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
        "source": "target_mappers.cmg.rockfluid_mapping.build_cmg_rockfluid_tables(swfn+sof2,miscible_fallback)",
    }


def _build_slt_from_sgx(table_obj: Optional[Dict[str, Any]], *, source_name: str) -> Optional[Dict[str, Any]]:
    if not table_obj:
        return None

    rows = []
    for row in table_obj.get("rows", []):
        if len(row) < 4:
            continue
        sg, krg, krog, pcog = [float(value) for value in row[:4]]
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
    rows = [dedup[key] for key in sorted(dedup.keys())]

    return {
        "type": "table",
        "columns": ["sl", "krg", "krog", "pcog"],
        "rows": rows,
        "confidence": 0.95,
        "source": f"target_mappers.cmg.rockfluid_mapping.build_cmg_rockfluid_tables({source_name}->slt)",
    }


def _build_slt_table(rockfluid: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    slt = _build_slt_from_sgx(rockfluid.get("sgt_table"), source_name="sgt")
    if slt:
        return slt
    slt = _build_slt_from_sgx(rockfluid.get("sgof_table"), source_name="sgof")
    if slt:
        return slt
    slt = _build_slt_from_sgfn(rockfluid)
    if slt:
        return slt
    return _build_slt_miscible_fallback(rockfluid)


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
    for key in (
        "swt_table",
        "slt_table",
        "swof_table",
        "sgof_table",
        "sgt_table",
        "swfn_table",
        "sgfn_table",
        "sof2_table",
        "sof3_table",
    ):
        table = _table_at_index(rockfluid, key, index)
        if table:
            variant[key] = table
    return variant


def _score_monotonic_table(
    tbl: Optional[Dict[str, Any]],
    sat_col: int,
    endpoint_cols: Optional[Tuple[int, int]] = None,
) -> float:
    if not tbl or tbl.get("type") != "table":
        return -1e9
    rows = tbl.get("rows") or []
    if not rows:
        return -1e9
    try:
        sats = [float(row[sat_col]) for row in rows if len(row) > sat_col]
    except (TypeError, ValueError):
        return -1e9
    score = float(len(rows))
    if all(sats[idx] <= sats[idx + 1] for idx in range(len(sats) - 1)):
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
            score -= abs(1.0 - float(max(row[hi_col] for row in rows if len(row) > hi_col))) * 20.0
        except (TypeError, ValueError, IndexError):
            pass
    return score


def _build_single_rockfluid_tables(rockfluid: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    swt = rockfluid.get("swt_table") or rockfluid.get("swof_table")
    slt = rockfluid.get("slt_table")

    if not swt:
        swt = _build_swt_table(rockfluid)
    if not slt:
        slt = _build_slt_table(rockfluid)

    return swt, slt


def build_cmg_rockfluid_tables(rockfluid: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    keys = (
        "swt_table",
        "slt_table",
        "swof_table",
        "sgof_table",
        "sgt_table",
        "swfn_table",
        "sgfn_table",
        "sof2_table",
        "sof3_table",
    )
    max_sets = max((_table_set_count(rockfluid, key) for key in keys), default=0)

    best_pair = _build_single_rockfluid_tables(rockfluid)
    best_score = _score_monotonic_table(best_pair[0], 0, endpoint_cols=(1, 2))
    best_score += _score_monotonic_table(best_pair[1], 0, endpoint_cols=(2, 1))

    if max_sets > 1:
        for idx in range(max_sets):
            variant = _build_rockfluid_variant(rockfluid, idx)
            if not variant:
                continue
            pair = _build_single_rockfluid_tables(variant)
            score = _score_monotonic_table(pair[0], 0, endpoint_cols=(1, 2))
            score += _score_monotonic_table(pair[1], 0, endpoint_cols=(2, 1))
            if score > best_score:
                best_pair = pair
                best_score = score

    return best_pair
