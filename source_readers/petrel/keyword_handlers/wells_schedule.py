from __future__ import annotations

import re

from source_readers.petrel.value_builders import to_float


def parse_welspecs(parser, R):
    parser._skip_rest_of_kw_line(parser._last_lineno())
    while parser._peek():
        _, tok = parser._peek()
        if tok.startswith("'"):
            break
        if tok == "/":
            parser.pos += 1
            break
        parser.pos += 1

    while parser._peek():
        row = parser._read_until_slash()
        if not row:
            break
        strs = [str(t).strip("'") for t in row]
        if len(strs) < 4:
            continue
        name = strs[0].strip()
        group = strs[1]
        try:
            ci = int(strs[2])
            cj = int(strs[3])
        except ValueError:
            continue
        phase = parser._normalize_phase_or_fluid(strs[5] if len(strs) > 5 else "OIL") or "OIL"
        wtype = "PRODUCER" if phase == "OIL" else None
        existing = parser._find_well(name, R)
        if existing is None:
            R["wells"].append(
                {
                    "well_name": name,
                    "well_type": wtype,
                    "well_group": group,
                    "well_i": ci,
                    "well_j": cj,
                    "phase": phase,
                    "bhp_max": None,
                    "bhp_min": None,
                    "rate_max": None,
                    "rate_min": None,
                    "perforations": [],
                    "well_radius": None,
                    "inj_fluid": None,
                    "alter_schedule": [],
                    "source": "SCHEDULE WELSPECS",
                }
            )
        else:
            existing.update(
                {
                    "well_group": group,
                    "well_i": ci,
                    "well_j": cj,
                    "phase": phase,
                    "source": "SCHEDULE WELSPECS",
                }
            )
            if wtype and not existing.get("well_type"):
                existing["well_type"] = wtype


def parse_compdat(parser, R):
    parser._skip_rest_of_kw_line(parser._last_lineno())
    while parser._peek():
        row = parser._read_until_slash()
        if not row:
            break
        strs = [str(t).strip("'") for t in row]
        if len(strs) < 5:
            continue
        name = strs[0].strip()
        well = parser._find_well(name, R)
        if well is None:
            continue
        fields = []
        for token in strs[1:]:
            match = re.match(r"^(\d+)\*$", token)
            if match:
                fields.extend([None] * int(match.group(1)))
            else:
                fields.append(token)
        if len(fields) < 5:
            continue
        try:
            pi = well.get("well_i") if fields[0] is None else int(fields[0])
            pj = well.get("well_j") if fields[1] is None else int(fields[1])
            k1 = int(fields[2])
            k2 = int(fields[3])
        except (ValueError, TypeError):
            continue
        status = str(fields[4] or "OPEN").upper()
        diam = None
        for field in fields[5:]:
            if field is None or re.match(r"^\d+\*$", str(field)):
                continue
            try:
                diam = to_float(field)
                break
            except ValueError:
                continue
        if diam is not None and diam > 0:
            well["well_radius"] = diam / 2.0
        for k in range(k1, k2 + 1):
            well["perforations"].append({"i": pi, "j": pj, "k": k, "wi": -1.0, "status": status, "perf_type": "COMPDAT"})


def _get_optional_value(strs, idx):
    if idx >= len(strs):
        return None
    raw = strs[idx]
    if re.match(r"^\d+\*$", raw):
        return None
    try:
        return to_float(raw)
    except ValueError:
        return None


def parse_wconprod(parser, R):
    parser._skip_rest_of_kw_line(parser._last_lineno())
    while parser._peek():
        row = parser._read_until_slash()
        if not row:
            break
        strs = [str(t).strip("'") for t in row]
        if len(strs) < 3:
            continue
        name = strs[0].strip()
        wells = parser._find_wells(name, R)
        if not wells:
            continue
        oil = _get_optional_value(strs, 3)
        bhp = _get_optional_value(strs, 8)
        for well in wells:
            well["well_type"] = "PRODUCER"
            if oil is not None and oil > 0:
                well["rate_max"] = oil
            if bhp is not None:
                well["bhp_min"] = bhp


def parse_wconinje(parser, R):
    parser._skip_rest_of_kw_line(parser._last_lineno())
    while parser._peek():
        row = parser._read_until_slash()
        if not row:
            break
        strs = [str(t).strip("'") for t in row]
        if len(strs) < 4:
            continue
        name = strs[0].strip()
        inj_type = parser._normalize_phase_or_fluid(strs[1] if len(strs) > 1 else "GAS") or "GAS"
        wells = parser._find_wells(name, R)
        if not wells:
            continue
        rate = _get_optional_value(strs, 4)
        bhp = _get_optional_value(strs, 6)
        for well in wells:
            well["well_type"] = "INJECTOR"
            well["inj_fluid"] = inj_type
            if rate is not None and rate > 0:
                well["rate_max"] = rate
            if bhp is not None:
                well["bhp_max"] = bhp


def parse_weltarg(parser, R):
    parser._skip_rest_of_kw_line(parser._last_lineno())
    while parser._peek():
        row = parser._read_until_slash()
        if not row:
            break
        strs = [str(t).strip("'") for t in row]
        if len(strs) < 3:
            continue
        name = strs[0].strip()
        target = strs[1].upper()
        try:
            value = to_float(strs[2])
        except (ValueError, IndexError):
            continue
        for well in parser._find_wells(name, R):
            well["alter_schedule"].append({"target": target, "value": value, "time": parser._current_time})


def parse_tstep(parser, R):
    vals = parser._read_floats_until_slash()
    for dt in vals:
        parser._current_time += dt
        parser._time_checkpoints.append(parser._current_time)


def parse_dates(parser, R):
    row = parser._read_until_slash()
    strs = [str(t).strip("'") for t in row]
    if len(strs) >= 3:
        try:
            dy = int(strs[0])
            mon = parser._MONTH_MAP.get(strs[1].upper()[:3], 1)
            yr = int(strs[2])
            R["meta"].setdefault("schedule_dates", []).append(f"{yr:04d}-{mon:02d}-{dy:02d}")
        except (ValueError, IndexError):
            pass
