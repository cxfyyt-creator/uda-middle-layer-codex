# =============================================================================
# cmg_generator.py  —  通用JSON dict → CMG IMEX .dat
# v2：保留modifier、4列相渗、PERFV、DATE/ALTER/TIME
# =============================================================================

import json
from pathlib import Path

def _fmt(v):
    if isinstance(v, int): return str(v)
    if v == 0.0: return "0.0"
    if abs(v) >= 0.001 and abs(v) < 1e6:
        return f"{v:.10g}"
    return f"{v:.6E}"

def _vals(obj):
    return [obj["value"]] if obj["type"] == "scalar" else obj["values"]

def _interp(xy_pairs, x):
    """线性插值：给定 [(x0,y0),(x1,y1),...] 和 x，返回插值 y"""
    if not xy_pairs:
        return 0.0
    if x <= xy_pairs[0][0]:
        return xy_pairs[0][1]
    if x >= xy_pairs[-1][0]:
        return xy_pairs[-1][1]
    for i in range(len(xy_pairs)-1):
        x0, y0 = xy_pairs[i]
        x1, y1 = xy_pairs[i+1]
        if x0 <= x <= x1:
            if x1 == x0:
                return y0
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return xy_pairs[-1][1]

class CMGGenerator:
    def __init__(self, data):
        self.d = data
        self.lines = []

    def _w(self, line=""):
        self.lines.append(line)

    def _section(self, title):
        self._w()
        self._w("** " + "*"*74)
        self._w(f"** {title}")
        self._w("** " + "*"*74)

    def _write_array(self, kw, obj):
        """根据保存的modifier还原正确的写法。
        注意：如果来源是 Petrel（层序 k=1=顶层），KVAR 数组需要反转为 CMG 层序（k=1=底层）。
        """
        vals = _vals(obj)
        modifier = obj.get("modifier", "")
        is_scalar_val = obj["type"] == "scalar"

        # 判断是否需要反转：来源是 Petrel 且为 KVAR 数组
        src = obj.get("source", "")
        if (modifier == "KVAR" and not is_scalar_val and
                ("EQUALS" in src or "petrel" in src.lower() or "eclipse" in src.lower())):
            vals = list(reversed(vals))

        if is_scalar_val or modifier == "CON":
            self._w(f"{kw} *CON {_fmt(vals[0])}")
        elif modifier in ("KVAR","IVAR","JVAR"):
            self._w(f"{kw} *{modifier}")
            self._w("   " + "  ".join(_fmt(v) for v in vals))
        elif modifier == "ALL":
            self._w(f"{kw} *ALL")
            # 每行最多8个值
            for i in range(0, len(vals), 8):
                self._w("   " + "  ".join(_fmt(v) for v in vals[i:i+8]))
        else:
            if len(vals) == 1:
                self._w(f"{kw} *CON {_fmt(vals[0])}")
            else:
                self._w(f"{kw} *KVAR")
                self._w("   " + "  ".join(_fmt(v) for v in vals))

    def _gen_io(self):
        self._section("I/O Control Section")
        self._w("RESULTS SIMULATOR IMEX")
        self._w()
        src = self.d["meta"].get("source_file","unknown")
        ts  = self.d["meta"].get("conversion_timestamp","")[:10]
        self._w(f"** Generated from: {src}  ({ts})")
        self._w()
        us = self.d["meta"].get("unit_system","field").upper()
        self._w(f"*INUNIT *{us}")

    def _gen_grid(self):
        g = self.d.get("grid", {})
        if not g: return
        self._section("Reservoir Description Section")
        gtype = g.get("grid_type","CART")
        ni, nj, nk = g.get("ni",""), g.get("nj",""), g.get("nk","")
        self._w(f"*GRID *{gtype}  {ni}  {nj}  {nk}")

        for key, kw in [("di","*DI"),("dj","*DJ"),("dk","*DK")]:
            obj = g.get(key)
            if obj: self._write_array(kw, obj)

        # CMG 原生格式：*DEPTH i j k value（来自 depth_ref_block）
        depth = g.get("depth_ref_block")
        if depth:
            i = depth.get("i", 1)
            j = depth.get("j", 1)
            k = depth.get("k", 1)
            self._w(f"*DEPTH  {i}  {j}  {k}  {_fmt(depth['value'])}")
        # Petrel 来源：TOPS（顶深）→ 推算第一块中心深度
        elif g.get("tops_ref"):
            tops = g["tops_ref"]
            nk = g.get("nk", 1)
            # Petrel tops 是顶层(k=1)的顶深，CMG DEPTH 是块中心深度
            # 顶层(Petrel k=1) 在 CMG 中是最底层(k=nk)
            # 取最底层中心：tops + DK_bottom/2（若 DK 是 KVAR，取最后一层）
            dk_obj = g.get("dk")
            if dk_obj:
                dk_vals = _vals(dk_obj)
                # CMG 底层在 Petrel 的最后一个 k
                dk_bottom = dk_vals[-1] if dk_vals else 0.0
            else:
                dk_bottom = 0.0
            center_depth = tops["value"] + dk_bottom / 2.0
            self._w(f"*DEPTH  1  1  1  {_fmt(center_depth)}")

    def _gen_reservoir(self):
        r = self.d.get("reservoir", {})
        if not r: return
        self._w()
        self._w("** Rock Properties")
        for key, kw in [("porosity","*POR"),("perm_i","*PERMI"),
                        ("perm_j","*PERMJ"),("perm_k","*PERMK")]:
            obj = r.get(key)
            if obj: self._write_array(kw, obj)
        for key, kw in [("rock_ref_pressure","*PRPOR"),
                        ("rock_compressibility","*CPOR")]:
            obj = r.get(key)
            if obj: self._w(f"{kw}  {_fmt(obj['value'])}")

    def _gen_fluid(self):
        f = self.d.get("fluid", {})
        if not f: return
        self._section("Component Property Section")
        self._w("*MODEL *BLACKOIL")
        self._w()
        # CMG 原生 *PVT 表（6列：p rs bo eg viso visg）
        pvt = f.get("pvt_table")
        if pvt:
            self._w("*PVT")
            cols = pvt["columns"]
            self._w("** " + "".join(f"{c:>12}" for c in cols))
            for row in pvt["rows"]:
                self._w("   " + "".join(f"{_fmt(v):>12}" for v in row))
            self._w()
        # Petrel 来源的 PVTO（活油）+ PVDG（干气）→ 合并为 CMG *PVT 6列
        pvto = f.get("pvto_table")
        pvdg = f.get("pvdg_table")
        if pvto and not pvt:
            # 以 PVTO 为主，匹配 PVDG 中相同压力点的 eg/visg
            pvdg_map = {}
            if pvdg:
                for row in pvdg["rows"]:
                    # Petrel PVDG: p bg visg; CMG *PVT eg = 1/bg (RB/Mscf → reciprocal)
                    p = row[0]
                    bg   = row[1] if len(row) > 1 else 0.0
                    visg = row[2] if len(row) > 2 else 0.0
                    eg = (1.0 / bg) if bg > 0 else 0.0
                    pvdg_map[p] = (eg, visg)

            self._w("*PVT")
            self._w("** " + "  ".join(f"{c:>12}" for c in ["p","rs","bo","eg","viso","visg"]))
            for row in pvto["rows"]:
                rs, p, bo, viso = row[0], row[1], row[2], row[3]
                # 插值取最近的 PVDG 压力点
                if pvdg_map:
                    closest_p = min(pvdg_map.keys(), key=lambda x: abs(x - p))
                    eg, visg = pvdg_map[closest_p]
                else:
                    eg, visg = 0.0, 0.0
                vals = [p, rs, bo, eg, viso, visg]
                self._w("  " + "  ".join(f"{_fmt(v):>12}" for v in vals))
            self._w()

        for key, kw in [("oil_density","*OIL"),("gas_density","*GAS"),
                        ("water_density","*WATER")]:
            obj = f.get(key)
            if obj: self._w(f"*DENSITY {kw}  {_fmt(obj['value'])}")
        for key, kw in [("oil_compressibility","*CO"),
                        ("oil_viscosity_coeff","*CVO"),
                        ("water_fvf","*BWI"),
                        ("water_compressibility","*CW"),
                        ("water_ref_pressure","*REFPW"),
                        ("water_viscosity","*VWI"),
                        ("water_viscosity_coeff","*CVW")]:
            obj = f.get(key)
            if obj: self._w(f"{kw}  {_fmt(obj['value'])}")

    def _gen_rockfluid(self):
        rf = self.d.get("rockfluid", {})
        if not rf: return
        self._section("Rock-Fluid Property Section")
        self._w("*ROCKFLUID")
        self._w("*RPT 1")

        # ── 路径A：CMG原生 SWT / SLT ──────────────────────────────────────────
        for key, kw in [("swt_table","*SWT"),("slt_table","*SLT")]:
            tbl = rf.get(key)
            if not tbl: continue
            self._w(kw)
            cols = tbl["columns"]
            self._w("**" + "".join(f"{c:>14}" for c in cols))
            for row in tbl["rows"]:
                self._w("  " + "".join(f"{_fmt(v):>14}" for v in row))

        # ── 路径B：Petrel SWFN + SGFN + SOF3 → CMG *SWT / *SLT ──────────────
        swfn = rf.get("swfn_table")   # columns: sw  krw  pcow
        sgfn = rf.get("sgfn_table")   # columns: sg  krg  pcog
        sof3 = rf.get("sof3_table")   # columns: so  krow krog

        # *SWT：sw krw krow [pcow]
        # sw 来自 SWFN，krw 来自 SWFN，krow 来自 SOF3（通过 so=1-sw 插值）
        if swfn and not rf.get("swt_table"):
            self._w("*SWT")
            self._w("**" + "".join(f"{c:>14}" for c in ["sw","krw","krow","pcow"]))
            sof3_rows = sof3["rows"] if sof3 else []
            # 建立 so->krow 的查找表（用于插值）
            so_krow = [(r[0], r[1]) for r in sof3_rows] if sof3_rows else []
            for sw_row in swfn["rows"]:
                sw   = sw_row[0]
                krw  = sw_row[1]
                pcow = sw_row[2] if len(sw_row) > 2 else 0.0
                # so = 1 - sw（忽略气饱和度，假设两相）
                so = round(1.0 - sw, 8)
                krow = _interp(so_krow, so) if so_krow else 0.0
                self._w("  " + "".join(f"{_fmt(v):>14}" for v in [sw, krw, krow, pcow]))

        # *SLT：sl krg krog [pcog]，sl = 1 - sg
        # sl 来自 SGFN（转换），krg 来自 SGFN，krog 来自 SOF3
        if sgfn and not rf.get("slt_table"):
            self._w("*SLT")
            self._w("**" + "".join(f"{c:>14}" for c in ["sl","krg","krog","pcog"]))
            sof3_rows = sof3["rows"] if sof3 else []
            so_krog = [(r[0], r[2]) for r in sof3_rows] if sof3_rows else []
            # SGFN 按 sg 递增，SLT 按 sl=1-sg 排列，sl 应递减→需要反转后再逆序输出
            sgfn_rows_rev = list(reversed(sgfn["rows"]))
            for sg_row in sgfn_rows_rev:
                sg   = sg_row[0]
                krg  = sg_row[1]
                pcog = sg_row[2] if len(sg_row) > 2 else 0.0
                sl   = round(1.0 - sg, 8)
                so   = sl   # 近似：忽略连生水饱和度
                krog = _interp(so_krog, so) if so_krog else 0.0
                self._w("  " + "".join(f"{_fmt(v):>14}" for v in [sl, krg, krog, pcog]))

    def _gen_initial(self):
        ini = self.d.get("initial", {})
        if not ini: return
        self._section("Initial Conditions Section")
        self._w("*INITIAL")
        if ini.get("ref_pressure") or ini.get("woc_depth"):
            self._w("*VERTICAL *BLOCK_CENTER *WATER_OIL_GAS")
        elif ini.get("pressure"):
            self._w("*USER_INPUT")

        def _write_ini(key, kw):
            obj = ini.get(key)
            if obj is None: return
            vals = _vals(obj)
            mod = obj.get("modifier","")
            if obj["type"] == "scalar" or mod == "CON":
                self._w(f"{kw} *CON  {_fmt(vals[0])}")
            elif mod in ("KVAR","IVAR","JVAR"):
                self._w(f"{kw} *{mod}")
                self._w("   " + "  ".join(_fmt(v) for v in vals))
            else:
                self._w(f"{kw} *CON  {_fmt(vals[0])}")

        _write_ini("bubble_point_pressure",        "*PB")
        _write_ini("solvent_bubble_point_pressure", "*PBS")
        _write_ini("pressure",                     "*PRES")
        _write_ini("water_saturation",             "*SW")
        _write_ini("oil_saturation",               "*SO")
        _write_ini("gas_saturation",               "*SG")

        for key, kw in [("ref_pressure","*REFPRES"),("ref_depth","*REFDEPTH"),
                        ("woc_depth","*DWOC"),("goc_depth","*DGOC")]:
            obj = ini.get(key)
            if obj: self._w(f"{kw}  {_fmt(obj['value'])}")

    def _gen_numerical(self):
        num = self.d.get("numerical", {})
        if not num: return
        self._section("Numerical Control Section")
        self._w("*NUMERICAL")
        for key, kw in [("max_timestep","*DTMAX"),("max_steps","*MAXSTEPS")]:
            obj = num.get(key)
            if obj:
                v = obj["value"]
                self._w(f"{kw}  {int(v) if key=='max_steps' else _fmt(v)}")

    def _gen_wells(self):
        raw_wells = self.d.get("wells", [])
        # 支持 CMG 原生（有 well_index）和 Petrel 来源（无 well_index，自动编号）
        wells = []
        for i, w in enumerate(raw_wells):
            if isinstance(w.get("well_index"), int):
                wells.append(w)
            else:
                # Petrel 来源：自动分配编号
                wc = dict(w)
                wc["well_index"] = i + 1
                wells.append(wc)
        if not wells: return
        self._section("Well and Recurrent Data Section")
        self._w("*RUN")

        # 起始日期
        date = self.d["meta"].get("start_date")
        if date:
            self._w(f"*DATE {date.replace('-',' ')}")
        else:
            self._w("*DATE 1990 01 01")

        dtwell = self.d["meta"].get("dtwell")
        if dtwell: self._w(f"*DTWELL {_fmt(dtwell)}")
        else:      self._w("*DTWELL 1.0")

        for w in wells:
            self._w()
            idx  = w.get("well_index", 1)
            name = w.get("well_name","Well")
            self._w(f"*WELL {idx}  '{name}'")

            wtype = w.get("well_type","PRODUCER")
            if wtype == "INJECTOR":
                self._w(f"*INJECTOR *UNWEIGHT {idx}")
                self._w("*INCOMP *GAS")
            else:
                self._w(f"*PRODUCER {idx}")

            if w.get("rate_max") is not None:
                kw = "*STG" if wtype == "INJECTOR" else "*STO"
                self._w(f"*OPERATE *MAX {kw}  {_fmt(w['rate_max'])}")
            if w.get("rate_min") is not None:
                self._w(f"*OPERATE *MIN *STO  {_fmt(w['rate_min'])}")
            if w.get("bhp_max") is not None:
                self._w(f"*OPERATE *MAX *BHP  {_fmt(w['bhp_max'])}")
            if w.get("bhp_min") is not None:
                self._w(f"*OPERATE *MIN *BHP  {_fmt(w['bhp_min'])}  *CONT *REPEAT")

            # 井筒几何
            radius = w.get("well_radius")
            if radius is not None:
                gf   = _fmt(w.get("geofac", 0.34))
                wf   = _fmt(w.get("wfrac",  1.0))
                skin = _fmt(w.get("skin",   0.0))
                self._w(f"*GEOMETRY *K  {_fmt(radius)}  {gf}  {wf}  {skin}")

            # 射孔
            perfs = w.get("perforations", [])
            if perfs:
                ptype = perfs[0].get("perf_type","PERF")
                # COMPDAT 来源时 wi=-1 表示"由软件计算"；有 GEOMETRY 时用 *GEO，否则给默认值 1.0
                def _wi(p):
                    v = p.get("wi", 1.0)
                    if v < 0:
                        return 1.0  # 占位：CMG 在有 *GEOMETRY 时会忽略此值
                    return v
                geo_tag = "*GEO " if radius is not None else ""
                if ptype == "PERFV":
                    self._w(f"*PERFV {geo_tag}{idx}")
                    self._w("** kf   ff")
                    # 合并连续的k值范围
                    ks = sorted(set(p["k"] for p in perfs))
                    if len(ks) > 1 and ks[-1]-ks[0] == len(ks)-1:
                        self._w(f"  {ks[0]}:{ks[-1]}  {_fmt(_wi(perfs[0]))}")
                    else:
                        for p in perfs:
                            self._w(f"  {p['k']}  {_fmt(_wi(p))}")
                else:
                    self._w(f"*PERF {geo_tag}{idx}")
                    self._w("** if  jf  kf   wi")
                    for p in perfs:
                        self._w(f"   {p['i']}  {p['j']}  {p['k']}  {_fmt(_wi(p))}")

            # ALTER时间表
            alters = w.get("alter_schedule", [])
            for a in alters:
                self._w()
                self._w(f"*TIME {_fmt(a['time'])}")
                self._w(f"*ALTER")
                self._w(f"   {idx}")
                self._w(f"   {_fmt(a['rate'])}")

        self._w()
        self._w("*TIME 3650.0")
        self._w("*STOP")

    def generate(self):
        self._gen_io()
        self._gen_grid()
        self._gen_reservoir()
        self._gen_fluid()
        self._gen_rockfluid()
        self._gen_initial()
        self._gen_numerical()
        self._gen_wells()
        return "\n".join(self.lines)


def generate_cmg(data, output_path):
    text = CMGGenerator(data).generate()
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    return text


if __name__ == "__main__":
    import sys

    default_json = Path("outputs/json/mxspe001_parsed.json")
    json_file = Path(sys.argv[1]) if len(sys.argv) > 1 else default_json

    out_dir = Path("outputs/cmg")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{json_file.stem.replace('_parsed', '')}_roundtrip.dat"

    with open(json_file, encoding="utf-8") as f:
        data = json.load(f)
    generate_cmg(data, out_file)
    print(f"Generated: {out_file}")