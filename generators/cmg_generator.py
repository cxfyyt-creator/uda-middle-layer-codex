# =============================================================================
# generators/cmg_generator.py  —  通用 JSON → CMG IMEX .dat
# 架构：规则驱动
#   - generators.cmg 配置决定每个 JSON 字段对应哪个关键字和格式
#   - 新增简单字段：只需在 keyword_registry.yaml 的 generators.cmg 下添加一行
# =============================================================================

import json
import shutil
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.confidence_checks import evaluate_confidence
from utils.cmg_case_dependencies import scan_cmg_case_dependencies
from utils.rule_loader import get_loader
from utils.reporting import write_report_bundle
from utils.target_preflight import evaluate_target_preflight
from utils.value_semantics import modifier_from_distribution
from business_rules import (
    apply_radial_perm_j,
    compute_depth_from_tops,
    derive_pb,
    enrich_miscible_model,
    ensure_co_cvo,
    merge_pvt_saturated_only,
    merge_rockfluid_tables,
    reorder_k_array,
    should_reverse_k_layers,
)

# ── 格式化工具 ────────────────────────────────────────────────────────────────

def _fmt(v, width=14):
    """格式化单个数值，统一列宽"""
    if isinstance(v, int):
        return str(v).rjust(width)
    if abs(v) >= 1e5 or (abs(v) < 1e-3 and v != 0):
        return f"{v:.6E}".rjust(width)
    return f"{v:.6g}".rjust(width)

def _get_val(obj):
    """从 JSON 值对象取出数值（scalar→value，array→values）"""
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
    if obj.get("type") == "reference" and str(obj.get("relation", "")).upper() == "EQUALSI":
        return float(obj.get("scale", 1.0) or 1.0)
    hint = obj.get("source_format_hint") or {}
    if str(hint.get("keyword", "")).upper() == "*EQUALSI":
        return float(hint.get("scale", 1.0) or 1.0)
    return None

# ── CMG 数组写入 ──────────────────────────────────────────────────────────────

def _write_array(lines, keyword, obj):
    """?? JSON ??? type/modifier ?? CMG ?????"""
    if obj is None:
        return
    t = obj.get("type") if isinstance(obj, dict) else None
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
        # fallback
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


# ── PVT 合并（pvto_table + pvdg_table → 6列 pvt_table）─────────────────────

def _merge_pvt(fluid):
    """业务逻辑委托给 business_rules"""
    return merge_pvt_saturated_only(fluid)


# ── 主生成器 ──────────────────────────────────────────────────────────────────

class CMGGenerator:

    def __init__(self):
        self._rl = get_loader()
        self._gen_cfg = self._rl.cmg_gen_config()

    def _preserved_cmg_deck(self, data):
        if not isinstance(data, dict):
            return None
        meta = data.get("meta", {}) or {}
        if str(meta.get("source_software", "")).lower() != "cmg_imex":
            return None
        if meta.get("_cmg_roundtrip_mode") != "source_faithful":
            return None
        raw_lines = meta.get("_cmg_raw_deck_lines")
        if not isinstance(raw_lines, list) or not raw_lines:
            return None
        text = "\n".join(str(line) for line in raw_lines).rstrip()
        if not text:
            return None
        return text + "\n"

    def _copy_external_file_refs(self, data, output_file):
        if not isinstance(data, dict) or not output_file:
            return

        meta = data.get("meta", {}) or {}
        raw_lines = meta.get("_cmg_raw_deck_lines")
        source_dir = meta.get("_cmg_source_dir")
        if not raw_lines or not source_dir:
            return

        dst_root = Path(output_file).parent
        deps = meta.get("_cmg_case_dependencies") or scan_cmg_case_dependencies(raw_lines, source_dir)
        for item in deps.get("runtime_inputs", []):
            ref = item.get("path")
            if not ref:
                continue
            src_path = Path(item.get("source_path") or ref)
            dst_path = dst_root / Path(ref).name
            if not src_path.exists():
                continue
            if src_path.resolve() == dst_path.resolve():
                continue
            if dst_path.exists():
                continue
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)

    def generate(self, data):
        preserved = self._preserved_cmg_deck(data)
        if preserved is not None:
            return preserved

        lines = []
        meta      = data.get("meta", {})
        grid      = data.get("grid", {})
        reservoir = data.get("reservoir", {})
        fluid     = data.get("fluid", {})
        rockfluid = data.get("rockfluid", {})
        initial   = data.get("initial", {})

        reservoir = apply_radial_perm_j(grid, reservoir)
        initial = dict(initial)
        initial["bubble_point_pressure"] = derive_pb(initial, fluid)
        fluid, initial = enrich_miscible_model(fluid, rockfluid, initial, meta)

        numerical = data.get("numerical", {})
        wells     = data.get("wells", [])
        timeline_events = data.get("timeline_events", [])
        lines += [
            f"** Generated by UDA Middle Layer",
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

        # ── GRID ──────────────────────────────────────────────────────────────
        lines.append("** ============================================================")
        lines.append("** GRID")
        lines.append("** ============================================================")
        self._write_grid(lines, grid)
        lines.append("")

        # ── RESERVOIR ─────────────────────────────────────────────────────────
        lines.append("** ============================================================")
        lines.append("** RESERVOIR")
        lines.append("** ============================================================")
        self._write_section(lines, "reservoir", reservoir, grid=grid)
        lines.append("")

        # ── FLUID ─────────────────────────────────────────────────────────────
        lines.append("** ============================================================")
        lines.append("** FLUID")
        lines.append("** ============================================================")
        model = str(fluid.get("model", "BLACKOIL")).upper()
        if model == "MISCIBLE":
            model = "MISNCG"
        lines.append(f"*MODEL *{model}")
        self._write_fluid(lines, fluid)

        lines.append("")

        # ── ROCKFLUID ─────────────────────────────────────────────────────────
        lines.append("** ============================================================")
        lines.append("** ROCKFLUID")
        lines.append("** ============================================================")
        lines.append("*ROCKFLUID")
        self._write_rockfluid(lines, rockfluid)
        lines.append("")

        # ── INITIAL ───────────────────────────────────────────────────────────
        lines.append("** ============================================================")
        lines.append("** INITIAL")
        lines.append("** ============================================================")
        lines.append("*INITIAL")
        self._write_initial(lines, initial)
        lines.append("")

        # ── NUMERICAL ─────────────────────────────────────────────────────────
        lines.append("** ============================================================")
        lines.append("** NUMERICAL")
        lines.append("** ============================================================")
        lines.append("*NUMERICAL")
        self._write_section(lines, "numerical", numerical)
        self._write_cmg_numerical_directives(lines, numerical)
        lines.append("")

        # ── WELLS ─────────────────────────────────────────────────────────────
        lines.append("** ============================================================")
        lines.append("** WELL DATA")
        lines.append("** ============================================================")
        lines.append("*RUN")
        self._write_wells(lines, wells, data.get("meta", {}), timeline_events)

        self._write_unparsed_blocks(lines, data.get("unparsed_blocks", []))
        lines.append("*STOP")
        return "\n".join(lines) + "\n"

    # ── 通用分区写入 ─────────────────────────────────────────────────────────

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
                if (not is_reference) and isinstance(val, list) and section_name in ("grid", "reservoir") and key in (
                    "dk", "porosity", "perm_i", "perm_j", "perm_k", "ntg"
                ):
                    out_obj = dict(obj)
                    out_obj["values"] = reorder_k_array(val, reverse_k)
                    out_obj["type"] = "array"
                _write_array(lines, kw, out_obj)

    # ── 网格写入 ──────────────────────────────────────────────────────────────

    def _write_array_forced(self, lines, keyword, obj, modifier):
        """强制指定修饰词写数组，忽略 JSON 里原有的 modifier。
        用于径向网格 *DI *IVAR / *DK *KVAR 等必须指定方向的场景。"""
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

        depth_obj = grid.get("depth_ref_block") or compute_depth_from_tops(
            grid, strategy="default" if reverse_k else "kdir_down"
        )
        if depth_obj and isinstance(depth_obj, dict):
            i = depth_obj.get("i", 1)
            j = depth_obj.get("j", 1)
            k = depth_obj.get("k", 1)
            v = depth_obj.get("value", 0)
            lines.append(f"*DEPTH  {i}  {j}  {k}  {_fmt(v).strip()}")

    def _write_initial(self, lines, initial):
        has_user_input_fields = any(
            initial.get(key) is not None
            for key in ("pressure_table", "water_saturation", "oil_saturation", "gas_saturation")
        )
        if has_user_input_fields:
            lines.append("*USER_INPUT")
        else:
            lines.append("*VERTICAL *BLOCK_CENTER *WATER_OIL_GAS")
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
                directives.append((
                    int(item.get("line", 10**9) or 10**9),
                    seq,
                    keyword,
                    [str(tok) for tok in (item.get("tokens") or [])],
                ))

        directives.sort(key=lambda x: (x[0], x[1]))
        for _, _, keyword, tokens in directives:
            line = " ".join([keyword, *tokens]).strip()
            if line:
                lines.append(line)

    # ── 流体写入 ──────────────────────────────────────────────────────────────

    def _write_fluid(self, lines, fluid):
        model = str(fluid.get("model", "BLACKOIL")).upper()

        tres = fluid.get("reservoir_temperature")
        if tres is not None and _get_val(tres) is not None:
            lines.append(f"*TRES  {_fmt(_get_val(tres)).strip()}")

        pvt = _merge_pvt(fluid)
        if pvt:
            lines.append("")
            lines.append("*PVT")
            lines.append(f"** {'p':>12} {'rs':>12} {'bo':>12} {'eg':>12} {'viso':>12} {'visg':>12}")
            for row in pvt["rows"]:
                lines.append("  " + "".join(_fmt(v) for v in row))
        else:
            zg = fluid.get("zg_table")
            if zg and zg.get("rows"):
                lines.append("")
                lines.append("*PVT *ZG")
                lines.append(f"** {'p':>12} {'rs':>12} {'bo':>12} {'zg':>12} {'viso':>12} {'visg':>12}")
                for row in zg["rows"]:
                    lines.append("  " + "".join(_fmt(v) for v in row[:6]))

        if model.startswith("MIS"):
            pvts = fluid.get("pvts_table")
            if pvts and pvts.get("rows"):
                lines.append("")
                lines.append("*PVTS")
                lines.append(f"** {'p':>12} {'rss':>12} {'es':>12} {'viss':>12} {'omega_s':>12}")
                for row in pvts["rows"]:
                    lines.append("  " + "".join(_fmt(v) for v in row))

        co_obj, cvo_obj = ensure_co_cvo(fluid)
        fluid = dict(fluid)
        fluid["oil_compressibility"] = co_obj
        fluid["oil_viscosity_coeff"] = cvo_obj

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


    # ── 相渗写入 ──────────────────────────────────────────────────────────────

    def _write_rockfluid(self, lines, rockfluid):
        swt, slt = merge_rockfluid_tables(rockfluid)
        lines.append("*RPT 1")
        if swt:
            cols = swt.get("columns", ["sw", "krw", "krow", "pcow"])
            lines.append(f"*SWT")
            lines.append("** " + "  ".join(f"{c:>10}" for c in cols))
            for row in swt["rows"]:
                lines.append("  " + "".join(_fmt(v) for v in row))
        if slt:
            cols = slt.get("columns", ["sl", "krg", "krog", "pcog"])
            lines.append(f"*SLT")
            lines.append("** " + "  ".join(f"{c:>10}" for c in cols))
            for row in slt["rows"]:
                lines.append("  " + "".join(_fmt(v) for v in row))

    # ── 井写入 ────────────────────────────────────────────────────────────────

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

        # 写出井定义
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

            # 井几何
            radius = w.get("well_radius")
            geofac = w.get("geofac", 0.34)
            wfrac  = w.get("wfrac",  1.0)
            skin   = w.get("skin",   0.0)
            if radius and radius > 0:
                lines.append(f"*GEOMETRY *K  {radius:.4f}  {geofac:.2f}  {wfrac:.1f}  {skin:.1f}")

            # 射孔
            perfs = w.get("perforations", [])
            if perfs:
                lines.append(f"*PERF {idx}")
                for p in perfs:
                    wi = p.get("wi", -1.0)
                    if wi <= 0:
                        wi = 1.0
                    lines.append(f"  {p['i']}  {p['j']}  {p['k']}  {_fmt(wi).strip()}")
            lines.append("")

        # 动态调度（ALTER）
        self._write_schedule(lines, wells, meta, timeline_events or [])

    def _write_schedule(self, lines, wells, meta, timeline_events):
        """
        将 alter_schedule 中的时间点汇总，按时间顺序写 *TIME/*ALTER。
        支持两种来源：
          timeline_events来源: {absolute_days: float, value: float}
          兜底来源: well.alter_schedule
        """
        # 收集所有 (time, well_idx, entry, well) 事件
        events = []
        if timeline_events:
            well_map = {
                (w.get("well_name") or f"W{i}"): w
                for i, w in enumerate(wells, start=1)
            }
            well_idx_map = {
                (w.get("well_name") or f"W{i}"): i
                for i, w in enumerate(wells, start=1)
            }
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
                    t = ev.get("time", 0.0)
                    events.append((t, idx, ev, w))

        if not events:
            total = meta.get("_total_sim_time", 0.0) or 3650.0
            lines.append(f"*TIME  {total:.2f}")
            return

        events.sort(key=lambda e: e[0])
        current_time = 0.0
        lines.append("** ── 动态调度 ──")

        # 按时间分组
        from itertools import groupby
        for t, group in groupby(events, key=lambda e: e[0]):
            group = list(group)
            if t != current_time:
                lines.append(f"*TIME  {t:.2f}")
                current_time = t
            for _, idx, ev, w in group:
                if "rate" in ev:
                    rate = ev["rate"]
                    lines.append("*ALTER")
                    lines.append(f"  {idx}")
                    lines.append(f"  {_fmt(rate).strip()}")
                elif "target" in ev:
                    target = ev.get("target", "ORATE")
                    val    = ev.get("value", 0.0)
                    lines.append(f"** WELTARG mapped via ALTER: {w.get('well_name')} {target}={val}")
                    lines.append("*ALTER")
                    lines.append(f"  {idx}")
                    lines.append(f"  {_fmt(val).strip()}")
                elif "value" in ev:
                    lines.append("*ALTER")
                    lines.append(f"  {idx}")
                    lines.append(f"  {_fmt(ev['value']).strip()}")

        # 结束时间
        total_time = meta.get("_total_sim_time", 0.0)
        if not total_time:
            total_time = current_time + 3650.0
        if current_time < total_time:
            lines.append(f"*TIME  {total_time:.2f}")

    def _write_unparsed_blocks(self, lines, unparsed_blocks):
        if not unparsed_blocks:
            return
        lines.append("** ── UNPARSED BLOCKS ──")
        for blk in unparsed_blocks:
            ln = blk.get("line", "?")
            txt = str(blk.get("text", "")).strip()
            lines.append(f"** UNPARSED [line {ln}]: {txt}")


# ── 对外接口 ──────────────────────────────────────────────────────────────────

def generate_cmg(data_or_json, output_file=None, report_dir="outputs/reports/generators"):
    source_name = str(data_or_json) if isinstance(data_or_json, (str, Path)) else "in_memory_json"
    if isinstance(data_or_json, (str, Path)):
        with open(data_or_json, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = data_or_json
    generator = CMGGenerator()
    preserved_content = generator._preserved_cmg_deck(data) if isinstance(data, dict) else None
    source_faithful = preserved_content is not None

    def _write_failed_report(errors, warnings=None):
        md_path, json_path = write_report_bundle(
            report_dir=report_dir,
            source_name=Path(source_name).name,
            report_type="generate_cmg",
            title="CMG generation report",
            summary_items=[
                ("output_file", "(not written)"),
                ("line_count", 0),
                ("well_count", len(data.get("wells", [])) if isinstance(data, dict) else 0),
                ("grid_type", data.get("grid", {}).get("grid_type", "unknown") if isinstance(data, dict) else "unknown"),
            ],
            warnings=warnings or [],
            errors=errors,
            details={
                "stage": "pre_generation_validation",
                "preflight": preflight,
                "confidence_check": confidence_check,
            },
        )
        if isinstance(data, dict):
            data.setdefault("_generate_report", {"md": str(md_path), "json": str(json_path)})

    preflight = evaluate_target_preflight(data, target="cmg") if isinstance(data, dict) else {
        "target": "cmg", "model": "UNKNOWN", "warnings": [], "blockers": [], "ok": True,
    }
    confidence_check = evaluate_confidence(data, target="cmg") if isinstance(data, dict) else {
        "warnings": [], "blockers": [], "low_confidence_items": [], "checked_item_count": 0,
        "warning_threshold": 0.9, "block_threshold": 0.5, "target": "cmg",
    }

    effective_preflight_blockers = list(preflight["blockers"])
    if source_faithful:
        effective_preflight_blockers = [
            item for item in effective_preflight_blockers
            if str(item).startswith("missing required CMG runtime input:")
        ]

    if effective_preflight_blockers:
        _write_failed_report(effective_preflight_blockers, warnings=preflight["warnings"])
        raise ValueError(
            "CMG generation blocked by preflight checks: "
            + "; ".join(effective_preflight_blockers)
        )
    effective_confidence_blockers = [] if source_faithful else list(confidence_check["blockers"])
    if effective_confidence_blockers:
        _write_failed_report(confidence_check["blockers"], warnings=preflight["warnings"] + confidence_check["warnings"])
        raise ValueError(
            "CMG generation blocked by very low-confidence critical fields: "
            + "; ".join(effective_confidence_blockers)
        )

    content = preserved_content if preserved_content is not None else generator.generate(data)

    out_path = None
    if output_file:
        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        generator._copy_external_file_refs(data, out_path)

    warnings = []
    wells = data.get("wells", []) if isinstance(data, dict) else []
    meta = data.get("meta", {}) if isinstance(data, dict) else {}
    deps = meta.get("_cmg_case_dependencies", {}) if isinstance(meta, dict) else {}
    if not wells:
        warnings.append("no wells found; WELL DATA section may be empty")
    runtime_inputs = deps.get("runtime_inputs", []) or []
    missing_runtime = deps.get("missing_runtime_inputs", []) or []
    if runtime_inputs:
        warnings.append(f"cmg case runtime inputs detected: {len(runtime_inputs)}")
    for item in missing_runtime:
        warnings.append(f"missing cmg runtime input: {item.get('path')}")
    warnings.extend(f"preflight: {w}" for w in preflight["warnings"][:10])
    if len(preflight["warnings"]) > 10:
        warnings.append(f"preflight: omitted {len(preflight['warnings']) - 10} more items")
    warnings.extend(f"low confidence: {w}" for w in confidence_check["warnings"][:10])
    if len(confidence_check["warnings"]) > 10:
        warnings.append(f"low confidence: omitted {len(confidence_check['warnings']) - 10} more items")

    summary = [
        ("output_file", str(out_path) if out_path else "(not written)"),
        ("line_count", len(content.splitlines())),
        ("well_count", len(wells)),
        ("grid_type", data.get("grid", {}).get("grid_type", "CART") if isinstance(data, dict) else "unknown"),
    ]
    md_path, json_path = write_report_bundle(
        report_dir=report_dir,
        source_name=Path(source_name).name,
        report_type="generate_cmg",
        title="CMG generation report",
        summary_items=summary,
        warnings=warnings,
        errors=[],
        details={
            "has_pvto_table": bool(data.get("fluid", {}).get("pvto_table")) if isinstance(data, dict) else False,
            "has_pvdg_table": bool(data.get("fluid", {}).get("pvdg_table")) if isinstance(data, dict) else False,
            "has_pvt_table": bool(data.get("fluid", {}).get("pvt_table")) if isinstance(data, dict) else False,
            "case_dependencies": deps if isinstance(data, dict) else {},
            "preflight": preflight,
            "confidence_check": confidence_check,
        },
    )
    if isinstance(data, dict):
        data.setdefault("_generate_report", {"md": str(md_path), "json": str(json_path)})

    return content


if __name__ == "__main__":
    default_json = Path("outputs/json/SPE2_CHAP_parsed.json")
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else default_json

    out_dir = Path("outputs/cmg")
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(src).stem.replace("_parsed", "")
    out = out_dir / f"{stem}_converted.dat"

    generate_cmg(src, str(out))
    print(f"CMG file written: {out}")
