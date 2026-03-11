# =============================================================================
# cmg_parser.py  —  CMG IMEX .dat → 通用JSON dict
# v2：修复N*value、4列相渗、PERFV、modifier保留、DATE/ALTER/TIME等
# =============================================================================

import re, json
from datetime import datetime
from pathlib import Path

# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _strip_comments(line):
    idx = line.find("**")
    return line[:idx].strip() if idx >= 0 else line.strip()

def _is_kw(tok):
    return tok.startswith("*") and not tok.startswith("**")

def _to_float(s):
    return float(s.replace("d","e").replace("D","E"))

def _expand_repeat(tok):
    """展开 N*value 语法，如 2*8.0 → [8.0, 8.0]"""
    m = re.match(r'^(\d+)\*([0-9.eEdD+\-]+)$', tok)
    if m:
        n = int(m.group(1))
        v = _to_float(m.group(2))
        return [v] * n
    return None

def _scalar(v, unit, src, modifier=None):
    d = {"type":"scalar","value":v,"unit":unit,"confidence":0.99,"source":src}
    if modifier: d["modifier"] = modifier
    return d

def _array(vs, unit, src, modifier=None):
    d = {"type":"array","values":vs,"unit":unit,"grid_order":"IJK",
         "confidence":0.99,"source":src}
    if modifier: d["modifier"] = modifier
    return d

def _table(cols, rows, src):
    return {"type":"table","columns":cols,"rows":rows,
            "confidence":0.99,"source":src}

# ── 主解析器 ──────────────────────────────────────────────────────────────────

class CMGParser:
    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self.tokens = []
        self.pos = 0

    def _load_tokens(self):
        with open(self.filepath, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        for lineno, raw in enumerate(lines, 1):
            line = _strip_comments(raw)
            if not line: continue
            for tok in line.split():
                self.tokens.append((lineno, tok))

    def _peek(self, off=0):
        i = self.pos + off
        return self.tokens[i] if i < len(self.tokens) else None

    def _next(self):
        t = self._peek(); self.pos += 1; return t

    def _read_floats(self):
        """读取连续浮点数，支持N*value重复语法，遇到关键字停止"""
        vals = []
        while self._peek():
            _, tok = self._peek()
            if _is_kw(tok): break
            expanded = _expand_repeat(tok)
            if expanded is not None:
                vals.extend(expanded); self.pos += 1
                continue
            try:
                vals.append(_to_float(tok)); self.pos += 1
            except ValueError:
                break
        return vals

    def _scalar_prop(self, block, key, unit, R):
        """解析单值属性，支持下行值"""
        lineno, _ = self._peek(-1) if self.pos > 0 else (0, "")
        src = f"{block} {key} 第{lineno}行"
        t = self._peek()
        if not t: return
        _, tok = t
        if tok.upper() == "*CON":
            self.pos += 1
            vals = self._read_floats()
            if vals: R[block][key] = _scalar(vals[0], unit, src)
        elif not _is_kw(tok):
            try:
                self.pos += 1
                R[block][key] = _scalar(_to_float(tok), unit, src)
            except ValueError:
                pass

    def _array_prop(self, block, key, unit, R):
        """解析数组属性，保留modifier（*CON/*KVAR/*IVAR等）"""
        lineno, _ = self._peek(-1) if self.pos > 0 else (0, "")
        src = f"{block} {key} 第{lineno}行"
        t = self._peek()
        if not t: return
        _, mod = t
        mod_upper = mod.upper()

        if mod_upper == "*CON":
            self.pos += 1
            vals = self._read_floats()
            if vals: R[block][key] = _scalar(vals[0], unit, src, modifier="CON")

        elif mod_upper in ("*KVAR","*IVAR","*JVAR","*ALL","*IJK"):
            self.pos += 1
            vals = self._read_floats()
            if vals: R[block][key] = _array(vals, unit, src,
                                            modifier=mod_upper.lstrip("*"))
        else:
            vals = self._read_floats()
            if len(vals) == 1:
                R[block][key] = _scalar(vals[0], unit, src)
            elif vals:
                R[block][key] = _array(vals, unit, src)

    def _parse_grid(self, R):
        t = self._peek()
        if t and _is_kw(t[1]):
            _, gkw = self._next()
            R["grid"]["grid_type"] = gkw.lstrip("*").upper()
        dims = []
        for _ in range(3):
            t = self._peek()
            if t and not _is_kw(t[1]):
                try: dims.append(int(t[1])); self.pos += 1
                except ValueError: break
            else: break
        if len(dims) == 3:
            R["grid"]["ni"], R["grid"]["nj"], R["grid"]["nk"] = dims

    def _parse_dim(self, key, unit, R):
        lineno, _ = self._peek(-1) if self.pos > 0 else (0, "")
        src = f"grid {key} 第{lineno}行"
        t = self._peek()
        if not t: return
        _, mod = t
        mod_upper = mod.upper()
        if mod_upper in ("*CON","*KVAR","*IVAR","*JVAR"):
            self.pos += 1
            vals = self._read_floats()
            modifier = mod_upper.lstrip("*")
            if len(vals) == 1:
                R["grid"][key] = _scalar(vals[0], unit, src, modifier=modifier)
            elif vals:
                R["grid"][key] = _array(vals, unit, src, modifier=modifier)
        else:
            vals = self._read_floats()
            if len(vals) == 1: R["grid"][key] = _scalar(vals[0], unit, src)
            elif vals:         R["grid"][key] = _array(vals, unit, src)

    def _parse_depth(self, R):
        """解析 *DEPTH i j k value，保留ijk坐标"""
        nums = []
        for _ in range(4):
            t = self._peek()
            if t and not _is_kw(t[1]):
                try: nums.append(_to_float(t[1])); self.pos += 1
                except ValueError: break
            else: break
        if len(nums) == 4:
            R["grid"]["depth_ref_block"] = {
                "type": "scalar", "value": nums[3], "unit": "ft",
                "i": int(nums[0]), "j": int(nums[1]), "k": int(nums[2]),
                "confidence": 0.99, "source": "grid depth"
            }

    def _parse_pvt(self, R):
        cols = ["p","rs","bo","eg","viso","visg"]
        rows = []
        while self._peek():
            _, tok = self._peek()
            if _is_kw(tok): break
            row = []
            for _ in range(6):
                t = self._peek()
                if t and not _is_kw(t[1]):
                    expanded = _expand_repeat(t[1])
                    if expanded:
                        row.extend(expanded); self.pos += 1
                    else:
                        try: row.append(_to_float(t[1])); self.pos += 1
                        except ValueError: break
                else: break
            if len(row) == 6: rows.append(row)
            elif row: break
        if rows: R["fluid"]["pvt_table"] = _table(cols, rows, "fluid *PVT")

    def _parse_density(self, R):
        t = self._peek()
        if not t: return
        _, phase = self._next()
        t2 = self._peek()
        if not t2 or _is_kw(t2[1]): return
        _, vt = self._next()
        km = {"OIL":"oil_density","GAS":"gas_density","WATER":"water_density"}
        k = km.get(phase.upper().lstrip("*"))
        if k: R["fluid"][k] = _scalar(_to_float(vt), "lb/ft3", f"fluid {k}")

    def _parse_rpt_table(self, kw, R):
        """
        解析相渗表，自动检测列数（3列或4列）
        SWT: sw krw krow [pcow]
        SLT: sl krg krog [pcog]
        """
        if kw == "*SWT":
            key = "swt_table"
            col3 = ["sw","krw","krow"]
            col4 = ["sw","krw","krow","pcow"]
        else:
            key = "slt_table"
            col3 = ["sl","krg","krog"]
            col4 = ["sl","krg","krog","pcog"]

        # 先把所有数据行读出来
        raw_values = []
        while self._peek():
            _, tok = self._peek()
            if _is_kw(tok): break
            expanded = _expand_repeat(tok)
            if expanded:
                raw_values.extend(expanded); self.pos += 1
            else:
                try: raw_values.append(_to_float(tok)); self.pos += 1
                except ValueError: break

        if not raw_values: return

        # 自动检测列数：4列优先，但必须整除且第一列饱和度单调递增
        chosen_cols, chosen_rows = None, None
        for ncols, cols in [(4, col4), (3, col3)]:
            if len(raw_values) % ncols != 0:
                continue
            rows = [raw_values[i:i+ncols]
                    for i in range(0, len(raw_values), ncols)]
            sat = [r[0] for r in rows]
            if all(0.0 <= s <= 1.0 for s in sat) and                all(sat[i] <= sat[i+1] for i in range(len(sat)-1)):
                chosen_cols, chosen_rows = cols, rows
                break

        if chosen_cols:
            R["rockfluid"][key] = _table(chosen_cols, chosen_rows, f"rockfluid {kw}")
        elif raw_values:
            # 兜底：按3列切分
            rows = [raw_values[i:i+3] for i in range(0, len(raw_values)-2, 3)]
            R["rockfluid"][key] = _table(col3, rows, f"rockfluid {kw}")

    def _parse_well(self, R):
        lineno, _ = self._peek(-1) if self.pos > 0 else (0, "")
        # 读取井号；无有效井号则不创建井，避免误把I/O区 *WELL 当作井定义
        idx = None
        t = self._peek()
        if t and not _is_kw(t[1]):
            try:
                idx = int(t[1]); self.pos += 1
            except ValueError:
                return
        if idx is None:
            return

        # 读取井名（带引号）；缺省用 Well_<idx>
        name = f"Well_{idx}"
        t = self._peek()
        if t and t[1].startswith("'"):
            parts = []
            while self._peek():
                _, tok = self._peek()
                if _is_kw(tok): break
                self.pos += 1; parts.append(tok)
                if tok.endswith("'"): break
            parsed = " ".join(parts).strip("'").strip()
            if parsed:
                name = parsed

        # 消耗 *VERT/*HORIZ 修饰词及后续整数
        while self._peek():
            _, tok = self._peek()
            if _is_kw(tok) and tok.upper() in ("*VERT","*HORIZ","*HORI"):
                self.pos += 1
                # 消耗后面的 i j 整数
                for _ in range(2):
                    t = self._peek()
                    if t and not _is_kw(t[1]):
                        try: int(t[1]); self.pos += 1
                        except ValueError: break
                    else: break
            else:
                break

        R["wells"].append({
            "well_name": name,
            "well_type": "PRODUCER",
            "well_index": idx,
            "bhp_max": None, "bhp_min": None,
            "rate_max": None, "rate_min": None,
            "perforations": [],
            "well_radius": None,
            "alter_schedule": [],  # 存储 *ALTER 记录
            "source": f"WELL 第{lineno}行"
        })

    def _parse_operate(self, R):
        if not R["wells"]: return
        w = R["wells"][-1]
        t1 = self._peek()
        if not t1 or not _is_kw(t1[1]): return
        _, mm = self._next()
        t2 = self._peek()
        if not t2 or not _is_kw(t2[1]): return
        _, ct = self._next()
        t3 = self._peek()
        if not t3 or _is_kw(t3[1]): return
        _, vt = self._next()
        try: val = _to_float(vt)
        except ValueError: return

        # 消耗可选的 *CONT *REPEAT 修饰词
        while self._peek():
            _, tok = self._peek()
            if _is_kw(tok) and tok.upper() in ("*CONT","*REPEAT"):
                self.pos += 1
            else:
                break

        mm = mm.upper().lstrip("*")
        ct = ct.upper().lstrip("*")
        if ct == "BHP":
            if mm == "MAX": w["bhp_max"] = val
            else:           w["bhp_min"] = val
        elif ct in ("STO","STL"):
            if mm == "MAX": w["rate_max"] = val
            else:           w["rate_min"] = val
        elif ct == "STG" and mm == "MAX":
            w["rate_max"] = val

    def _parse_perf(self, R, kw="*PERF"):
        """解析 *PERF 和 *PERFV，支持 k1:k2 范围格式"""
        if not R["wells"]: return

        # 消耗 *GEO 等修饰词
        has_geo = False
        while self._peek():
            _, tok = self._peek()
            if _is_kw(tok):
                if tok.upper() == "*GEO": has_geo = True; self.pos += 1
                else: break
            else:
                # 消耗井号整数
                try: int(tok); self.pos += 1; break
                except ValueError: break

        w = R["wells"][-1]

        if kw == "*PERFV":
            # *PERFV 格式: kf ff 或 k1:k2 ff
            while self._peek():
                _, tok = self._peek()
                if _is_kw(tok): break

                # 检查是否是 k1:k2 范围格式
                range_m = re.match(r'^(\d+):(\d+)$', tok)
                if range_m:
                    k1, k2 = int(range_m.group(1)), int(range_m.group(2))
                    self.pos += 1
                    # 读取 ff（流动因子）
                    t = self._peek()
                    ff = 1.0
                    if t and not _is_kw(t[1]):
                        try: ff = _to_float(t[1]); self.pos += 1
                        except ValueError: pass
                    # 展开范围
                    for k in range(k1, k2+1):
                        w["perforations"].append({"i":1,"j":1,"k":k,"wi":ff,
                                                   "perf_type":"PERFV"})
                else:
                    # 单个k值
                    try:
                        k = int(tok); self.pos += 1
                        t = self._peek()
                        ff = 1.0
                        if t and not _is_kw(t[1]):
                            try: ff = _to_float(t[1]); self.pos += 1
                            except ValueError: pass
                        w["perforations"].append({"i":1,"j":1,"k":k,"wi":ff,
                                                   "perf_type":"PERFV"})
                    except ValueError:
                        break
        else:
            # 标准 *PERF 格式: i j k wi
            while self._peek():
                _, tok = self._peek()
                if _is_kw(tok): break
                nums = []
                for _ in range(4):
                    t = self._peek()
                    if t and not _is_kw(t[1]):
                        try: nums.append(_to_float(t[1])); self.pos += 1
                        except ValueError: break
                    else: break
                if len(nums) >= 3:
                    w["perforations"].append({
                        "i":int(nums[0]),"j":int(nums[1]),"k":int(nums[2]),
                        "wi": nums[3] if len(nums) > 3 else 1.0,
                        "perf_type":"PERF"
                    })
                elif nums: break

    def _parse_geometry(self, R):
        if not R["wells"]: return
        # 消耗方向关键字
        t = self._peek()
        if t and _is_kw(t[1]): self.pos += 1
        # rad geofac wfrac skin
        nums = []
        for _ in range(4):
            t = self._peek()
            if t and not _is_kw(t[1]):
                try: nums.append(_to_float(t[1])); self.pos += 1
                except ValueError: break
            else: break
        if nums:
            R["wells"][-1]["well_radius"] = nums[0]
            if len(nums) > 1: R["wells"][-1]["geofac"] = nums[1]
            if len(nums) > 2: R["wells"][-1]["wfrac"]  = nums[2]
            if len(nums) > 3: R["wells"][-1]["skin"]   = nums[3]

    def _parse_alter(self, R):
        """解析 *ALTER：记录井号和新速率"""
        if not R["wells"]: return
        # 读取井号
        t = self._peek()
        if not t or _is_kw(t[1]): return
        try: well_idx = int(t[1]); self.pos += 1
        except ValueError: return
        # 读取新速率
        t = self._peek()
        if not t or _is_kw(t[1]): return
        try: new_rate = _to_float(t[1]); self.pos += 1
        except ValueError: return
        # 附加到当前时间点（由调用方设置）
        for w in reversed(R["wells"]):
            if w.get("well_index") == well_idx:
                w["alter_schedule"].append({
                    "time": R.get("_current_time", 0.0),
                    "rate": new_rate
                })
                break

    # ── 主解析流程 ────────────────────────────────────────────────────────────

    def parse(self):
        self._load_tokens()
        R = {
            "meta": {
                "source_software": "cmg_imex",
                "source_file": self.filepath.name,
                "unit_system": "field",
                "conversion_timestamp": datetime.now().isoformat(),
                "start_date": None,
                "dtwell": None
            },
            "grid": {}, "reservoir": {}, "fluid": {},
            "rockfluid": {}, "initial": {}, "numerical": {},
            "wells": [],
            "_current_time": 0.0  # 内部用，跟踪当前时间
        }

        in_run_section = False

        while self._peek():
            lineno, tok = self._next()
            u = tok.upper()

            # ── 单位制 ──
            if u == "*INUNIT":
                t = self._peek()
                if t: R["meta"]["unit_system"] = t[1].lstrip("*").lower(); self.pos += 1

            # ── 网格 ──
            elif u == "*GRID":   self._parse_grid(R)
            elif u == "*DI":     self._parse_dim("di", "ft", R)
            elif u == "*DJ":     self._parse_dim("dj", "ft", R)
            elif u == "*DK":     self._parse_dim("dk", "ft", R)
            elif u == "*DEPTH":  self._parse_depth(R)

            # ── 储层 ──
            elif u == "*POR":    self._array_prop("reservoir","porosity","fraction",R)
            elif u == "*PERMI":  self._array_prop("reservoir","perm_i","md",R)
            elif u == "*PERMJ":  self._array_prop("reservoir","perm_j","md",R)
            elif u == "*PERMK":  self._array_prop("reservoir","perm_k","md",R)
            elif u == "*CPOR":   self._scalar_prop("reservoir","rock_compressibility","1/psi",R)
            elif u == "*PRPOR":  self._scalar_prop("reservoir","rock_ref_pressure","psia",R)

            # ── 流体 ──
            elif u == "*PVT":    self._parse_pvt(R)
            elif u == "*DENSITY":self._parse_density(R)
            elif u == "*BWI":    self._scalar_prop("fluid","water_fvf","RB/STB",R)
            elif u == "*CW":     self._scalar_prop("fluid","water_compressibility","1/psi",R)
            elif u == "*REFPW":  self._scalar_prop("fluid","water_ref_pressure","psia",R)
            elif u == "*VWI":    self._scalar_prop("fluid","water_viscosity","cp",R)
            elif u == "*CO":     self._scalar_prop("fluid","oil_compressibility","1/psi",R)
            elif u == "*CVO":    self._scalar_prop("fluid","oil_viscosity_coeff","1/psi",R)
            elif u == "*CVW":    self._scalar_prop("fluid","water_viscosity_coeff","1/psi",R)

            # ── 相渗 ──
            elif u == "*RPT":
                t = self._peek()
                if t and not _is_kw(t[1]):
                    try: int(t[1]); self.pos += 1
                    except ValueError: pass
            elif u == "*SWT":    self._parse_rpt_table("*SWT", R)
            elif u == "*SLT":    self._parse_rpt_table("*SLT", R)

            # ── 初始条件 ──
            elif u in ("*VERTICAL","*BLOCK_CENTER","*WATER_OIL_GAS","*USER_INPUT"): pass
            elif u == "*REFDEPTH":  self._scalar_prop("initial","ref_depth","ft",R)
            elif u == "*REFPRES":   self._scalar_prop("initial","ref_pressure","psia",R)
            elif u == "*PRES":      self._array_prop("initial","pressure","psia",R)
            elif u == "*PB":        self._array_prop("initial","bubble_point_pressure","psia",R)
            elif u == "*PBS":       self._array_prop("initial","solvent_bubble_point_pressure","psia",R)
            elif u == "*SW":        self._array_prop("initial","water_saturation","fraction",R)
            elif u == "*SO":        self._array_prop("initial","oil_saturation","fraction",R)
            elif u == "*SG":        self._array_prop("initial","gas_saturation","fraction",R)
            elif u == "*DWOC":      self._scalar_prop("initial","woc_depth","ft",R)
            elif u == "*DGOC":      self._scalar_prop("initial","goc_depth","ft",R)

            # ── 数值控制 ──
            elif u == "*DTMAX":   self._scalar_prop("numerical","max_timestep","day",R)
            elif u == "*MAXSTEPS":self._scalar_prop("numerical","max_steps","–",R)
            elif u in ("*NORM","*AIM"):
                # 消耗后面的修饰词和数值
                while self._peek():
                    _, tok2 = self._peek()
                    if _is_kw(tok2) and tok2.upper() not in (
                        "*PRESS","*SATUR","*THRESH","*NONE","*PRESS","*CHANGE"): break
                    self.pos += 1

            elif u == "*RUN":
                in_run_section = True

            # ── 动态数据 ──
            elif u == "*DATE" and in_run_section:
                parts = []
                for _ in range(3):
                    t = self._peek()
                    if t and not _is_kw(t[1]):
                        parts.append(t[1]); self.pos += 1
                    else: break
                if len(parts) == 3:
                    R["meta"]["start_date"] = "-".join(parts)

            elif u == "*DTWELL" and in_run_section:
                t = self._peek()
                if t and not _is_kw(t[1]):
                    try: R["meta"]["dtwell"] = _to_float(t[1]); self.pos += 1
                    except ValueError: pass

            elif u == "*TIME" and in_run_section:
                t = self._peek()
                if t and not _is_kw(t[1]):
                    try: R["_current_time"] = _to_float(t[1]); self.pos += 1
                    except ValueError: pass

            elif u == "*ALTER" and in_run_section:
                self._parse_alter(R)

            # ── 井 ──
            elif u == "*WELL" and in_run_section:    self._parse_well(R)
            elif u == "*INJECTOR" and in_run_section:
                if R["wells"]: R["wells"][-1]["well_type"] = "INJECTOR"
                while self._peek():
                    _, t2 = self._peek()
                    if _is_kw(t2) and t2.upper() not in ("*UNWEIGHT","*WEIGHT"): break
                    self.pos += 1
            elif u == "*PRODUCER" and in_run_section:
                if R["wells"]: R["wells"][-1]["well_type"] = "PRODUCER"
                t = self._peek()
                if t and not _is_kw(t[1]):
                    try: int(t[1]); self.pos += 1
                    except ValueError: pass
            elif u == "*OPERATE" and in_run_section:  self._parse_operate(R)
            elif u == "*PERF" and in_run_section:     self._parse_perf(R, "*PERF")
            elif u == "*PERFV" and in_run_section:    self._parse_perf(R, "*PERFV")
            elif u == "*GEOMETRY" and in_run_section: self._parse_geometry(R)
            # 其余关键字静默跳过

        # 清理内部状态
        R.pop("_current_time", None)
        return R


def parse_cmg(filepath, output_json=None):
    r = CMGParser(filepath).parse()
    if output_json:
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(r, f, indent=2, ensure_ascii=False)
    return r


if __name__ == "__main__":
    import sys

    default_input = Path("inputs/cmg/mxspe001.dat")
    f = Path(sys.argv[1]) if len(sys.argv) > 1 else default_input

    default_out_dir = Path("outputs/json")
    default_out_dir.mkdir(parents=True, exist_ok=True)
    out = default_out_dir / f"{f.stem}_parsed.json"

    d = parse_cmg(f, str(out))
    g = d["grid"]
    print(f"Grid: {g.get('ni')} x {g.get('nj')} x {g.get('nk')} type={g.get('grid_type')}")
    print(f"Porosity type: {d['reservoir'].get('porosity',{}).get('type','not_found')}")
    print(f"PVT rows: {len(d['fluid'].get('pvt_table',{}).get('rows',[]))}")
    print(f"Wells: {len(d['wells'])}")
    print(f"Start date: {d['meta'].get('start_date')}")
    print(f"JSON written: {out}")
