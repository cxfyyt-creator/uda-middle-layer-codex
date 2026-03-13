# =============================================================================
# generators/cmg_generator.py  —  通用 JSON → CMG IMEX .dat
# 架构：规则驱动
#   - generators.cmg 配置决定每个 JSON 字段对应哪个关键字和格式
#   - 新增简单字段：只需在 keyword_registry.yaml 的 generators.cmg 下添加一行
# =============================================================================

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.rule_loader import get_loader

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
        return obj.get("modifier")
    return None

# ── CMG 数组写入 ──────────────────────────────────────────────────────────────

def _write_array(lines, keyword, obj):
    """根据 JSON 对象的 type/modifier 写出 CMG 数组关键字"""
    if obj is None:
        return
    t = obj.get("type") if isinstance(obj, dict) else None
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
    """
    如果 JSON 里有 pvto_table + pvdg_table（Petrel来源），
    合并为 CMG *PVT 格式的 6列表：p, rs, bo, eg, viso, visg
    如果已有 pvt_table（CMG来源）则直接使用。
    """
    if fluid.get("pvt_table"):
        return fluid["pvt_table"]

    pvto = fluid.get("pvto_table")
    pvdg = fluid.get("pvdg_table")
    if not pvto or not pvdg:
        return None

    # pvto cols: [rs, p, bo, viso]
    pvto_rows = pvto["rows"]
    # pvdg cols: [p, bg, visg]
    pvdg_rows = pvdg["rows"]

    # 建立 PVDG 压力→(bg, visg) 插值字典
    pvdg_p = [r[0] for r in pvdg_rows]
    pvdg_bg = [r[1] for r in pvdg_rows]
    pvdg_visg = [r[2] for r in pvdg_rows]

    def _interp(px, xs, ys):
        if px <= xs[0]:
            return ys[0]
        if px >= xs[-1]:
            return ys[-1]
        for i in range(len(xs) - 1):
            if xs[i] <= px <= xs[i + 1]:
                t = (px - xs[i]) / (xs[i + 1] - xs[i])
                return ys[i] + t * (ys[i + 1] - ys[i])
        return ys[-1]

    # CMG *PVT 只支持饱和点（每个RS对应唯一的饱和压力）
    # PVTO 中同一 RS 下的欠饱和点（后续更高压力行）须丢弃
    # 判断依据：rs 值与上一行相同 → 欠饱和点
    merged = []
    seen_rs = set()
    for row in pvto_rows:
        rs, p, bo, viso = row[0], row[1], row[2], row[3]
        # 跳过欠饱和行（同一 RS 已出现过）
        rs_key = round(rs, 6)
        if rs_key in seen_rs:
            continue
        seen_rs.add(rs_key)
        bg = _interp(p, pvdg_p, pvdg_bg)
        visg = _interp(p, pvdg_p, pvdg_visg)
        eg = 1.0 / bg if bg > 0 else 0.0
        merged.append([p, rs, bo, eg, viso, visg])

    # 按压力升序排序（CMG *PVT 要求升序）
    merged.sort(key=lambda r: r[0])

    return {"type": "table",
            "columns": ["p", "rs", "bo", "eg", "viso", "visg"],
            "rows": merged,
            "confidence": 0.95,
            "source": "merged from pvto_table + pvdg_table"}


# ── 相渗表合并（swfn/sgfn/sof3 → swt/slt）──────────────────────────────────

def _merge_rockfluid(rockfluid):
    """
    如果 JSON 里有 swfn/sgfn/sof3（Petrel来源），合并为 CMG swt/slt。
    如果已有 swt_table/slt_table（CMG来源）则直接使用。
    """
    # 优先使用已有表
    swt = rockfluid.get("swt_table") or rockfluid.get("swof_table")
    slt = rockfluid.get("slt_table") or rockfluid.get("sgof_table")

    if not swt:
        swt = _merge_swt(rockfluid)
    if not slt:
        slt = _merge_slt(rockfluid)

    return swt, slt


def _interp1d(x, xs, ys):
    if len(xs) < 2:
        return ys[0] if ys else 0.0
    if x <= xs[0]: return ys[0]
    if x >= xs[-1]: return ys[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            t = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + t * (ys[i + 1] - ys[i])
    return ys[-1]


def _merge_swt(rockfluid):
    """SWFN(sw,krw,pcow) + SOF3(so,krow,krog) → SWT(sw,krw,krow,pcow)"""
    swfn = rockfluid.get("swfn_table")
    sof3 = rockfluid.get("sof3_table")
    if not swfn:
        return None

    swfn_rows = swfn["rows"]   # [sw, krw, pcow]
    sof3_rows = sof3["rows"] if sof3 else None

    # SOF3: so→krow
    if sof3_rows:
        sof3_so   = [r[0] for r in sof3_rows]
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
            krow = 1.0 - sw  # fallback 线性
        rows.append([sw, krw, krow, pcow])

    return {"type": "table",
            "columns": ["sw", "krw", "krow", "pcow"],
            "rows": rows,
            "confidence": 0.9,
            "source": "merged from swfn_table + sof3_table"}


def _merge_slt(rockfluid):
    """SGFN(sg,krg,pcog) + SOF3(so,krow,krog) → SLT(sl,krg,krog,pcog)"""
    sgfn = rockfluid.get("sgfn_table")
    sof3 = rockfluid.get("sof3_table")
    if not sgfn:
        return None

    sgfn_rows = sgfn["rows"]   # [sg, krg, pcog]
    sof3_rows = sof3["rows"] if sof3 else None

    if sof3_rows:
        sof3_so   = [r[0] for r in sof3_rows]
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
            krog = sg  # fallback
        rows.append([sl, krg, krog, pcog])

    # SLT 按 sl 升序排列
    rows.sort(key=lambda r: r[0])

    return {"type": "table",
            "columns": ["sl", "krg", "krog", "pcog"],
            "rows": rows,
            "confidence": 0.9,
            "source": "merged from sgfn_table + sof3_table"}


# ── 主生成器 ──────────────────────────────────────────────────────────────────

class CMGGenerator:

    def __init__(self):
        self._rl = get_loader()
        self._gen_cfg = self._rl.cmg_gen_config()

    def generate(self, data):
        lines = []
        meta      = data.get("meta", {})
        grid      = data.get("grid", {})
        reservoir = data.get("reservoir", {})
        fluid     = data.get("fluid", {})
        rockfluid = data.get("rockfluid", {})
        initial   = data.get("initial", {})
        numerical = data.get("numerical", {})
        wells     = data.get("wells", [])

        # ── 文件头 ────────────────────────────────────────────────────────────
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
        lines.append("*MODEL *BLACKOIL")
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
        lines.append("*VERTICAL *BLOCK_CENTER *WATER_OIL_GAS")
        self._write_section(lines, "initial", initial)
        lines.append("")

        # ── NUMERICAL ─────────────────────────────────────────────────────────
        lines.append("** ============================================================")
        lines.append("** NUMERICAL")
        lines.append("** ============================================================")
        lines.append("*NUMERICAL")
        self._write_section(lines, "numerical", numerical)
        lines.append("")

        # ── WELLS ─────────────────────────────────────────────────────────────
        lines.append("** ============================================================")
        lines.append("** WELL DATA")
        lines.append("** ============================================================")
        lines.append("*RUN")
        self._write_wells(lines, wells, data.get("meta", {}))

        lines.append("*STOP")
        return "\n".join(lines) + "\n"

    # ── 通用分区写入 ─────────────────────────────────────────────────────────

    def _write_section(self, lines, section_name, section_data, grid=None):
        cfg = self._gen_cfg.get(section_name, {})
        gt = (grid or {}).get("grid_type", "CART").upper() if grid else "CART"

        for key, field_cfg in cfg.items():
            kw = field_cfg.get("keyword")
            fmt = field_cfg.get("format")
            if not kw or fmt in ("depth_from_tops", "depth_block"):
                continue
            obj = section_data.get(key)

            # 径向网格：perm_j 缺失时用 perm_i 填充（PERMR 同时作径向和切向）
            if obj is None and section_name == "reservoir" and gt == "RADIAL":
                if key == "perm_j":
                    obj = section_data.get("perm_i")
                elif key == "perm_k" and section_data.get("perm_k") is None:
                    # perm_k 若真的缺失才跳过（PERMZ 可能已经 MULTIPLY 了，保留原值）
                    pass

            if obj is None:
                continue
            val = _get_val(obj)
            if val is None:
                continue

            if fmt == "scalar_inline":
                lines.append(f"{kw}  {_fmt(val).strip()}")
            elif fmt == "array":
                _write_array(lines, kw, obj)

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

        if gt == "RADIAL":
            lines.append(f"*GRID *RADIAL  {ni}  {nj}  {nk}")
            rw = _get_val(grid.get("inrad"))
            if rw is not None:
                lines.append(f"*RW  {_fmt(rw).strip()}")

            # *DI *IVAR — 径向方向，ni 个值（不能用 *CON/*KVAR）
            di_obj = grid.get("di") or grid.get("drv")
            if di_obj:
                di_val = _get_val(di_obj)
                if isinstance(di_val, list) and len(set(round(v,6) for v in di_val)) == 1:
                    # 所有径向间距相同时才可以用 *CON
                    self._write_array_forced(lines, "*DI", di_obj, "CON")
                else:
                    self._write_array_forced(lines, "*DI", di_obj, "IVAR")

            # *DJ *CON 360 — 角度方向（径向模型通常固定360°）
            dj_obj = grid.get("dj") or grid.get("dtheta")
            if dj_obj:
                dj_val = _get_val(dj_obj)
                if isinstance(dj_val, list):
                    if len(set(round(v, 4) for v in dj_val)) == 1:
                        lines.append(f"*DJ *CON {dj_val[0]:.1f}")
                    else:
                        self._write_array_forced(lines, "*DJ", dj_obj, "JVAR")
                elif dj_val is not None:
                    lines.append(f"*DJ *CON {dj_val:.1f}")
                else:
                    lines.append("*DJ *CON 360.0")
            else:
                lines.append("*DJ *CON 360.0")

            # *DK *KVAR — 层方向，nk 个值（不能用 *IVAR）
            dk_obj = grid.get("dk")
            if dk_obj:
                dk_val = _get_val(dk_obj)
                if isinstance(dk_val, list) and len(set(round(v,6) for v in dk_val)) == 1:
                    self._write_array_forced(lines, "*DK", dk_obj, "CON")
                else:
                    self._write_array_forced(lines, "*DK", dk_obj, "KVAR")

        else:
            # 笛卡尔网格：*DI/*DJ/*DK，修饰词由 JSON modifier 决定（CON/KVAR等均合法）
            lines.append(f"*GRID *CART  {ni}  {nj}  {nk}")
            for key, kw in [("di", "*DI"), ("dj", "*DJ"), ("dk", "*DK")]:
                obj = grid.get(key)
                if obj:
                    _write_array(lines, kw, obj)

        # 深度
        depth_obj = grid.get("depth_ref_block")
        if depth_obj and isinstance(depth_obj, dict):
            i = depth_obj.get("i", 1)
            j = depth_obj.get("j", 1)
            k = depth_obj.get("k", 1)
            v = depth_obj.get("value", 0)
            lines.append(f"*DEPTH  {i}  {j}  {k}  {_fmt(v).strip()}")
        elif grid.get("tops_ref"):
            tops_val = _get_val(grid["tops_ref"])
            if isinstance(tops_val, list):
                lines.append(f"*DEPTH  1  1  1  {_fmt(tops_val[0]).strip()}")
            elif tops_val is not None:
                lines.append(f"*DEPTH  1  1  1  {_fmt(tops_val).strip()}")

    # ── 流体写入 ──────────────────────────────────────────────────────────────

    def _write_fluid(self, lines, fluid):
        # PVT 表（合并 pvto+pvdg 或直接用 pvt_table）
        pvt = _merge_pvt(fluid)
        if pvt:
            lines.append("")
            lines.append("*PVT")
            lines.append(f"** {'p':>12} {'rs':>12} {'bo':>12} {'eg':>12} {'viso':>12} {'visg':>12}")
            for row in pvt["rows"]:
                lines.append("  " + "".join(_fmt(v) for v in row))

        # 密度
        cfg = self._gen_cfg.get("fluid", {})
        for key, field_cfg in cfg.items():
            if key == "pvt_table":
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

    # ── 相渗写入 ──────────────────────────────────────────────────────────────

    def _write_rockfluid(self, lines, rockfluid):
        swt, slt = _merge_rockfluid(rockfluid)
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

    def _write_wells(self, lines, wells, meta):
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
                    lines.append(f"*OPERATE *MAX *STG  {_fmt(rate_max).strip()}")
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
        self._write_schedule(lines, wells, meta)

    def _write_schedule(self, lines, wells, meta):
        """
        将 alter_schedule 中的时间点汇总，按时间顺序写 *TIME/*ALTER。
        支持两种来源：
          CMG来源: {time: float, rate: float}
          Petrel来源: {time: float, target: str, value: float}
        """
        # 收集所有 (time, well_idx, entry) 事件
        events = []
        for idx, w in enumerate(wells, start=1):
            for ev in w.get("alter_schedule", []):
                t = ev.get("time", 0.0)
                events.append((t, idx, ev, w))

        if not events:
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
                    lines.append(f"*ALTER  {idx}  {_fmt(rate).strip()}")
                elif "target" in ev:
                    target = ev.get("target", "ORATE")
                    val    = ev.get("value", 0.0)
                    lines.append(f"** WELTARG: {w.get('well_name')} {target}={val}")
                    lines.append(f"*ALTER  {idx}  {_fmt(val).strip()}")

        # 结束时间
        total_time = meta.get("_total_sim_time", 0.0)
        if not total_time:
            total_time = current_time + 3650.0
        if current_time < total_time:
            lines.append(f"*TIME  {total_time:.2f}")


# ── 对外接口 ──────────────────────────────────────────────────────────────────

def generate_cmg(data_or_json, output_file=None):
    if isinstance(data_or_json, (str, Path)):
        with open(data_or_json, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = data_or_json

    content = CMGGenerator().generate(data)

    if output_file:
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(content)

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