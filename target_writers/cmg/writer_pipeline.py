from datetime import datetime

from domain_logic import compute_depth_from_tops, reorder_k_array, should_reverse_k_layers
from infra.registry_loader import get_loader
from infra.value_semantics import modifier_from_distribution


def _fmt(v, width=14):
    if isinstance(v, int):
        return str(v).rjust(width)
    if abs(v) >= 1e5 or (abs(v) < 1e-3 and v != 0):
        return f"{v:.6E}".rjust(width)
    return f"{v:.6g}".rjust(width)


def _get_val(obj):
    if obj is None:
        return None
    if isinstance(obj, dict):
        if obj.get("type") == "scalar":
            return obj["value"]
        if obj.get("type") == "array":
            return obj["values"]
    return obj


def _get_modifier(obj):
    if isinstance(obj, dict):
        return obj.get("modifier") or modifier_from_distribution(obj)
    return None


def _get_equalsi_scale(obj):
    if not isinstance(obj, dict):
        return None
    if obj.get("type") == "ref" and str(obj.get("relation", "")).upper() == "EQUALSI":
        return float(obj.get("scale", 1.0) or 1.0)
    hint = obj.get("source_format_hint") or {}
    if str(hint.get("keyword", "")).upper() == "*EQUALSI":
        return float(hint.get("scale", 1.0) or 1.0)
    return None


def _get_ref_write_mode(obj):
    if not isinstance(obj, dict) or obj.get("type") != "ref":
        return None
    hint = obj.get("source_format_hint") or {}
    hint_keyword = str(hint.get("keyword", "")).upper()
    if hint_keyword == "*EQUALSI":
        scale = hint.get("scale", obj.get("scale", 1.0))
        return {"mode": "equalsi", "scale": float(scale or 1.0)}
    ref_format = str(obj.get("format", "")).upper()
    if ref_format in {"SIP_DATA", "BINARY_DATA"}:
        return {"mode": "external_dataset", "format": ref_format}
    return None


def _write_array(lines, keyword, obj):
    if obj is None:
        return
    t = obj.get("type") if isinstance(obj, dict) else None
    if t == "ref":
        ref_mode = _get_ref_write_mode(obj)
        if not ref_mode:
            raise ValueError(
                f"Structured CMG writer does not yet support ref value for {keyword}: "
                f"{obj.get('format') or 'UNKNOWN'} -> {obj.get('source_file') or '<unknown>'}"
            )
        if ref_mode["mode"] == "equalsi":
            scale = float(ref_mode.get("scale", 1.0) or 1.0)
            if abs(scale - 1.0) < 1e-12:
                lines.append(f"{keyword} *EQUALSI")
            else:
                lines.append(f"{keyword} *EQUALSI * {_fmt(scale).strip()}")
            return
        if ref_mode["mode"] == "external_dataset":
            lines.append(f"{keyword} {ref_mode['format']}")
            return
    equalsi_scale = _get_equalsi_scale(obj)
    if equalsi_scale is not None:
        if abs(equalsi_scale - 1.0) < 1e-12:
            lines.append(f"{keyword} *EQUALSI")
        else:
            lines.append(f"{keyword} *EQUALSI * {_fmt(equalsi_scale).strip()}")
        return
    mod = _get_modifier(obj)
    val = _get_val(obj)
    if t == "scalar" or (t == "array" and mod == "CON"):
        v = val if t == "scalar" else (val[0] if isinstance(val, list) else val)
        lines.append(f"{keyword} *CON  {_fmt(v).strip()}")
    elif t == "array" and mod in (None, "KVAR", "IVAR", "JVAR", "ALL"):
        cmg_mod = f"*{mod}" if mod else ""
        if mod == "KVAR" or (mod is None and isinstance(val, list)):
            mod_str = "*KVAR" if mod == "KVAR" else ""
            lines.append(f"{keyword}{' ' + mod_str if mod_str else ''}")
        else:
            lines.append(f"{keyword} {cmg_mod}".strip())
        if isinstance(val, list):
            row = ""
            for i, v in enumerate(val):
                row += f"  {_fmt(v).strip()}"
                if (i + 1) % 10 == 0:
                    lines.append(row)
                    row = ""
            if row:
                lines.append(row)
    else:
        if isinstance(val, list):
            lines.append(f"{keyword} *KVAR")
            row = ""
            for i, v in enumerate(val):
                row += f"  {_fmt(v).strip()}"
                if (i + 1) % 10 == 0:
                    lines.append(row)
                    row = ""
            if row:
                lines.append(row)
        elif val is not None:
            lines.append(f"{keyword} *CON  {_fmt(val).strip()}")


class CMGWriter:
    def __init__(self):
        self._rl = get_loader()
        self._gen_cfg = self._rl.cmg_gen_config()

    def _write_case_manifest_inputs(self, lines, case_manifest):
        if not isinstance(case_manifest, dict):
            return
        mapping = {"SIPDATA-IN": "SIPDATA-IN", "BINDATA-IN": "BINDATA-IN", "INCLUDE": "INCLUDE"}
        emitted = set()
        manifest_lines = []
        for item in case_manifest.get("static_inputs", []) or []:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind", "")).upper()
            path = str(item.get("path", "")).strip()
            cmg_kind = mapping.get(kind)
            if not cmg_kind or not path:
                continue
            key = (cmg_kind, path)
            if key in emitted:
                continue
            emitted.add(key)
            manifest_lines.append(f"FILENAMES {cmg_kind} '{path}'")
        if manifest_lines:
            lines.extend(manifest_lines)
            lines.append("")

    def generate(self, data):
        lines = []
        meta = data.get("meta", {})
        case_manifest = data.get("case_manifest", {})
        grid = data.get("grid", {})
        reservoir = data.get("reservoir", {})
        fluid = data.get("fluid", {})
        rockfluid = data.get("rockfluid", {})
        initial = data.get("initial", {})
        numerical = data.get("numerical", {})
        wells = data.get("wells", [])
        timeline_events = data.get("timeline_events", [])
        lines += [
            "** Generated by UDA Middle Layer",
            f"** Source: {meta.get('source_file', 'unknown')}",
            f"** Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"** Source software: {meta.get('source_software', 'unknown')}",
            "",
            "*RESULTS *SIMULATOR *IMEX",
            "*TITLE1 'Converted by UDA Middle Layer'",
            "",
            f"*INUNIT *{meta.get('unit_system', 'field').upper()}",
            "",
            "*WPRN *WELL *TIME",
            "*OUTSRF *WELL *ALL",
            "*OUTSRF *GRID *ALL",
            "",
        ]
        self._write_case_manifest_inputs(lines, case_manifest)
        lines.extend(["** ============================================================", "** GRID", "** ============================================================"])
        self._write_grid(lines, grid)
        lines.append("")
        lines.extend(["** ============================================================", "** RESERVOIR", "** ============================================================"])
        self._write_section(lines, "reservoir", reservoir, grid=grid)
        lines.append("")
        lines.extend(["** ============================================================", "** FLUID", "** ============================================================"])
        model = str(fluid.get("model", "BLACKOIL")).upper()
        if model == "MISCIBLE":
            model = "MISNCG"
        lines.append(f"*MODEL *{model}")
        self._write_fluid(lines, fluid)
        lines.append("")
        lines.extend(["** ============================================================", "** ROCKFLUID", "** ============================================================"])
        lines.append("*ROCKFLUID")
        self._write_rockfluid(lines, rockfluid)
        lines.append("")
        lines.extend(["** ============================================================", "** INITIAL", "** ============================================================"])
        lines.append("*INITIAL")
        self._write_initial(lines, initial)
        lines.append("")
        lines.extend(["** ============================================================", "** NUMERICAL", "** ============================================================"])
        lines.append("*NUMERICAL")
        self._write_section(lines, "numerical", numerical)
        self._write_cmg_numerical_directives(lines, numerical)
        lines.append("")
        lines.extend(["** ============================================================", "** WELL DATA", "** ============================================================"])
        lines.append("*RUN")
        self._write_wells(lines, wells, data.get("meta", {}), timeline_events)
        self._write_unparsed_blocks(lines, data.get("unparsed_blocks", []))
        lines.append("*STOP")
        return "\n".join(lines) + "\n"

    def _write_section(self, lines, section_name, section_data, grid=None):
        cfg = self._gen_cfg.get(section_name, {})
        reverse_k = should_reverse_k_layers(grid or {})
        for key, field_cfg in cfg.items():
            kw = field_cfg.get("keyword")
            fmt = field_cfg.get("format")
            if not kw or fmt in ("depth_from_tops", "depth_block"):
                continue
            obj = section_data.get(key)
            if obj is None:
                continue
            is_reference = isinstance(obj, dict) and obj.get("type") == "reference"
            val = _get_val(obj)
            if val is None and not (fmt == "array" and is_reference):
                continue
            if fmt == "scalar_inline":
                lines.append(f"{kw}  {_fmt(val).strip()}")
            elif fmt == "array":
                out_obj = obj
                if (not is_reference) and isinstance(val, list) and section_name in ("grid", "reservoir") and key in ("dk", "porosity", "perm_i", "perm_j", "perm_k", "ntg"):
                    out_obj = dict(obj)
                    out_obj["values"] = reorder_k_array(val, reverse_k)
                    out_obj["type"] = "array"
                _write_array(lines, kw, out_obj)

    def _write_array_forced(self, lines, keyword, obj, modifier):
        val = _get_val(obj)
        if val is None:
            return
        if modifier == "CON":
            v = val[0] if isinstance(val, list) else val
            lines.append(f"{keyword} *CON  {_fmt(v).strip()}")
        else:
            lines.append(f"{keyword} *{modifier}")
            vals = val if isinstance(val, list) else [val]
            row = ""
            for i, v in enumerate(vals):
                row += f"  {_fmt(v).strip()}"
                if (i + 1) % 10 == 0:
                    lines.append(row)
                    row = ""
            if row:
                lines.append(row)

    def _write_grid(self, lines, grid):
        ni = grid.get("ni", 1)
        nj = grid.get("nj", 1)
        nk = grid.get("nk", 1)
        gt = grid.get("grid_type", "CART").upper()
        reverse_k = should_reverse_k_layers(grid)
        if gt == "RADIAL":
            lines.append(f"*GRID *RADIAL  {ni}  {nj}  {nk}")
            rw = _get_val(grid.get("inrad"))
            if rw is not None:
                lines.append(f"*RW  {_fmt(rw).strip()}")
            di_obj = grid.get("di") or grid.get("drv")
            if di_obj:
                di_val = _get_val(di_obj)
                if isinstance(di_val, list) and len(set(round(v, 6) for v in di_val)) == 1:
                    self._write_array_forced(lines, "*DI", di_obj, "CON")
                else:
                    self._write_array_forced(lines, "*DI", di_obj, "IVAR")
            dj_obj = grid.get("dj") or grid.get("dtheta")
            if dj_obj:
                dj_val = _get_val(dj_obj)
                if isinstance(dj_val, list) and len(set(round(v, 4) for v in dj_val)) != 1:
                    self._write_array_forced(lines, "*DJ", dj_obj, "JVAR")
                else:
                    dj_scalar = dj_val[0] if isinstance(dj_val, list) else dj_val
                    lines.append(f"*DJ *CON {float(dj_scalar):.1f}")
            else:
                lines.append("*DJ *CON 360.0")
            dk_obj = grid.get("dk")
            if dk_obj:
                dk_val = _get_val(dk_obj)
                if isinstance(dk_val, list):
                    out = dict(dk_obj)
                    out["type"] = "array"
                    out["values"] = reorder_k_array(dk_val, reverse_k)
                    self._write_array_forced(lines, "*DK", out, "KVAR")
                else:
                    self._write_array_forced(lines, "*DK", dk_obj, "CON")
        else:
            lines.append(f"*GRID *CART  {ni}  {nj}  {nk}")
            for key, kw in [("di", "*DI"), ("dj", "*DJ"), ("dk", "*DK")]:
                obj = grid.get(key)
                if not obj:
                    continue
                val = _get_val(obj)
                out_obj = obj
                if key == "dk" and isinstance(val, list):
                    out_obj = dict(obj)
                    out_obj["type"] = "array"
                    out_obj["values"] = reorder_k_array(val, reverse_k)
                _write_array(lines, kw, out_obj)
        if grid.get("active_cell_mask") is not None:
            _write_array(lines, "NULL", grid.get("active_cell_mask"))
        if grid.get("pinchout_array") is not None:
            _write_array(lines, "PINCHOUTARRAY", grid.get("pinchout_array"))
        depth_obj = grid.get("depth_ref_block") or compute_depth_from_tops(grid, strategy="default" if reverse_k else "kdir_down")
        if depth_obj and isinstance(depth_obj, dict):
            i = depth_obj.get("i", 1)
            j = depth_obj.get("j", 1)
            k = depth_obj.get("k", 1)
            v = depth_obj.get("value", 0)
            lines.append(f"*DEPTH  {i}  {j}  {k}  {_fmt(v).strip()}")

    def _write_initial(self, lines, initial):
        has_user_input_fields = any(initial.get(key) is not None for key in ("pressure_table", "water_saturation", "oil_saturation", "gas_saturation"))
        lines.append("*USER_INPUT" if has_user_input_fields else "*VERTICAL *BLOCK_CENTER *WATER_OIL_GAS")
        self._write_section(lines, "initial", initial)

    def _write_cmg_numerical_directives(self, lines, numerical):
        directives = []
        for bucket_name in ("_cmg_control_directives", "_cmg_solver_directives"):
            for seq, item in enumerate(numerical.get(bucket_name, []) or []):
                if not isinstance(item, dict):
                    continue
                keyword = str(item.get("keyword", "")).strip()
                if not keyword or keyword.upper() == "*NOLIST":
                    continue
                directives.append((int(item.get("line", 10**9) or 10**9), seq, keyword, [str(tok) for tok in (item.get("tokens") or [])]))
        directives.sort(key=lambda x: (x[0], x[1]))
        for _, _, keyword, tokens in directives:
            line = " ".join([keyword, *tokens]).strip()
            if line:
                lines.append(line)

    def _write_fluid(self, lines, fluid):
        model = str(fluid.get("model", "BLACKOIL")).upper()
        tres = fluid.get("reservoir_temperature")
        if tres is not None and _get_val(tres) is not None:
            lines.append(f"*TRES  {_fmt(_get_val(tres)).strip()}")
        pvt = fluid.get("pvt_table")
        if pvt:
            lines.extend(["", "*PVT", f"** {'p':>12} {'rs':>12} {'bo':>12} {'eg':>12} {'viso':>12} {'visg':>12}"])
            for row in pvt["rows"]:
                lines.append("  " + "".join(_fmt(v) for v in row))
        else:
            zg = fluid.get("zg_table")
            if zg and zg.get("rows"):
                lines.extend(["", "*PVT *ZG", f"** {'p':>12} {'rs':>12} {'bo':>12} {'zg':>12} {'viso':>12} {'visg':>12}"])
                for row in zg["rows"]:
                    lines.append("  " + "".join(_fmt(v) for v in row[:6]))
        if model.startswith("MIS"):
            pvts = fluid.get("pvts_table")
            if pvts and pvts.get("rows"):
                lines.extend(["", "*PVTS", f"** {'p':>12} {'rss':>12} {'es':>12} {'viss':>12} {'omega_s':>12}"])
                for row in pvts["rows"]:
                    lines.append("  " + "".join(_fmt(v) for v in row))
        cfg = self._gen_cfg.get("fluid", {})
        for key, field_cfg in cfg.items():
            if key in {"pvt_table", "reservoir_temperature"}:
                continue
            kw = field_cfg.get("keyword")
            if not kw:
                continue
            obj = fluid.get(key)
            if obj is None:
                continue
            val = _get_val(obj)
            if val is None:
                continue
            lines.append(f"{kw}  {_fmt(val).strip()}")
        gas_gravity = fluid.get("gas_gravity")
        if gas_gravity is not None and _get_val(gas_gravity) is not None:
            lines.append(f"*GRAVITY *GAS  {_fmt(_get_val(gas_gravity)).strip()}")

    def _write_rockfluid(self, lines, rockfluid):
        swt = rockfluid.get("swt_table")
        slt = rockfluid.get("slt_table")
        lines.append("*RPT 1")
        if swt:
            cols = swt.get("columns", ["sw", "krw", "krow", "pcow"])
            lines.append("*SWT")
            lines.append("** " + "  ".join(f"{c:>10}" for c in cols))
            for row in swt["rows"]:
                lines.append("  " + "".join(_fmt(v) for v in row))
        if slt:
            cols = slt.get("columns", ["sl", "krg", "krog", "pcog"])
            lines.append("*SLT")
            lines.append("** " + "  ".join(f"{c:>10}" for c in cols))
            for row in slt["rows"]:
                lines.append("  " + "".join(_fmt(v) for v in row))

    def _write_wells(self, lines, wells, meta, timeline_events=None):
        if not wells:
            return
        start_date = meta.get("start_date")
        if start_date:
            parts = start_date.split("-")
            if len(parts) == 3:
                lines.append(f"*DATE {parts[0]} {parts[1]} {parts[2]}")
        else:
            lines.append("*DATE 1900 01 01")
        lines.append("")
        dtwell = meta.get("dtwell")
        if dtwell:
            lines.append(f"*DTWELL  {dtwell}")
        for idx, w in enumerate(wells, start=1):
            wname = w.get("well_name", f"W{idx}")
            wtype = (w.get("well_type") or "PRODUCER").upper()
            lines.append(f"*WELL {idx} '{wname}'")
            if wtype == "INJECTOR":
                inj = (w.get("inj_fluid") or "GAS").upper()
                lines.append(f"*INJECTOR *UNWEIGHT {idx}")
                lines.append(f"*INCOMP *{inj}")
                bhp_max = w.get("bhp_max")
                rate_max = w.get("rate_max")
                if rate_max:
                    inj_target = "STW" if inj == "WATER" else "STG"
                    lines.append(f"*OPERATE *MAX *{inj_target}  {_fmt(rate_max).strip()}")
                if bhp_max:
                    lines.append(f"*OPERATE *MAX *BHP  {_fmt(bhp_max).strip()}")
            else:
                lines.append(f"*PRODUCER {idx}")
                bhp_min = w.get("bhp_min")
                rate_max = w.get("rate_max")
                if rate_max:
                    lines.append(f"*OPERATE *MAX *STO  {_fmt(rate_max).strip()}")
                if bhp_min:
                    lines.append(f"*OPERATE *MIN *BHP  {_fmt(bhp_min).strip()}")
            radius = w.get("well_radius")
            geofac = w.get("geofac", 0.34)
            wfrac = w.get("wfrac", 1.0)
            skin = w.get("skin", 0.0)
            if radius and radius > 0:
                lines.append(f"*GEOMETRY *K  {radius:.4f}  {geofac:.2f}  {wfrac:.1f}  {skin:.1f}")
            perfs = w.get("perforations", [])
            if perfs:
                lines.append(f"*PERF {idx}")
                for p in perfs:
                    wi = p.get("wi", -1.0)
                    if wi <= 0:
                        wi = 1.0
                    lines.append(f"  {p['i']}  {p['j']}  {p['k']}  {_fmt(wi).strip()}")
            lines.append("")
        self._write_schedule(lines, wells, meta, timeline_events or [])

    def _write_schedule(self, lines, wells, meta, timeline_events):
        events = []
        if timeline_events:
            well_map = {(w.get("well_name") or f"W{i}"): w for i, w in enumerate(wells, start=1)}
            well_idx_map = {(w.get("well_name") or f"W{i}"): i for i, w in enumerate(wells, start=1)}
            for ev in timeline_events:
                t = float(ev.get("absolute_days", 0.0))
                wname = ev.get("well_name")
                idx = well_idx_map.get(wname)
                if idx is None:
                    continue
                val = ev.get("value")
                if val is None:
                    continue
                event_payload = {"value": val}
                if ev.get("target") is not None:
                    event_payload["target"] = ev.get("target")
                events.append((t, idx, event_payload, well_map.get(wname, {"well_name": wname})))
        else:
            for idx, w in enumerate(wells, start=1):
                for ev in w.get("alter_schedule", []):
                    events.append((ev.get("time", 0.0), idx, ev, w))
        if not events:
            total = meta.get("_total_sim_time", 0.0) or 3650.0
            lines.append(f"*TIME  {total:.2f}")
            return
        events.sort(key=lambda e: e[0])
        current_time = 0.0
        lines.append("** Dynamic schedule")
        from itertools import groupby
        for t, group in groupby(events, key=lambda e: e[0]):
            group = list(group)
            if t != current_time:
                lines.append(f"*TIME  {t:.2f}")
                current_time = t
            for _, idx, ev, w in group:
                if "rate" in ev:
                    lines.extend(["*ALTER", f"  {idx}", f"  {_fmt(ev['rate']).strip()}"])
                elif "target" in ev:
                    target = ev.get("target", "ORATE")
                    val = ev.get("value", 0.0)
                    lines.append(f"** WELTARG mapped via ALTER: {w.get('well_name')} {target}={val}")
                    lines.extend(["*ALTER", f"  {idx}", f"  {_fmt(val).strip()}"])
                elif "value" in ev:
                    lines.extend(["*ALTER", f"  {idx}", f"  {_fmt(ev['value']).strip()}"])
        total_time = meta.get("_total_sim_time", 0.0) or (current_time + 3650.0)
        if current_time < total_time:
            lines.append(f"*TIME  {total_time:.2f}")

    def _write_unparsed_blocks(self, lines, unparsed_blocks):
        if not unparsed_blocks:
            return
        lines.append("** UNPARSED BLOCKS")
        for blk in unparsed_blocks:
            ln = blk.get("line", "?")
            txt = str(blk.get("text", "")).strip()
            lines.append(f"** UNPARSED [line {ln}]: {txt}")
