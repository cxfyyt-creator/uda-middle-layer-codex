from __future__ import annotations

from typing import Any, Dict, List


def _has_value(obj: Any) -> bool:
    if obj is None:
        return False
    if isinstance(obj, dict):
        t = obj.get("type")
        if t == "scalar":
            return obj.get("value") is not None
        if t == "array":
            return bool(obj.get("values"))
        if t == "table":
            return bool(obj.get("rows"))
    return True


def _rows(obj: Any) -> list[list[Any]]:
    if isinstance(obj, dict) and obj.get("type") == "table":
        return obj.get("rows") or []
    return []


def _check_table_columns(obj: Any, expected: int, name: str, blockers: List[str]) -> None:
    rows = _rows(obj)
    for idx, row in enumerate(rows):
        if len(row) != expected:
            blockers.append(f"{name}.rows[{idx}] expected {expected} columns, got {len(row)}")


def _is_monotonic_non_decreasing(values: list[float]) -> bool:
    return all(values[i] <= values[i + 1] for i in range(len(values) - 1))


def _check_pvt_tables(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    fluid = data.get("fluid", {}) or {}

    pvt = fluid.get("pvt_table")
    if _has_value(pvt):
        _check_table_columns(pvt, 6, "fluid.pvt_table", blockers)
        rows = _rows(pvt)
        if rows:
            ps = [float(r[0]) for r in rows if len(r) >= 1]
            if ps and not _is_monotonic_non_decreasing(ps):
                warnings.append("fluid.pvt_table pressure column is not monotonic non-decreasing")

    pvto = fluid.get("pvto_table")
    if _has_value(pvto):
        _check_table_columns(pvto, 4, "fluid.pvto_table", blockers)
        rows = _rows(pvto)
        by_rs: Dict[float, list[float]] = {}
        for row in rows:
            if len(row) >= 2:
                by_rs.setdefault(float(row[0]), []).append(float(row[1]))
        for rs, ps in by_rs.items():
            if not _is_monotonic_non_decreasing(ps):
                warnings.append(f"fluid.pvto_table pressures are not monotonic inside rs={rs}")

    pvdg = fluid.get("pvdg_table")
    if _has_value(pvdg):
        _check_table_columns(pvdg, 3, "fluid.pvdg_table", blockers)
        rows = _rows(pvdg)
        if rows:
            ps = [float(r[0]) for r in rows if len(r) >= 1]
            if ps and not _is_monotonic_non_decreasing(ps):
                warnings.append("fluid.pvdg_table pressure column is not monotonic non-decreasing")

    pvts = fluid.get("pvts_table")
    if _has_value(pvts):
        _check_table_columns(pvts, 5, "fluid.pvts_table", blockers)
        rows = _rows(pvts)
        if rows:
            ps = [float(r[0]) for r in rows if len(r) >= 1]
            if ps and not _is_monotonic_non_decreasing(ps):
                warnings.append("fluid.pvts_table pressure column is not monotonic non-decreasing")


def _check_relperm_tables(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    rockfluid = data.get("rockfluid", {}) or {}
    table_specs = [
        ("rockfluid.swt_table", rockfluid.get("swt_table"), 4, 0),
        ("rockfluid.slt_table", rockfluid.get("slt_table"), 4, 0),
        ("rockfluid.swof_table", rockfluid.get("swof_table"), 4, 0),
        ("rockfluid.sgof_table", rockfluid.get("sgof_table"), 4, 0),
        ("rockfluid.swfn_table", rockfluid.get("swfn_table"), 3, 0),
        ("rockfluid.sgfn_table", rockfluid.get("sgfn_table"), 3, 0),
        ("rockfluid.sof2_table", rockfluid.get("sof2_table"), 2, 0),
        ("rockfluid.sof3_table", rockfluid.get("sof3_table"), 3, 0),
    ]

    for name, tbl, ncols, sat_col in table_specs:
        if not _has_value(tbl):
            continue
        _check_table_columns(tbl, ncols, name, blockers)
        rows = _rows(tbl)
        if not rows:
            continue
        sats = [float(r[sat_col]) for r in rows if len(r) > sat_col]
        if sats and not _is_monotonic_non_decreasing(sats):
            warnings.append(f"{name} saturation column is not monotonic non-decreasing")
        for idx, sat in enumerate(sats):
            if not (0.0 <= sat <= 1.0):
                blockers.append(f"{name}.rows[{idx}] saturation value {sat} out of [0,1]")


def _check_grid_common(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    grid = data.get("grid", {}) or {}
    for key in ("ni", "nj", "nk"):
        if not grid.get(key):
            blockers.append(f"grid.{key} is missing")

    gt = str(grid.get("grid_type", "CART")).upper()
    if gt == "RADIAL":
        if not (_has_value(grid.get("di")) or _has_value(grid.get("drv"))):
            blockers.append("radial grid requires grid.di or grid.drv")
        if not (_has_value(grid.get("dj")) or _has_value(grid.get("dtheta"))):
            blockers.append("radial grid requires grid.dj or grid.dtheta")
        if not _has_value(grid.get("dk")):
            blockers.append("radial grid requires grid.dk")
    else:
        for key in ("di", "dj", "dk"):
            if not _has_value(grid.get(key)):
                blockers.append(f"cartesian grid requires grid.{key}")

    if not (_has_value(grid.get("depth_ref_block")) or _has_value(grid.get("tops_ref"))):
        warnings.append("grid has neither depth_ref_block nor tops_ref; target may reject depth definition")


def _check_blackoil_fluid(data: Dict[str, Any], blockers: List[str], warnings: List[str], *, target: str) -> None:
    fluid = data.get("fluid", {}) or {}
    rockfluid = data.get("rockfluid", {}) or {}
    initial = data.get("initial", {}) or {}

    if not (
        _has_value(fluid.get("pvt_table"))
        or _has_value(fluid.get("zg_table"))
        or (_has_value(fluid.get("pvto_table")) and _has_value(fluid.get("pvdg_table")))
    ):
        blockers.append("blackoil fluid requires pvt_table or zg_table or pvto_table+pvdg_table")

    missing_densities = [k for k in ("oil_density", "water_density") if not _has_value(fluid.get(k))]
    if not (_has_value(fluid.get("gas_density")) or _has_value(fluid.get("gas_gravity"))):
        missing_densities.append("gas_density_or_gravity")
    if missing_densities:
        blockers.append("missing density fields: " + ", ".join(f"fluid.{k}" for k in missing_densities))
    for key in ("oil_density", "gas_density", "water_density"):
        obj = fluid.get(key)
        if _has_value(obj) and float(obj.get("value", 0.0)) <= 0:
            blockers.append(f"fluid.{key} must be positive")
    if _has_value(fluid.get("gas_gravity")) and float(fluid["gas_gravity"].get("value", 0.0)) <= 0:
        blockers.append("fluid.gas_gravity must be positive")

    if target == "cmg":
        if not (_has_value(rockfluid.get("swt_table")) or _has_value(rockfluid.get("swof_table")) or _has_value(rockfluid.get("swfn_table"))):
            blockers.append("CMG requires water/oil rockfluid data (swt_table or convertible source)")
        if not (
            _has_value(rockfluid.get("slt_table"))
            or _has_value(rockfluid.get("sgof_table"))
            or _has_value(rockfluid.get("sgfn_table"))
            or _has_value(rockfluid.get("sof3_table"))
            or _has_value(rockfluid.get("sof2_table"))
        ):
            blockers.append("CMG requires gas/oil rockfluid data (slt_table or convertible source)")
    else:
        if not (
            _has_value(rockfluid.get("swof_table"))
            or _has_value(rockfluid.get("swt_table"))
            or _has_value(rockfluid.get("swfn_table"))
        ):
            warnings.append("Petrel output has no explicit SWOF/SWT/SWFN source; rockfluid may be incomplete")
        if not (
            _has_value(rockfluid.get("sgof_table"))
            or _has_value(rockfluid.get("slt_table"))
            or _has_value(rockfluid.get("sgfn_table"))
        ):
            warnings.append("Petrel output has no explicit SGOF/SLT/SGFN source; gas-oil relperm may be incomplete")

    if not _has_value(initial.get("ref_pressure")):
        warnings.append("initial.ref_pressure is missing; initial condition block may be weak")
    if not _has_value(initial.get("ref_depth")):
        warnings.append("initial.ref_depth is missing; initial condition block may be weak")
    if _has_value(initial.get("goc_depth")) and _has_value(initial.get("woc_depth")):
        if float(initial["goc_depth"]["value"]) >= float(initial["woc_depth"]["value"]):
            blockers.append("initial.goc_depth should be shallower than initial.woc_depth")


def _check_miscible_fluid(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    fluid = data.get("fluid", {}) or {}
    if not (_has_value(fluid.get("pvts_table")) or _has_value(fluid.get("pvdg_table"))):
        blockers.append("miscible model requires pvts_table or at least pvdg_table for derivation")
    if not _has_value(fluid.get("omegasg")):
        warnings.append("miscible model missing fluid.omegasg")
    if not _has_value(fluid.get("minss")):
        warnings.append("miscible model missing fluid.minss")
    for key in ("oil_density", "gas_density", "water_density"):
        if not _has_value(fluid.get(key)):
            warnings.append(f"miscible model missing fluid.{key}")


def _check_water_properties(data: Dict[str, Any], warnings: List[str]) -> None:
    fluid = data.get("fluid", {}) or {}
    for key in ("water_fvf", "water_compressibility", "water_ref_pressure", "water_viscosity"):
        if not _has_value(fluid.get(key)):
            warnings.append(f"fluid.{key} is missing")


def _check_wells(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    wells = data.get("wells", []) or []
    timeline_events = data.get("timeline_events", []) or []
    grid = data.get("grid", {}) or {}
    ni = grid.get("ni")
    nj = grid.get("nj")
    nk = grid.get("nk")
    seen_names = set()

    for idx, w in enumerate(wells, start=1):
        name = str(w.get("well_name") or "").strip()
        if not name:
            blockers.append(f"wells[{idx-1}] missing well_name")
            continue
        if name in seen_names:
            blockers.append(f"duplicate well name: {name}")
        seen_names.add(name)

        wtype = str(w.get("well_type") or "").upper()
        if not wtype:
            warnings.append(f"well {name} missing well_type")

        perfs = w.get("perforations", []) or []
        if not perfs:
            warnings.append(f"well {name} has no perforations")
        for pidx, perf in enumerate(perfs):
            for key in ("i", "j", "k"):
                if perf.get(key) is None:
                    blockers.append(f"well {name} perforations[{pidx}] missing {key}")
            if ni and perf.get("i") is not None and not (1 <= int(perf["i"]) <= int(ni)):
                blockers.append(f"well {name} perforations[{pidx}].i out of grid range")
            if nj and perf.get("j") is not None and not (1 <= int(perf["j"]) <= int(nj)):
                blockers.append(f"well {name} perforations[{pidx}].j out of grid range")
            if nk and perf.get("k") is not None and not (1 <= int(perf["k"]) <= int(nk)):
                blockers.append(f"well {name} perforations[{pidx}].k out of grid range")

        if wtype == "INJECTOR":
            if not w.get("inj_fluid"):
                blockers.append(f"injector well {name} missing inj_fluid")
            elif str(w.get("inj_fluid")).upper() not in ("GAS", "WATER", "SOLVENT"):
                blockers.append(f"injector well {name} has unsupported inj_fluid={w.get('inj_fluid')}")
            if w.get("rate_max") is None and w.get("bhp_max") is None:
                warnings.append(f"injector well {name} has neither rate_max nor bhp_max")
            if w.get("bhp_min") is not None:
                warnings.append(f"injector well {name} has bhp_min which is unusual")
        elif wtype == "PRODUCER":
            if w.get("rate_max") is None and w.get("bhp_min") is None:
                warnings.append(f"producer well {name} has neither rate_max nor bhp_min")
            if w.get("bhp_max") is not None:
                warnings.append(f"producer well {name} has bhp_max which is unusual")
        elif wtype:
            blockers.append(f"well {name} has unsupported well_type={wtype}")

        if w.get("rate_max") is not None and float(w.get("rate_max")) <= 0:
            warnings.append(f"well {name} has non-positive rate_max")
        if w.get("bhp_max") is not None and float(w.get("bhp_max")) <= 0:
            warnings.append(f"well {name} has non-positive bhp_max")
        if w.get("bhp_min") is not None and float(w.get("bhp_min")) <= 0:
            warnings.append(f"well {name} has non-positive bhp_min")

    for ev_idx, ev in enumerate(timeline_events):
        wname = ev.get("well_name")
        if wname and wname not in seen_names:
            blockers.append(f"timeline_events[{ev_idx}] references unknown well {wname}")
        if ev.get("event_type") == "WELL_TARGET_CHANGE" and ev.get("value") is None:
            blockers.append(f"timeline_events[{ev_idx}] missing value")
        if ev.get("absolute_days") is not None and float(ev.get("absolute_days")) < 0:
            blockers.append(f"timeline_events[{ev_idx}] has negative absolute_days")
        if ev.get("event_type") and ev.get("event_type") != "WELL_TARGET_CHANGE":
            warnings.append(f"timeline_events[{ev_idx}] has unsupported event_type={ev.get('event_type')}")


def _check_schedule_support(data: Dict[str, Any], blockers: List[str], warnings: List[str], *, target: str) -> None:
    timeline_events = data.get("timeline_events", []) or []
    if not timeline_events:
        return

    if target == "cmg":
        supported_targets = {"RATE", "ORAT", "WRAT", "GRAT", "ORATE", "WRATE", "GRATE", "STO", "STG", "STW", "BHP"}
        approximation_counts: Dict[str, int] = {}
        for idx, ev in enumerate(timeline_events):
            tgt = str(ev.get("target") or "RATE").upper()
            if tgt not in supported_targets:
                blockers.append(f"timeline_events[{idx}] target={tgt} is not supported by current CMG backend")
            if tgt in {"BHP", "ORAT", "WRAT", "GRAT", "ORATE", "WRATE", "GRATE"}:
                approximation_counts[tgt] = approximation_counts.get(tgt, 0) + 1
        for tgt, count in sorted(approximation_counts.items()):
            warnings.append(f"{count} timeline events with target={tgt} will be mapped to current CMG ALTER schedule backend")

    if target == "petrel":
        for idx, ev in enumerate(timeline_events):
            if ev.get("event_type") != "WELL_TARGET_CHANGE":
                warnings.append(f"timeline_events[{idx}] may not be exported cleanly to Petrel")


def _check_case_runtime_dependencies(data: Dict[str, Any], blockers: List[str], warnings: List[str], *, target: str) -> None:
    if target != "cmg":
        return

    meta = data.get("meta", {}) or {}
    deps = meta.get("_cmg_case_dependencies", {}) or {}
    runtime_inputs = deps.get("runtime_inputs", []) or []
    missing_runtime_inputs = deps.get("missing_runtime_inputs", []) or []

    if runtime_inputs:
        warnings.append(f"cmg runtime inputs detected: {len(runtime_inputs)}")

    for item in missing_runtime_inputs:
        path = item.get("path") or item.get("source_path") or "<unknown>"
        blockers.append(f"missing required CMG runtime input: {path}")


def evaluate_target_preflight(data: Dict[str, Any], *, target: str) -> Dict[str, Any]:
    blockers: List[str] = []
    warnings: List[str] = []

    meta = data.get("meta", {}) or {}
    fluid = data.get("fluid", {}) or {}
    model = str(fluid.get("model", "BLACKOIL")).upper()

    if not meta.get("unit_system"):
        warnings.append("meta.unit_system is missing")
    if not meta.get("source_software"):
        warnings.append("meta.source_software is missing")

    _check_grid_common(data, blockers, warnings)
    _check_water_properties(data, warnings)
    _check_pvt_tables(data, blockers, warnings)
    _check_relperm_tables(data, blockers, warnings)
    _check_wells(data, blockers, warnings)
    _check_schedule_support(data, blockers, warnings, target=target.lower())
    _check_case_runtime_dependencies(data, blockers, warnings, target=target.lower())

    if model.startswith("MIS"):
        if target.lower() == "petrel":
            blockers.append("current Petrel backend does not support miscible export")
        _check_miscible_fluid(data, blockers, warnings)
    else:
        _check_blackoil_fluid(data, blockers, warnings, target=target.lower())

    if data.get("unparsed_blocks"):
        warnings.append(f"unparsed_blocks exists: {len(data['unparsed_blocks'])} items")
    if data.get("unknown_keywords"):
        warnings.append(f"unknown_keywords exists: {len(data['unknown_keywords'])} items")

    return {
        "target": target,
        "model": model,
        "warnings": warnings,
        "blockers": blockers,
        "ok": not blockers,
    }
