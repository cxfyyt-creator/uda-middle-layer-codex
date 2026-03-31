from __future__ import annotations

from typing import Any, Dict, List

from utils.cmg_case_dependencies import collect_case_input_files


_LAYER_ORDER = [
    "format_coverage",
    "generator_capability",
    "validation_rule",
    "completeness",
]
_REASON_TYPES = [
    "format_coverage",
    "ir_expression",
    "generator_capability",
    "validation_rule",
]


def _issue(layer: str, reason_type: str, severity: str, message: str) -> Dict[str, str]:
    return {
        "layer": layer,
        "reason_type": reason_type,
        "severity": severity,
        "message": message,
    }


def _append_messages(
    issues: List[Dict[str, str]],
    *,
    layer: str,
    reason_type: str,
    blockers: List[str],
    warnings: List[str],
) -> None:
    issues.extend(_issue(layer, reason_type, "blocker", message) for message in blockers)
    issues.extend(_issue(layer, reason_type, "warning", message) for message in warnings)


def _run_check(fn, *args, **kwargs) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    fn(*args, blockers, warnings, **kwargs)
    return blockers, warnings


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
        if t == "ref":
            return bool(obj.get("source_file"))
    return True


def _iter_ref_paths(obj: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        if obj.get("type") == "ref":
            found.append(prefix or "<root>")
        for key, value in obj.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            found.extend(_iter_ref_paths(value, child))
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            child = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            found.extend(_iter_ref_paths(value, child))
    return found


def _rows(obj: Any) -> list[list[Any]]:
    if isinstance(obj, dict) and obj.get("type") == "table":
        return obj.get("rows") or []
    return []


def _is_monotonic_non_decreasing(values: list[float]) -> bool:
    return all(values[i] <= values[i + 1] for i in range(len(values) - 1))


def _get_nested_value(data: Any, path: str) -> Any:
    current = data
    token = ""
    i = 0
    while i < len(path):
        ch = path[i]
        if ch == ".":
            if token:
                if not isinstance(current, dict):
                    return None
                current = current.get(token)
                token = ""
            i += 1
            continue
        if ch == "[":
            if token:
                if not isinstance(current, dict):
                    return None
                current = current.get(token)
                token = ""
            end = path.find("]", i)
            if end < 0:
                return None
            if not isinstance(current, list):
                return None
            try:
                current = current[int(path[i + 1:end])]
            except (ValueError, IndexError):
                return None
            i = end + 1
            continue
        token += ch
        i += 1

    if token:
        if not isinstance(current, dict):
            return None
        current = current.get(token)
    return current


def _is_supported_cmg_ref(obj: Any) -> bool:
    if not isinstance(obj, dict) or obj.get("type") != "ref":
        return False

    hint = obj.get("source_format_hint") or {}
    if str(hint.get("keyword", "")).upper() == "*EQUALSI":
        return True

    ref_format = str(obj.get("format", "")).upper()
    return ref_format in {"SIP_DATA", "BINARY_DATA"}


def _extract_numeric_values(obj: Any) -> list[float]:
    if not isinstance(obj, dict):
        return []
    if obj.get("type") == "scalar":
        try:
            return [float(obj.get("value"))]
        except (TypeError, ValueError):
            return []
    if obj.get("type") == "array":
        values = obj.get("values") or []
        out: list[float] = []
        for value in values:
            try:
                out.append(float(value))
            except (TypeError, ValueError):
                continue
        return out
    return []


def _build_active_mask_from_data(data: Dict[str, Any]) -> list[bool]:
    grid = data.get("grid", {}) or {}
    active_values = _extract_numeric_values(grid.get("active_cell_mask"))
    pinch_values = _extract_numeric_values(grid.get("pinchout_array"))
    size = max(len(active_values), len(pinch_values))
    if size == 0:
        return []

    mask = [True] * size
    if active_values:
        if len(active_values) == 1 and size > 1:
            active_values = active_values * size
        for idx, value in enumerate(active_values[:size]):
            mask[idx] = mask[idx] and float(value) > 0.0
    if pinch_values:
        if len(pinch_values) == 1 and size > 1:
            pinch_values = pinch_values * size
        for idx, value in enumerate(pinch_values[:size]):
            mask[idx] = mask[idx] and float(value) > 0.0
    return mask


def _check_reservoir_physics(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    reservoir = data.get("reservoir", {}) or {}
    porosity = reservoir.get("porosity")
    values = _extract_numeric_values(porosity)
    if values:
        active_mask = _build_active_mask_from_data(data)
        zero_active = 0
        out_of_range: list[float] = []
        for idx, value in enumerate(values):
            if value < 0.0 or value > 0.60:
                out_of_range.append(value)
                continue
            is_active = active_mask[idx] if idx < len(active_mask) else True
            if value == 0.0 and is_active:
                zero_active += 1
        if out_of_range:
            blockers.append(f"reservoir.porosity has values out of [0,0.60]: {out_of_range[:5]}")
        if zero_active:
            blockers.append(f"reservoir.porosity has {zero_active} active cells with zero porosity")


def _check_meta_completeness(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    meta = data.get("meta", {}) or {}
    if not meta.get("unit_system"):
        warnings.append("meta.unit_system is missing")
    if not meta.get("source_software"):
        warnings.append("meta.source_software is missing")


def _check_grid_completeness(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
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


def _check_water_properties_completeness(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    fluid = data.get("fluid", {}) or {}
    for key in ("water_fvf", "water_compressibility", "water_ref_pressure", "water_viscosity"):
        if not _has_value(fluid.get(key)):
            warnings.append(f"fluid.{key} is missing")


def _check_pvt_table_shapes(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    fluid = data.get("fluid", {}) or {}
    table_specs = [
        ("fluid.pvt_table", fluid.get("pvt_table"), 6),
        ("fluid.pvto_table", fluid.get("pvto_table"), 4),
        ("fluid.pvdg_table", fluid.get("pvdg_table"), 3),
        ("fluid.pvts_table", fluid.get("pvts_table"), 5),
    ]
    for name, tbl, expected in table_specs:
        rows = _rows(tbl)
        for idx, row in enumerate(rows):
            if len(row) != expected:
                blockers.append(f"{name}.rows[{idx}] expected {expected} columns, got {len(row)}")


def _check_pvt_table_physics(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    fluid = data.get("fluid", {}) or {}

    pvt = fluid.get("pvt_table")
    rows = _rows(pvt)
    if rows:
        ps = [float(r[0]) for r in rows if len(r) >= 1]
        if ps and not _is_monotonic_non_decreasing(ps):
            warnings.append("fluid.pvt_table pressure column is not monotonic non-decreasing")

    pvto = fluid.get("pvto_table")
    rows = _rows(pvto)
    if rows:
        by_rs: Dict[float, list[float]] = {}
        for row in rows:
            if len(row) >= 2:
                by_rs.setdefault(float(row[0]), []).append(float(row[1]))
        for rs, ps in by_rs.items():
            if not _is_monotonic_non_decreasing(ps):
                warnings.append(f"fluid.pvto_table pressures are not monotonic inside rs={rs}")

    pvdg = fluid.get("pvdg_table")
    rows = _rows(pvdg)
    if rows:
        ps = [float(r[0]) for r in rows if len(r) >= 1]
        if ps and not _is_monotonic_non_decreasing(ps):
            warnings.append("fluid.pvdg_table pressure column is not monotonic non-decreasing")

    pvts = fluid.get("pvts_table")
    rows = _rows(pvts)
    if rows:
        ps = [float(r[0]) for r in rows if len(r) >= 1]
        if ps and not _is_monotonic_non_decreasing(ps):
            warnings.append("fluid.pvts_table pressure column is not monotonic non-decreasing")


def _check_relperm_table_shapes(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    rockfluid = data.get("rockfluid", {}) or {}
    table_specs = [
        ("rockfluid.swt_table", rockfluid.get("swt_table"), 4),
        ("rockfluid.slt_table", rockfluid.get("slt_table"), 4),
        ("rockfluid.swof_table", rockfluid.get("swof_table"), 4),
        ("rockfluid.sgof_table", rockfluid.get("sgof_table"), 4),
        ("rockfluid.swfn_table", rockfluid.get("swfn_table"), 3),
        ("rockfluid.sgfn_table", rockfluid.get("sgfn_table"), 3),
        ("rockfluid.sof2_table", rockfluid.get("sof2_table"), 2),
        ("rockfluid.sof3_table", rockfluid.get("sof3_table"), 3),
    ]
    for name, tbl, expected in table_specs:
        rows = _rows(tbl)
        for idx, row in enumerate(rows):
            if len(row) != expected:
                blockers.append(f"{name}.rows[{idx}] expected {expected} columns, got {len(row)}")


def _check_relperm_table_physics(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    rockfluid = data.get("rockfluid", {}) or {}
    table_specs = [
        ("rockfluid.swt_table", rockfluid.get("swt_table"), 0),
        ("rockfluid.slt_table", rockfluid.get("slt_table"), 0),
        ("rockfluid.swof_table", rockfluid.get("swof_table"), 0),
        ("rockfluid.sgof_table", rockfluid.get("sgof_table"), 0),
        ("rockfluid.swfn_table", rockfluid.get("swfn_table"), 0),
        ("rockfluid.sgfn_table", rockfluid.get("sgfn_table"), 0),
        ("rockfluid.sof2_table", rockfluid.get("sof2_table"), 0),
        ("rockfluid.sof3_table", rockfluid.get("sof3_table"), 0),
    ]

    for name, tbl, sat_col in table_specs:
        rows = _rows(tbl)
        if not rows:
            continue
        sats = [float(r[sat_col]) for r in rows if len(r) > sat_col]
        if sats and not _is_monotonic_non_decreasing(sats):
            warnings.append(f"{name} saturation column is not monotonic non-decreasing")
        for idx, sat in enumerate(sats):
            if not (0.0 <= sat <= 1.0):
                blockers.append(f"{name}.rows[{idx}] saturation value {sat} out of [0,1]")


def _check_blackoil_completeness(data: Dict[str, Any], blockers: List[str], warnings: List[str], *, target: str) -> None:
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


def _check_blackoil_validation(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    fluid = data.get("fluid", {}) or {}
    initial = data.get("initial", {}) or {}

    for key in ("oil_density", "gas_density", "water_density"):
        obj = fluid.get(key)
        if _has_value(obj) and float(obj.get("value", 0.0)) <= 0:
            blockers.append(f"fluid.{key} must be positive")
    if _has_value(fluid.get("gas_gravity")) and float(fluid["gas_gravity"].get("value", 0.0)) <= 0:
        blockers.append("fluid.gas_gravity must be positive")
    if _has_value(initial.get("goc_depth")) and _has_value(initial.get("woc_depth")):
        if float(initial["goc_depth"]["value"]) >= float(initial["woc_depth"]["value"]):
            blockers.append("initial.goc_depth should be shallower than initial.woc_depth")


def _check_miscible_completeness(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
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


def _check_wells_completeness(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
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
        elif wtype == "PRODUCER":
            if w.get("rate_max") is None and w.get("bhp_min") is None:
                warnings.append(f"producer well {name} has neither rate_max nor bhp_min")
        elif wtype:
            blockers.append(f"well {name} has unsupported well_type={wtype}")

    for ev_idx, ev in enumerate(timeline_events):
        wname = ev.get("well_name")
        if wname and wname not in seen_names:
            blockers.append(f"timeline_events[{ev_idx}] references unknown well {wname}")
        if ev.get("event_type") == "WELL_TARGET_CHANGE" and ev.get("value") is None:
            blockers.append(f"timeline_events[{ev_idx}] missing value")


def _check_wells_validation(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    wells = data.get("wells", []) or []
    timeline_events = data.get("timeline_events", []) or []

    for w in wells:
        name = str(w.get("well_name") or "<unnamed>").strip()
        wtype = str(w.get("well_type") or "").upper()
        if wtype == "INJECTOR" and w.get("bhp_min") is not None:
            warnings.append(f"injector well {name} has bhp_min which is unusual")
        if wtype == "PRODUCER" and w.get("bhp_max") is not None:
            warnings.append(f"producer well {name} has bhp_max which is unusual")
        if w.get("rate_max") is not None and float(w.get("rate_max")) <= 0:
            warnings.append(f"well {name} has non-positive rate_max")
        if w.get("bhp_max") is not None and float(w.get("bhp_max")) <= 0:
            warnings.append(f"well {name} has non-positive bhp_max")
        if w.get("bhp_min") is not None and float(w.get("bhp_min")) <= 0:
            warnings.append(f"well {name} has non-positive bhp_min")

    for ev_idx, ev in enumerate(timeline_events):
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

    inputs = collect_case_input_files(data)
    if inputs:
        warnings.append(f"cmg case inputs detected: {len(inputs)}")

    for item in inputs:
        if item.get("exists") is False and item.get("required", True):
            path = item.get("path") or item.get("source_path") or "<unknown>"
            producer_case = item.get("producer_case")
            producer_artifact = item.get("producer_artifact")
            if producer_case or producer_artifact:
                detail = []
                if producer_case:
                    detail.append(f"upstream case {producer_case}")
                if producer_artifact:
                    detail.append(f"expected artifact {producer_artifact}")
                blockers.append(f"missing required CMG runtime input: {path} ({', '.join(detail)})")
            else:
                blockers.append(f"missing required CMG runtime input: {path}")


def _check_ref_support(data: Dict[str, Any], blockers: List[str], warnings: List[str], *, target: str) -> None:
    ref_paths = _iter_ref_paths(data)
    if not ref_paths:
        return

    warnings.append(f"ir ref values detected: {len(ref_paths)}")
    meta = data.get("meta", {}) or {}
    source_faithful_cmg = (
        target == "cmg"
        and str(meta.get("source_software", "")).lower() == "cmg_imex"
        and meta.get("_cmg_roundtrip_mode") == "source_faithful"
    )
    if source_faithful_cmg:
        return

    if target == "cmg":
        unsupported: list[str] = []
        for path in ref_paths:
            obj = _get_nested_value(data, path)
            if not _is_supported_cmg_ref(obj):
                unsupported.append(path)
        if not unsupported:
            return
        ref_paths = unsupported

    sample = ", ".join(ref_paths[:5])
    blockers.append(
        "structured backend does not yet support ref values: "
        + sample
        + (f" (+{len(ref_paths) - 5} more)" if len(ref_paths) > 5 else "")
    )


def _run_format_coverage_checks(data: Dict[str, Any]) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    if data.get("unknown_keywords"):
        issues.append(_issue(
            "format_coverage",
            "format_coverage",
            "warning",
            f"unknown_keywords exists: {len(data['unknown_keywords'])} items",
        ))
    if data.get("unparsed_blocks"):
        issues.append(_issue(
            "format_coverage",
            "format_coverage",
            "warning",
            f"unparsed_blocks exists: {len(data['unparsed_blocks'])} items",
        ))
    return issues


def _run_generator_capability_checks(data: Dict[str, Any], *, target: str, model: str) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    blockers, warnings = _run_check(_check_schedule_support, data, target=target)
    _append_messages(issues, layer="generator_capability", reason_type="generator_capability", blockers=blockers, warnings=warnings)

    blockers, warnings = _run_check(_check_ref_support, data, target=target)
    _append_messages(issues, layer="generator_capability", reason_type="generator_capability", blockers=blockers, warnings=warnings)

    if model.startswith("MIS") and target == "petrel":
        issues.append(_issue(
            "generator_capability",
            "generator_capability",
            "blocker",
            "current Petrel backend does not support miscible export",
        ))
    return issues


def _run_validation_rule_checks(data: Dict[str, Any], *, model: str) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for fn in (_check_pvt_table_physics, _check_relperm_table_physics, _check_reservoir_physics, _check_wells_validation):
        blockers, warnings = _run_check(fn, data)
        _append_messages(issues, layer="validation_rule", reason_type="validation_rule", blockers=blockers, warnings=warnings)

    if model.startswith("MIS"):
        return issues

    blockers, warnings = _run_check(_check_blackoil_validation, data)
    _append_messages(issues, layer="validation_rule", reason_type="validation_rule", blockers=blockers, warnings=warnings)
    return issues


def _run_completeness_checks(data: Dict[str, Any], *, target: str, model: str) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    for fn in (
        _check_meta_completeness,
        _check_grid_completeness,
        _check_water_properties_completeness,
        _check_pvt_table_shapes,
        _check_relperm_table_shapes,
        _check_wells_completeness,
    ):
        blockers, warnings = _run_check(fn, data)
        _append_messages(issues, layer="completeness", reason_type="ir_expression", blockers=blockers, warnings=warnings)

    blockers, warnings = _run_check(_check_case_runtime_dependencies, data, target=target)
    _append_messages(issues, layer="completeness", reason_type="generator_capability", blockers=blockers, warnings=warnings)

    if model.startswith("MIS"):
        blockers, warnings = _run_check(_check_miscible_completeness, data)
    else:
        blockers, warnings = _run_check(_check_blackoil_completeness, data, target=target)
    _append_messages(issues, layer="completeness", reason_type="ir_expression", blockers=blockers, warnings=warnings)
    return issues


def _build_layer_view(issues: List[Dict[str, str]]) -> Dict[str, Dict[str, Any]]:
    view: Dict[str, Dict[str, Any]] = {}
    for layer in _LAYER_ORDER:
        layer_issues = [item for item in issues if item["layer"] == layer]
        view[layer] = {
            "ok": not any(item["severity"] == "blocker" for item in layer_issues),
            "blockers": [item["message"] for item in layer_issues if item["severity"] == "blocker"],
            "warnings": [item["message"] for item in layer_issues if item["severity"] == "warning"],
            "issues": layer_issues,
        }
    return view


def _build_reason_summary(issues: List[Dict[str, str]]) -> Dict[str, Dict[str, int]]:
    summary: Dict[str, Dict[str, int]] = {}
    for reason_type in _REASON_TYPES:
        type_issues = [item for item in issues if item["reason_type"] == reason_type]
        summary[reason_type] = {
            "blockers": sum(1 for item in type_issues if item["severity"] == "blocker"),
            "warnings": sum(1 for item in type_issues if item["severity"] == "warning"),
            "total": len(type_issues),
        }
    return summary


def evaluate_target_preflight(data: Dict[str, Any], *, target: str) -> Dict[str, Any]:
    fluid = data.get("fluid", {}) or {}
    model = str(fluid.get("model", "BLACKOIL")).upper()
    normalized_target = target.lower()

    issues: List[Dict[str, str]] = []
    issues.extend(_run_format_coverage_checks(data))
    issues.extend(_run_generator_capability_checks(data, target=normalized_target, model=model))
    issues.extend(_run_validation_rule_checks(data, model=model))
    issues.extend(_run_completeness_checks(data, target=normalized_target, model=model))

    blockers = [item["message"] for item in issues if item["severity"] == "blocker"]
    warnings = [item["message"] for item in issues if item["severity"] == "warning"]

    return {
        "target": target,
        "model": model,
        "warnings": warnings,
        "blockers": blockers,
        "ok": not blockers,
        "issues": issues,
        "layers": _build_layer_view(issues),
        "reason_summary": _build_reason_summary(issues),
    }
