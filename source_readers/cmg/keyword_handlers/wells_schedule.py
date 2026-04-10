from __future__ import annotations

from source_readers.cmg.token_stream import is_kw
from source_readers.cmg.value_builders import to_float


def parse_well(parser, R, in_run_section):
    lineno = parser._last_lineno()
    tokens = parser._read_same_line_tokens(lineno)
    selector = []
    name = None
    vert = None
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        expanded = parser._expand_int_token(tok)
        if expanded and not selector:
            selector = expanded
            i += 1
            continue
        if tok.startswith("'") and tok.endswith("'") and name is None:
            name = tok.strip("'")
            i += 1
            continue
        if tok.upper() == "*VERT" and i + 2 < len(tokens):
            try:
                vert = (int(float(tokens[i + 1])), int(float(tokens[i + 2])))
                i += 3
                continue
            except ValueError:
                pass
        i += 1

    well_index = selector[0] if selector else len(R["wells"]) + 1
    well = parser._ensure_well(R, well_index, name)
    if name:
        well["well_name"] = name
    if vert:
        well["well_i"], well["well_j"] = vert
    parser.active_well_indices = [well_index]


def parse_producer(parser, R, in_run_section):
    if not in_run_section or not R["wells"]:
        return

    lineno = parser._last_lineno()
    tokens = parser._read_same_line_tokens(lineno)
    selector = []
    for tok in tokens:
        expanded = parser._expand_int_token(tok)
        if expanded:
            selector = expanded
            break
    wells = parser._wells_for_selector(R, selector)
    for well in wells:
        well["well_type"] = "PRODUCER"
    parser.active_well_indices = [w["well_index"] for w in wells]


def parse_injector(parser, R, in_run_section):
    if not in_run_section or not R["wells"]:
        return

    lineno = parser._last_lineno()
    tokens = parser._read_same_line_tokens(lineno)
    selector = []
    for tok in tokens:
        expanded = parser._expand_int_token(tok)
        if expanded:
            selector = expanded
            break
    wells = parser._wells_for_selector(R, selector)
    for well in wells:
        well["well_type"] = "INJECTOR"
    parser.active_well_indices = [w["well_index"] for w in wells]


def parse_incomp(parser, R, in_run_section):
    if not in_run_section or not R["wells"]:
        return

    lineno = parser._last_lineno()
    tokens = parser._read_same_line_tokens(lineno)
    fluid_kw = next((tok for tok in tokens if is_kw(tok)), None)
    if fluid_kw:
        for well in parser._wells_for_selector(R):
            well["inj_fluid"] = fluid_kw.lstrip("*").upper()


def parse_operate(parser, R, in_run_section):
    if not in_run_section or not R["wells"]:
        return

    lineno = parser._last_lineno()
    parts = parser._read_same_line_tokens(lineno)

    mode = None
    target = None
    value = None
    for part in parts:
        part_upper = part.upper()
        if part_upper in ("*MAX", "*MIN"):
            mode = part_upper.lstrip("*")
        elif part_upper in ("*BHP", "*STO", "*STG", "*STW", "*RESV"):
            target = part_upper.lstrip("*")
        else:
            try:
                value = to_float(part)
            except ValueError:
                pass
    if target and value is not None:
        for well in parser._wells_for_selector(R):
            if target == "BHP":
                if mode == "MAX":
                    well["bhp_max"] = value
                else:
                    well["bhp_min"] = value
            elif target in ("STO", "STG", "STW"):
                if mode == "MAX":
                    well["rate_max"] = value


def parse_perf(parser, R, in_run_section, perf_kw="*PERF"):
    if not in_run_section or not R["wells"]:
        return

    lineno = parser._last_lineno()
    header_tokens = parser._read_same_line_tokens(lineno)
    selector = []
    use_geo = False
    for tok in header_tokens:
        if tok.upper() == "*GEO":
            use_geo = True
            continue
        expanded = parser._expand_int_token(tok)
        if expanded:
            selector = expanded
            break

    wells = parser._wells_for_selector(R, selector)
    if use_geo and parser.last_geometry:
        for well in wells:
            well["well_radius"] = parser.last_geometry.get("well_radius")
            well["geofac"] = parser.last_geometry.get("geofac")
            well["wfrac"] = parser.last_geometry.get("wfrac")
            well["skin"] = parser.last_geometry.get("skin")

    while parser._peek() and not is_kw(parser._peek()[1]):
        row_lineno = parser._peek()[0]
        row_tokens = parser._read_same_line_tokens(row_lineno)
        if not row_tokens:
            continue

        if perf_kw == "*PERFV":
            k_vals = parser._expand_int_token(row_tokens[0]) or []
            try:
                wi = to_float(row_tokens[1]) if len(row_tokens) > 1 else -1.0
            except ValueError:
                wi = -1.0
            if wi <= 0:
                wi = -1.0
            for well in wells:
                well_i = well.get("well_i")
                well_j = well.get("well_j")
                if well_i is None or well_j is None:
                    continue
                for k in k_vals:
                    well["perforations"].append(
                        {
                            "i": int(well_i),
                            "j": int(well_j),
                            "k": int(k),
                            "wi": wi,
                            "perf_type": perf_kw.lstrip("*"),
                        }
                    )
            continue

        if len(row_tokens) < 3:
            break
        i_vals = parser._expand_int_token(row_tokens[0]) or []
        j_vals = parser._expand_int_token(row_tokens[1]) or []
        k_vals = parser._expand_int_token(row_tokens[2]) or []
        try:
            wi = to_float(row_tokens[3]) if len(row_tokens) > 3 else -1.0
        except ValueError:
            wi = -1.0
        if wi <= 0:
            wi = -1.0
        for well in wells:
            for ii in i_vals:
                for jj in j_vals:
                    for kk in k_vals:
                        well["perforations"].append(
                            {
                                "i": int(ii),
                                "j": int(jj),
                                "k": int(kk),
                                "wi": wi,
                                "perf_type": perf_kw.lstrip("*"),
                            }
                        )


def parse_perfv(parser, R, in_run_section):
    parse_perf(parser, R, in_run_section, "*PERFV")


def parse_geometry(parser, R, in_run_section):
    if not in_run_section:
        return

    lineno = parser._last_lineno()
    tokens = parser._read_same_line_tokens(lineno)
    nums = []
    for tok in tokens:
        if is_kw(tok):
            continue
        try:
            nums.append(to_float(tok))
        except ValueError:
            pass
    if nums:
        geom = {
            "well_radius": nums[0],
            "geofac": nums[1] if len(nums) > 1 else None,
            "wfrac": nums[2] if len(nums) > 2 else None,
            "skin": nums[3] if len(nums) > 3 else None,
        }
        parser.last_geometry = geom
        parser.default_geometry = geom
        for well in parser._wells_for_selector(R):
            well["well_radius"] = geom["well_radius"]
            if geom["geofac"] is not None:
                well["geofac"] = geom["geofac"]
            if geom["wfrac"] is not None:
                well["wfrac"] = geom["wfrac"]
            if geom["skin"] is not None:
                well["skin"] = geom["skin"]


def parse_alter(parser, R, in_run_section):
    if not in_run_section or not R["wells"]:
        return

    lineno = parser._last_lineno()
    raw_tokens = parser._read_same_line_tokens(lineno)
    raw_tokens.extend(parser._collect_numeric_tokens_until_kw())

    selector = []
    if raw_tokens:
        maybe_selector = parser._expand_int_token(raw_tokens[0])
        if maybe_selector and len(raw_tokens) > 1:
            selector = maybe_selector
            raw_tokens = raw_tokens[1:]

    values = parser._expand_numeric_tokens(raw_tokens)
    well_indices = parser._resolve_well_indices(R, selector)
    if not well_indices or not values:
        return

    if len(values) == 1:
        values = values * len(well_indices)
    elif len(values) < len(well_indices):
        values.extend([values[-1]] * (len(well_indices) - len(values)))

    for idx, new_rate in zip(well_indices, values):
        well = parser._find_well(R, idx)
        if well is None:
            continue
        well["alter_schedule"].append({"time": R.get("_current_time", 0.0), "rate": new_rate})


def parse_well_status_action(parser, R, in_run_section, action):
    if not in_run_section or not R["wells"]:
        return

    lineno = parser._last_lineno()
    tokens = parser._read_same_line_tokens(lineno)
    selector = []
    for tok in tokens:
        expanded = parser._expand_int_token(tok)
        if expanded:
            selector = expanded
            break

    for well in parser._wells_for_selector(R, selector):
        well.setdefault("status_schedule", []).append({"time": R.get("_current_time", 0.0), "action": action})


def parse_open(parser, R, in_run_section):
    parse_well_status_action(parser, R, in_run_section, "OPEN")


def parse_shutin(parser, R, in_run_section):
    parse_well_status_action(parser, R, in_run_section, "SHUTIN")


def parse_control_directive(parser, R, in_run_section=None):
    lineno = parser._last_lineno()
    keyword = parser.tokens[parser.pos - 1][1].upper() if parser.pos > 0 else ""
    tokens = parser._read_same_line_tokens(lineno)
    bucket = R.setdefault("numerical", {}).setdefault("_cmg_control_directives", [])
    bucket.append({"keyword": keyword, "line": lineno, "tokens": [str(t) for t in tokens], "time": R.get("_current_time", 0.0)})


def parse_solver_directive(parser, R, in_run_section=None):
    lineno = parser._last_lineno()
    keyword = parser.tokens[parser.pos - 1][1].upper() if parser.pos > 0 else ""
    tokens = parser._read_same_line_tokens(lineno)
    bucket = R.setdefault("numerical", {}).setdefault("_cmg_solver_directives", [])
    bucket.append({"keyword": keyword, "line": lineno, "tokens": [str(t) for t in tokens], "time": R.get("_current_time", 0.0)})


def parse_equalsi(parser, R):
    lineno = parser._last_lineno()
    tokens = parser._read_same_line_tokens(lineno)
    bucket = R.setdefault("reservoir", {}).setdefault("_cmg_equalities", [])
    bucket.append({"keyword": "*EQUALSI", "line": lineno, "tokens": [str(t) for t in tokens]})


def parse_grid_directive(parser, R):
    lineno = parser._last_lineno()
    keyword = parser.tokens[parser.pos - 1][1].upper() if parser.pos > 0 else ""
    tokens = parser._read_same_line_tokens(lineno)
    bucket = R.setdefault("grid", {}).setdefault("_cmg_grid_directives", [])
    bucket.append({"keyword": keyword, "line": lineno, "tokens": [str(t) for t in tokens]})


def parse_time(parser, R, in_run_section):
    if not in_run_section:
        return
    token = parser._peek()
    if token and not is_kw(token[1]):
        try:
            R["_current_time"] = to_float(token[1])
            parser.pos += 1
        except ValueError:
            pass


def parse_date(parser, R, in_run_section):
    if not in_run_section:
        return
    parts = []
    for _ in range(3):
        token = parser._peek()
        if token and not is_kw(token[1]):
            parts.append(token[1])
            parser.pos += 1
        else:
            break
    if len(parts) == 3:
        R["meta"]["start_date"] = "-".join(parts)
