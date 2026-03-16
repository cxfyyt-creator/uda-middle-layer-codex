# =============================================================================
# parsers/cmg_parser.py  —  CMG IMEX .dat → 通用 JSON dict
# 架构：规则驱动 + 自定义处理器
#   - 简单关键字（array/scalar_inline/pvt6/rpt_table）全部由通用 handler 处理
#   - 复杂关键字（井定义/动态调度）由专属方法处理
#   - 新增简单关键字：只需在 rules/keyword_registry.yaml 中添加一行
# =============================================================================

import re
import json
import sys
import logging
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.rule_loader import get_loader
from utils.reporting import write_report_bundle

# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _strip_comments(line):
    idx = line.find("**")
    return line[:idx].strip() if idx >= 0 else line.strip()

def _is_kw(tok):
    return tok.startswith("*") and not tok.startswith("**")

def _to_float(s):
    return float(str(s).replace("d", "e").replace("D", "E"))

def _expand_repeat(tok):
    m = re.match(r'^(\d+)\*([0-9.eEdD+\-]+)$', tok)
    if m:
        return [_to_float(m.group(2))] * int(m.group(1))
    return None

def _scalar(v, unit, src, modifier=None):
    d = {"type": "scalar", "value": v, "unit": unit,
         "confidence": 0.99, "source": src}
    if modifier:
        d["modifier"] = modifier
    return d

def _array(vs, unit, src, modifier=None):
    d = {"type": "array", "values": vs, "unit": unit,
         "grid_order": "IJK", "confidence": 0.99, "source": src}
    if modifier:
        d["modifier"] = modifier
    return d

def _table(cols, rows, src):
    return {"type": "table", "columns": cols, "rows": rows,
            "confidence": 0.99, "source": src}


# ── 主解析器 ──────────────────────────────────────────────────────────────────

class CMGParser:

    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self.tokens = []
        self.pos = 0
        self._rl = get_loader()
        self.logger = logging.getLogger(__name__)
        self.unparsed_blocks = []

    # ── Token 管理 ────────────────────────────────────────────────────────────

    def _load_tokens(self):
        with open(self.filepath, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        for lineno, raw in enumerate(lines, 1):
            line = _strip_comments(raw)
            if not line:
                continue
            for tok in line.split():
                self.tokens.append((lineno, tok))

    def _peek(self, off=0):
        i = self.pos + off
        return self.tokens[i] if i < len(self.tokens) else None

    def _next(self):
        t = self._peek()
        self.pos += 1
        return t

    def _last_lineno(self):
        if self.pos > 0:
            return self.tokens[self.pos - 1][0]
        return 0

    def _record_unparsed(self, lineno, text, reason=""):
        msg = f"未解析内容 line={lineno}: {text}"
        if reason:
            msg += f" | reason={reason}"
        self.logger.warning(msg)
        self.unparsed_blocks.append({
            "line": lineno,
            "text": str(text),
            "reason": reason,
        })

    # ── 基础读取 ──────────────────────────────────────────────────────────────

    def _read_floats(self):
        """读取连续浮点数（支持N*val），遇到*关键字停止"""
        vals = []
        while self._peek():
            _, tok = self._peek()
            if _is_kw(tok):
                break
            expanded = _expand_repeat(tok)
            if expanded is not None:
                vals.extend(expanded)
                self.pos += 1
                continue
            try:
                vals.append(_to_float(tok))
                self.pos += 1
            except ValueError:
                break
        return vals

    def _peek_modifier(self):
        """查看下一个token是否是 *CON/*KVAR/*IVAR/*JVAR/*ALL/*IJK 修饰词"""
        t = self._peek()
        if not t:
            return None
        _, tok = t
        if tok.upper() in ("*CON", "*KVAR", "*IVAR", "*JVAR", "*ALL", "*IJK"):
            return tok.upper()
        return None

    # ── 通用 handler：array（带修饰词）────────────────────────────────────────

    def _handle_array(self, entry, R):
        json_spec = entry["json"]
        unit = entry.get("unit", "")
        lineno = self._last_lineno()
        src = f"{json_spec['section']} {json_spec['key']} 第{lineno}行"
        section = json_spec["section"]
        key = json_spec["key"]

        mod = self._peek_modifier()
        if mod:
            self.pos += 1
            vals = self._read_floats()
            mod_name = mod.lstrip("*")
            if not vals:
                return
            if mod_name == "CON":
                R[section][key] = _scalar(vals[0], unit, src, modifier="CON")
            else:
                if len(vals) == 1:
                    R[section][key] = _scalar(vals[0], unit, src, modifier=mod_name)
                else:
                    R[section][key] = _array(vals, unit, src, modifier=mod_name)
        else:
            vals = self._read_floats()
            if not vals:
                return
            if len(vals) == 1:
                R[section][key] = _scalar(vals[0], unit, src)
            else:
                R[section][key] = _array(vals, unit, src)

    # ── 通用 handler：scalar_inline（同行单值）────────────────────────────────

    def _handle_scalar_inline(self, entry, R):
        json_spec = entry["json"]
        unit = entry.get("unit", "")
        lineno = self._last_lineno()
        src = f"{json_spec['section']} {json_spec['key']} 第{lineno}行"
        section = json_spec["section"]
        key = json_spec["key"]

        t = self._peek()
        if not t:
            return
        _, tok = t
        if _is_kw(tok):
            return
        if tok.upper() == "*CON":
            self.pos += 1
            vals = self._read_floats()
            if vals:
                R[section][key] = _scalar(vals[0], unit, src)
            return
        try:
            self.pos += 1
            R[section][key] = _scalar(_to_float(tok), unit, src)
        except ValueError:
            self._record_unparsed(self._last_lineno(), tok, reason=f"invalid scalar for {key}")

    # ── 通用 handler：pvt6（6列PVT表）────────────────────────────────────────

    def _handle_pvt6(self, R):
        cols = ["p", "rs", "bo", "eg", "viso", "visg"]
        rows = []
        while self._peek():
            _, tok = self._peek()
            if _is_kw(tok):
                break
            row = []
            for _ in range(6):
                t = self._peek()
                if t and not _is_kw(t[1]):
                    expanded = _expand_repeat(t[1])
                    if expanded:
                        row.extend(expanded)
                        self.pos += 1
                    else:
                        try:
                            row.append(_to_float(t[1]))
                            self.pos += 1
                        except ValueError:
                            break
                else:
                    break
            if len(row) == 6:
                rows.append(row)
            elif row:
                break
        if rows:
            R["fluid"]["pvt_table"] = _table(cols, rows, "fluid *PVT")

    # ── 通用 handler：rpt_table（相渗表）────────────────────────────────────

    def _handle_rpt_table(self, entry, R):
        json_spec = entry["json"]
        columns = entry.get("columns", [])
        ncols = len(columns)
        src = f"rockfluid {json_spec['key']}"

        nums = []
        while self._peek():
            _, tok = self._peek()
            if _is_kw(tok):
                break
            self.pos += 1
            expanded = _expand_repeat(tok)
            if expanded:
                nums.extend(expanded)
                continue
            try:
                nums.append(_to_float(tok))
            except ValueError:
                pass

        rows = []
        i = 0
        while i + ncols - 1 < len(nums):
            rows.append(nums[i:i + ncols])
            i += ncols
        if rows:
            R[json_spec["section"]][json_spec["key"]] = _table(columns, rows, src)

    # ── 通用 handler：grid_header ────────────────────────────────────────────

    def _handle_grid_header(self, R):
        """*GRID *CART/*RADIAL ni nj nk"""
        t = self._peek()
        if t and _is_kw(t[1]):
            _, gkw = self._next()
            R["grid"]["grid_type"] = gkw.lstrip("*").upper()
        dims = []
        for _ in range(3):
            t = self._peek()
            if t and not _is_kw(t[1]):
                try:
                    dims.append(int(t[1]))
                    self.pos += 1
                except ValueError:
                    break
            else:
                break
        if len(dims) == 3:
            R["grid"]["ni"], R["grid"]["nj"], R["grid"]["nk"] = dims

    # ── 通用 handler：depth ──────────────────────────────────────────────────

    def _handle_depth(self, R):
        """*DEPTH i j k value"""
        nums = []
        for _ in range(4):
            t = self._peek()
            if t and not _is_kw(t[1]):
                try:
                    nums.append(_to_float(t[1]))
                    self.pos += 1
                except ValueError:
                    break
            else:
                break
        if len(nums) == 4:
            R["grid"]["depth_ref_block"] = {
                "type": "scalar", "value": nums[3], "unit": "ft",
                "i": int(nums[0]), "j": int(nums[1]), "k": int(nums[2]),
                "confidence": 0.99, "source": "grid *DEPTH"
            }

    # ── 通用 handler：skip_int ───────────────────────────────────────────────

    def _handle_skip_int(self):
        """*RPT：消耗后面的整数"""
        t = self._peek()
        if t and not _is_kw(t[1]):
            try:
                int(t[1])
                self.pos += 1
            except ValueError:
                self._record_unparsed(t[0], t[1], reason="expected integer after *RPT")

    # ── 通用 handler：skip_modifiers ─────────────────────────────────────────

    def _handle_skip_modifiers(self):
        """*NORM/*AIM：消耗后面的修饰词和数值，直到遇到真正的*关键字"""
        _MODS = {"*PRESS", "*SATUR", "*THRESH", "*NONE", "*CHANGE",
                 "*PRESS", "*RESID", "*NEWT", "*WEIGHT", "*UNWEIGHT"}
        while self._peek():
            _, tok2 = self._peek()
            if _is_kw(tok2) and tok2.upper() not in _MODS:
                break
            self.pos += 1

    # ── 自定义：单位制 ────────────────────────────────────────────────────────

    def _parse_inunit(self, R):
        t = self._peek()
        if t:
            R["meta"]["unit_system"] = t[1].lstrip("*").lower()
            self.pos += 1

    def _parse_kdir(self, R):
        """*KDIR *DOWN|*UP 或 *KDIR DOWN|UP"""
        t = self._peek()
        if not t:
            return

        _, tok = t
        kdir = None
        if tok.startswith("*"):
            kdir = tok.lstrip("*").upper()
            self.pos += 1
        elif not _is_kw(tok):
            kdir = tok.upper()
            self.pos += 1

        if kdir in ("DOWN", "UP"):
            R["grid"]["kdir"] = kdir

    # ── 自定义：井定义 ────────────────────────────────────────────────────────

    def _parse_well(self, R, in_run_section):
        if not in_run_section:
            return
        nums = []
        name = None
        for _ in range(2):
            t = self._peek()
            if not t or _is_kw(t[1]):
                break
            _, tok = self._next()
            if tok.startswith("'"):
                name = tok.strip("'")
            else:
                try:
                    nums.append(int(tok))
                except ValueError:
                    pass
        well_index = nums[0] if nums else len(R["wells"]) + 1
        R["wells"].append({
            "well_name": name or f"W{well_index}",
            "well_index": well_index,
            "well_type": None,
            "perforations": [],
            "well_radius": None,
            "bhp_max": None, "bhp_min": None,
            "rate_max": None,
            "inj_fluid": None,
            "alter_schedule": [],
            "geofac": None, "wfrac": None, "skin": None,
        })

    def _parse_producer(self, R, in_run_section):
        if not in_run_section or not R["wells"]:
            return
        R["wells"][-1]["well_type"] = "PRODUCER"
        t = self._peek()
        if t and not _is_kw(t[1]):
            try:
                int(t[1])
                self.pos += 1
            except ValueError:
                pass

    def _parse_injector(self, R, in_run_section):
        if not in_run_section or not R["wells"]:
            return
        R["wells"][-1]["well_type"] = "INJECTOR"
        _MODS = {"*UNWEIGHT", "*WEIGHT"}
        while self._peek():
            _, t2 = self._peek()
            if _is_kw(t2) and t2.upper() not in _MODS:
                break
            self.pos += 1

    def _parse_incomp(self, R, in_run_section):
        if not in_run_section or not R["wells"]:
            return
        t = self._peek()
        if t and _is_kw(t[1]):
            _, fluid_kw = self._next()
            R["wells"][-1]["inj_fluid"] = fluid_kw.lstrip("*").upper()

    def _parse_operate(self, R, in_run_section):
        if not in_run_section or not R["wells"]:
            return
        _OPERATE_MODS = {"*MAX", "*MIN", "*BHP", "*STO", "*STG", "*STW",
                         "*RESV", "*DRAWDOWN", "*RATIO"}
        parts = []
        while self._peek():
            _, tok2 = self._peek()
            if _is_kw(tok2) and tok2.upper() not in _OPERATE_MODS:
                break
            parts.append(tok2)
            self.pos += 1

        # 解析 *MAX/*MIN *BHP/*STO/*STG value
        mode = None
        target = None
        value = None
        for i, p in enumerate(parts):
            pu = p.upper()
            if pu in ("*MAX", "*MIN"):
                mode = pu.lstrip("*")
            elif pu in ("*BHP", "*STO", "*STG", "*STW", "*RESV"):
                target = pu.lstrip("*")
            else:
                try:
                    value = _to_float(p)
                except ValueError:
                    pass
        if target and value is not None:
            w = R["wells"][-1]
            if target == "BHP":
                if mode == "MAX":
                    w["bhp_max"] = value
                else:
                    w["bhp_min"] = value
            elif target in ("STO", "STG", "STW"):
                if mode == "MAX":
                    w["rate_max"] = value

    def _parse_perf(self, R, in_run_section, perf_kw="*PERF"):
        if not in_run_section or not R["wells"]:
            return
        # 可选：井号
        t = self._peek()
        if t and not _is_kw(t[1]):
            try:
                int(t[1])
                self.pos += 1
            except ValueError:
                pass
        # 读取所有射孔行：i j k wi
        w = R["wells"][-1]
        while self._peek():
            _, tok = self._peek()
            if _is_kw(tok):
                break
            nums = []
            for _ in range(4):
                t2 = self._peek()
                if t2 and not _is_kw(t2[1]):
                    expanded = _expand_repeat(t2[1])
                    if expanded:
                        nums.extend(expanded)
                        self.pos += 1
                    else:
                        try:
                            nums.append(_to_float(t2[1]))
                            self.pos += 1
                        except ValueError:
                            break
                else:
                    break
            if len(nums) >= 3:
                wi = nums[3] if len(nums) >= 4 else -1.0
                if wi <= 0:
                    wi = -1.0  # 占位符，由 generator 计算
                w["perforations"].append({
                    "i": int(nums[0]), "j": int(nums[1]), "k": int(nums[2]),
                    "wi": wi,
                    "perf_type": perf_kw.lstrip("*"),
                })
            else:
                break

    def _parse_perfv(self, R, in_run_section):
        self._parse_perf(R, in_run_section, "*PERFV")

    def _parse_geometry(self, R, in_run_section):
        if not in_run_section or not R["wells"]:
            return
        # *GEOMETRY *K rad [geofac wfrac skin]
        t = self._peek()
        if t and _is_kw(t[1]):
            self.pos += 1  # 消耗 *K/*I/*J
        nums = []
        for _ in range(4):
            t = self._peek()
            if t and not _is_kw(t[1]):
                try:
                    nums.append(_to_float(t[1]))
                    self.pos += 1
                except ValueError:
                    break
            else:
                break
        if nums:
            w = R["wells"][-1]
            w["well_radius"] = nums[0]
            if len(nums) > 1: w["geofac"] = nums[1]
            if len(nums) > 2: w["wfrac"] = nums[2]
            if len(nums) > 3: w["skin"] = nums[3]

    def _parse_alter(self, R, in_run_section):
        if not in_run_section or not R["wells"]:
            return
        t = self._peek()
        if not t or _is_kw(t[1]):
            return
        try:
            well_idx = int(t[1])
            self.pos += 1
        except ValueError:
            return
        t = self._peek()
        if not t or _is_kw(t[1]):
            return
        try:
            new_rate = _to_float(t[1])
            self.pos += 1
        except ValueError:
            return
        for w in reversed(R["wells"]):
            if w.get("well_index") == well_idx:
                w["alter_schedule"].append({
                    "time": R.get("_current_time", 0.0),
                    "rate": new_rate,
                })
                break

    def _parse_time(self, R, in_run_section):
        if not in_run_section:
            return
        t = self._peek()
        if t and not _is_kw(t[1]):
            try:
                R["_current_time"] = _to_float(t[1])
                self.pos += 1
            except ValueError:
                pass

    def _parse_date(self, R, in_run_section):
        if not in_run_section:
            return
        parts = []
        for _ in range(3):
            t = self._peek()
            if t and not _is_kw(t[1]):
                parts.append(t[1])
                self.pos += 1
            else:
                break
        if len(parts) == 3:
            R["meta"]["start_date"] = "-".join(parts)

    def _parse_density_typed(self, R):
        """*DENSITY *OIL/*GAS/*WATER value"""
        t = self._peek()
        if not t or not _is_kw(t[1]):
            return
        _, dtype = self._next()
        dtype_u = dtype.lstrip("*").upper()
        t = self._peek()
        if not t or _is_kw(t[1]):
            return
        try:
            val = _to_float(t[1])
            self.pos += 1
        except ValueError:
            return
        lineno = self._last_lineno()
        src = f"fluid *DENSITY *{dtype_u} 第{lineno}行"
        key_map = {"OIL": "oil_density", "GAS": "gas_density", "WATER": "water_density"}
        unit_map = {"OIL": "lb/ft3", "GAS": "lb/ft3", "WATER": "lb/ft3"}
        key = key_map.get(dtype_u)
        if key:
            R["fluid"][key] = _scalar(val, unit_map.get(dtype_u, "lb/ft3"), src)

    # ── 主解析流程 ────────────────────────────────────────────────────────────

    def parse(self):
        self._load_tokens()
        kw_map = self._rl.cmg_kw_map()
        ignore_set = self._rl.cmg_ignore_set()

        R = {
            "meta": {
                "source_software": "cmg_imex",
                "source_file": self.filepath.name,
                "unit_system": "field",
                "conversion_timestamp": datetime.now().isoformat(),
                "start_date": None,
                "dtwell": None,
            },
            "grid": {}, "reservoir": {}, "fluid": {},
            "rockfluid": {}, "initial": {}, "numerical": {},
            "wells": [],
            "_current_time": 0.0,
        }

        in_run_section = False
        unknown_keys = []

        while self._peek():
            lineno, tok = self._next()
            u = tok.upper()

            # 忽略关键字
            if u in ignore_set:
                continue

            # *RUN 标记动态段开始
            if u == "*RUN":
                in_run_section = True
                continue

            # ── 从 YAML 注册表分发 ─────────────────────────────────────────
            if u in kw_map:
                entry = kw_map[u]
                fmt = entry["format"]

                if fmt == "array":
                    self._handle_array(entry, R)
                elif fmt == "scalar_inline":
                    if entry.get("json", {}).get("key") == "dtwell":
                        # dtwell 直接存 meta
                        t2 = self._peek()
                        if t2 and not _is_kw(t2[1]):
                            try:
                                R["meta"]["dtwell"] = _to_float(t2[1])
                                self.pos += 1
                            except ValueError:
                                self._record_unparsed(t2[0], t2[1], reason="invalid *DTWELL value")
                    else:
                        self._handle_scalar_inline(entry, R)
                elif fmt == "pvt6":
                    self._handle_pvt6(R)
                elif fmt == "density_typed":
                    self._parse_density_typed(R)
                elif fmt == "rpt_table":
                    self._handle_rpt_table(entry, R)
                elif fmt == "grid_header":
                    self._handle_grid_header(R)
                elif fmt == "depth":
                    self._handle_depth(R)
                elif fmt == "skip_int":
                    self._handle_skip_int()
                elif fmt == "skip_modifiers":
                    self._handle_skip_modifiers()
                elif fmt == "custom":
                    handler_name = entry["handler"]
                    handler = getattr(self, handler_name)
                    # 根据方法签名决定是否传 in_run_section
                    import inspect
                    sig = inspect.signature(handler)
                    params = list(sig.parameters.keys())
                    if "in_run_section" in params:
                        handler(R, in_run_section)
                    else:
                        handler(R)
            else:
                # 未注册关键字，记录并保留上下文
                self._record_unparsed(lineno, tok, reason="unknown keyword")
                if u not in unknown_keys:
                    unknown_keys.append(u)

        if unknown_keys:
            R["unknown_keywords"] = {k: [] for k in unknown_keys}

        if self.unparsed_blocks:
            R["unparsed_blocks"] = self.unparsed_blocks

        R.pop("_current_time", None)
        return R


# ── 对外接口 ──────────────────────────────────────────────────────────────────

def parse_cmg(filepath, output_json=None, report_dir="outputs/reports/parsers"):
    r = CMGParser(filepath).parse()
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(r, f, indent=2, ensure_ascii=False)

    unknown = r.get("unknown_keywords", {}) or {}
    warnings = []
    if unknown:
        warnings.append(f"存在未注册关键字 {len(unknown)} 个，请补充 keyword_registry.yaml")

    summary = [
        ("网格", f"{r.get('grid', {}).get('ni')} x {r.get('grid', {}).get('nj')} x {r.get('grid', {}).get('nk')}"),
        ("K层方向", r.get("grid", {}).get("kdir", "(未指定，CMG默认)")),
        ("井数量", len(r.get("wells", []))),
        ("PVT 行数", len(r.get("fluid", {}).get("pvt_table", {}).get("rows", []))),
        ("SWT 行数", len(r.get("rockfluid", {}).get("swt_table", {}).get("rows", []))),
        ("未知关键字数", len(unknown)),
    ]

    md_path, json_path = write_report_bundle(
        report_dir=report_dir,
        source_name=Path(filepath).name,
        report_type="parse_cmg",
        title="CMG 解析报告",
        summary_items=summary,
        warnings=warnings,
        errors=[],
        details={
            "unknown_keywords": unknown,
            "start_date": r.get("meta", {}).get("start_date"),
            "unit_system": r.get("meta", {}).get("unit_system"),
            "kdir": r.get("grid", {}).get("kdir"),
        },
    )
    r["_parse_report"] = {"md": str(md_path), "json": str(json_path)}
    return r


if __name__ == "__main__":
    default_input = Path("inputs/cmg/mxspe001.dat")
    f = Path(sys.argv[1]) if len(sys.argv) > 1 else default_input

    out_dir = Path("outputs/json")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{f.stem}_parsed.json"

    d = parse_cmg(f, str(out))
    g = d["grid"]
    print(f"Grid:      {g.get('ni')} x {g.get('nj')} x {g.get('nk')}  type={g.get('grid_type')}")
    print(f"Porosity:  {d['reservoir'].get('porosity', {}).get('type', 'not_found')}")
    print(f"PVT rows:  {len(d['fluid'].get('pvt_table', {}).get('rows', []))}")
    print(f"SWT rows:  {len(d['rockfluid'].get('swt_table', {}).get('rows', []))}")
    print(f"Wells:     {len(d['wells'])}")
    print(f"Start:     {d['meta'].get('start_date')}")
    print(f"JSON:      {out}")