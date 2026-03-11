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
        """根据保存的modifier还原正确的写法"""
        vals = _vals(obj)
        modifier = obj.get("modifier", "")
        is_scalar_val = obj["type"] == "scalar"

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

        depth = g.get("depth_ref_block")
        if depth:
            i = depth.get("i", 1)
            j = depth.get("j", 1)
            k = depth.get("k", 1)
            self._w(f"*DEPTH  {i}  {j}  {k}  {_fmt(depth['value'])}")

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
        pvt = f.get("pvt_table")
        if pvt:
            self._w("*PVT")
            cols = pvt["columns"]
            self._w("** " + "".join(f"{c:>12}" for c in cols))
            for row in pvt["rows"]:
                self._w("   " + "".join(f"{_fmt(v):>12}" for v in row))
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
        for key, kw in [("swt_table","*SWT"),("slt_table","*SLT")]:
            tbl = rf.get(key)
            if not tbl: continue
            self._w(kw)
            cols = tbl["columns"]
            self._w("**" + "".join(f"{c:>14}" for c in cols))
            for row in tbl["rows"]:
                self._w("  " + "".join(f"{_fmt(v):>14}" for v in row))

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
        wells = [w for w in raw_wells if isinstance(w.get("well_index"), int)]
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
                geo_tag = "*GEO " if radius is not None else ""
                if ptype == "PERFV":
                    self._w(f"*PERFV {geo_tag}{idx}")
                    self._w("** kf   ff")
                    # 合并连续的k值范围
                    ks = sorted(set(p["k"] for p in perfs))
                    if len(ks) > 1 and ks[-1]-ks[0] == len(ks)-1:
                        ff = _fmt(perfs[0]["wi"])
                        self._w(f"  {ks[0]}:{ks[-1]}  {ff}")
                    else:
                        for p in perfs:
                            self._w(f"  {p['k']}  {_fmt(p['wi'])}")
                else:
                    self._w(f"*PERF {geo_tag}{idx}")
                    self._w("** if  jf  kf   wi")
                    for p in perfs:
                        self._w(f"   {p['i']}  {p['j']}  {p['k']}  {_fmt(p['wi'])}")

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
