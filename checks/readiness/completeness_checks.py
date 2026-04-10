from __future__ import annotations

from typing import Any, Dict, List


def _has_value(obj: Any) -> bool:
    if obj is None:
        return False
    if isinstance(obj, dict):
        value_type = obj.get("type")
        if value_type == "scalar":
            return obj.get("value") is not None
        if value_type == "array":
            return bool(obj.get("values"))
        if value_type == "table":
            return bool(obj.get("rows"))
        if value_type == "ref":
            return bool(obj.get("source_file"))
    return True


def _rows(obj: Any) -> list[list[Any]]:
    if isinstance(obj, dict) and obj.get("type") == "table":
        return obj.get("rows") or []
    return []


def check_meta_completeness(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    meta = data.get("meta", {}) or {}
    if not meta.get("unit_system"):
        warnings.append("meta.unit_system is missing")
    if not meta.get("source_software"):
        warnings.append("meta.source_software is missing")


def check_grid_completeness(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    grid = data.get("grid", {}) or {}
    for key in ("ni", "nj", "nk"):
        if not grid.get(key):
            blockers.append(f"grid.{key} is missing")

    grid_type = str(grid.get("grid_type", "CART")).upper()
    if grid_type == "RADIAL":
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


def check_water_properties_completeness(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    fluid = data.get("fluid", {}) or {}
    for key in ("water_fvf", "water_compressibility", "water_ref_pressure", "water_viscosity"):
        if not _has_value(fluid.get(key)):
            warnings.append(f"fluid.{key} is missing")


def check_pvt_table_shapes(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    fluid = data.get("fluid", {}) or {}
    table_specs = [
        ("fluid.pvt_table", fluid.get("pvt_table"), 6),
        ("fluid.pvto_table", fluid.get("pvto_table"), 4),
        ("fluid.pvdg_table", fluid.get("pvdg_table"), 3),
        ("fluid.pvts_table", fluid.get("pvts_table"), 5),
    ]
    for name, table_obj, expected_columns in table_specs:
        for idx, row in enumerate(_rows(table_obj)):
            if len(row) != expected_columns:
                blockers.append(f"{name}.rows[{idx}] expected {expected_columns} columns, got {len(row)}")


def check_relperm_table_shapes(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
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
    for name, table_obj, expected_columns in table_specs:
        for idx, row in enumerate(_rows(table_obj)):
            if len(row) != expected_columns:
                blockers.append(f"{name}.rows[{idx}] expected {expected_columns} columns, got {len(row)}")


def check_blackoil_completeness(
    data: Dict[str, Any],
    blockers: List[str],
    warnings: List[str],
    *,
    target: str,
) -> None:
    fluid = data.get("fluid", {}) or {}
    rockfluid = data.get("rockfluid", {}) or {}
    initial = data.get("initial", {}) or {}

    if not (
        _has_value(fluid.get("pvt_table"))
        or _has_value(fluid.get("zg_table"))
        or (_has_value(fluid.get("pvto_table")) and _has_value(fluid.get("pvdg_table")))
    ):
        blockers.append("blackoil fluid requires pvt_table or zg_table or pvto_table+pvdg_table")

    missing_densities = [key for key in ("oil_density", "water_density") if not _has_value(fluid.get(key))]
    if not (_has_value(fluid.get("gas_density")) or _has_value(fluid.get("gas_gravity"))):
        missing_densities.append("gas_density_or_gravity")
    if missing_densities:
        blockers.append("missing density fields: " + ", ".join(f"fluid.{key}" for key in missing_densities))

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


def check_miscible_completeness(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
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


def check_wells_completeness(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    wells = data.get("wells", []) or []
    timeline_events = data.get("timeline_events", []) or []
    grid = data.get("grid", {}) or {}
    ni = grid.get("ni")
    nj = grid.get("nj")
    nk = grid.get("nk")
    seen_names = set()

    for idx, well in enumerate(wells, start=1):
        name = str(well.get("well_name") or "").strip()
        if not name:
            blockers.append(f"wells[{idx-1}] missing well_name")
            continue
        if name in seen_names:
            blockers.append(f"duplicate well name: {name}")
        seen_names.add(name)

        well_type = str(well.get("well_type") or "").upper()
        if not well_type:
            warnings.append(f"well {name} missing well_type")

        perfs = well.get("perforations", []) or []
        if not perfs:
            warnings.append(f"well {name} has no perforations")
        for perf_idx, perf in enumerate(perfs):
            for key in ("i", "j", "k"):
                if perf.get(key) is None:
                    blockers.append(f"well {name} perforations[{perf_idx}] missing {key}")
            if ni and perf.get("i") is not None and not (1 <= int(perf["i"]) <= int(ni)):
                blockers.append(f"well {name} perforations[{perf_idx}].i out of grid range")
            if nj and perf.get("j") is not None and not (1 <= int(perf["j"]) <= int(nj)):
                blockers.append(f"well {name} perforations[{perf_idx}].j out of grid range")
            if nk and perf.get("k") is not None and not (1 <= int(perf["k"]) <= int(nk)):
                blockers.append(f"well {name} perforations[{perf_idx}].k out of grid range")

        if well_type == "INJECTOR":
            if not well.get("inj_fluid"):
                blockers.append(f"injector well {name} missing inj_fluid")
            elif str(well.get("inj_fluid")).upper() not in ("GAS", "WATER", "SOLVENT"):
                blockers.append(f"injector well {name} has unsupported inj_fluid={well.get('inj_fluid')}")
            if well.get("rate_max") is None and well.get("bhp_max") is None:
                warnings.append(f"injector well {name} has neither rate_max nor bhp_max")
        elif well_type == "PRODUCER":
            if well.get("rate_max") is None and well.get("bhp_min") is None:
                warnings.append(f"producer well {name} has neither rate_max nor bhp_min")
        elif well_type:
            blockers.append(f"well {name} has unsupported well_type={well_type}")

    for event_idx, event in enumerate(timeline_events):
        well_name = event.get("well_name")
        if well_name and well_name not in seen_names:
            blockers.append(f"timeline_events[{event_idx}] references unknown well {well_name}")
        if event.get("event_type") == "WELL_TARGET_CHANGE" and event.get("value") is None:
            blockers.append(f"timeline_events[{event_idx}] missing value")
