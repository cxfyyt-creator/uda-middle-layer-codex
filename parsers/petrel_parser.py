# =============================================================================
# petrel_parser.py  —  Petrel Eclipse .DATA → 通用 JSON dict
# 支持：DIMENS / EQUALS / COPY / PORO / PERMX|Y|Z / DX|Y|Z / TOPS
#       PVTO / PVDG / PVTW / DENSITY / ROCK
#       SWFN / SGFN / SOF3 / SWOF / SGOF
#       EQUIL / RSVD / PBVD
#       WELSPECS / COMPDAT / WCONPROD / WCONINJE / TSTEP / DATES
# =============================================================================

import re, json, copy
from datetime import datetime
from pathlib import Path

# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _strip_comment(line):
    idx = line.find("--")
    return line[:idx].strip() if idx >= 0 else line.strip()

def _to_float(s):
    return float(str(s).replace("d","e").replace("D","E"))

def _expand_repeat(tok):
    m = re.match(r'^(\d+)\*([0-9.eEdD+\-]+)$', str(tok))
    if m:
        return [_to_float(m.group(2))] * int(m.group(1))
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
    return {"type":"table","columns":cols,"rows":rows,"confidence":0.99,"source":src}

_MONTH_MAP = {
    "JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
    "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12,
}

# ── 词元化 ────────────────────────────────────────────────────────────────────

def _tokenize(filepath):
    tokens = []
    with open(filepath, encoding="utf-8", errors="ignore") as f:
        for lineno, raw in enumerate(f, 1):
            line = _strip_comment(raw)
            if not line:
                continue
            i = 0
            while i < len(line):
                c = line[i]
                if c in (" ", "\t", "\r", ","):  # 逗号也作分隔符（兼容 SPE2 格式）
                    i += 1
                elif c == "'":
                    j = line.find("'", i+1)
                    if j < 0:
                        j = len(line) - 1
                    tokens.append((lineno, line[i:j+1]))
                    i = j + 1
                elif c == "/":
                    tokens.append((lineno, "/"))
                    i += 1
                else:
                    j = i + 1
                    while j < len(line) and line[j] not in (" ","\t","\r","/","'",","):
                        j += 1
                    tokens.append((lineno, line[i:j]))
                    i = j
    return tokens

# ── 主解析器 ──────────────────────────────────────────────────────────────────

class PetrelParser:
    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self.tokens = []
        self.pos = 0

    def _peek(self, off=0):
        i = self.pos + off
        return self.tokens[i] if i < len(self.tokens) else None

    def _next(self):
        t = self._peek()
        self.pos += 1
        return t

    def _is_kw_tok(self, tok):
        """判断是否为 Petrel 关键字（非数值、非/、非引号字符串）"""
        if not tok or tok == "/" or tok.startswith("'"):
            return False
        if tok[0] in "0123456789.-+":
            return False
        try:
            _to_float(tok)
            return False
        except ValueError:
            pass
        return bool(re.match(r'^[A-Z][A-Z0-9_]*$', tok))

    # 这些关键字在行内出现时应该被跳过（不作为块结束标志）
    _INLINE_SKIP = {"FIELD", "METRIC", "LAB", "SI"}

    def _read_until_slash(self):
        """读取词元直到 /（含），展开 N*value，返回 token 字符串列表。

        关键规则：
        - 遇到 / 停止，并消耗同行剩余的多余词（行内注释）
        - 遇到已知单位标志（FIELD/METRIC）或时间戳词（含 :）跳过
        - 遇到其他关键字词元 → 块结束，不消耗（但如果和上一个 token 同行，也跳过）
        """
        result = []
        slash_lineno = None
        last_lineno = None

        while self._peek():
            lineno, tok = self._peek()

            if tok == "/":
                self.pos += 1
                slash_lineno = lineno
                # 消耗 / 之后同一行的多余词（行内注释）
                while self._peek():
                    next_lineno, next_tok = self._peek()
                    if next_lineno != slash_lineno:
                        break
                    if next_tok == "/" or next_tok.startswith("'"):
                        break
                    self.pos += 1
                break

            # 行内单位标志和时间戳 token 跳过
            if tok.upper() in self._INLINE_SKIP or ":" in tok:
                self.pos += 1
                last_lineno = lineno
                continue

            # 遇到关键字词元
            if self._is_kw_tok(tok):
                # 如果和上一个 token 同行（行内注释），跳过
                if last_lineno is not None and lineno == last_lineno:
                    self.pos += 1
                    continue
                # 否则是新行的真实关键字 → 块结束，不消耗
                break

            self.pos += 1
            last_lineno = lineno
            exp = _expand_repeat(tok)
            if exp is not None:
                result.extend([str(v) for v in exp])
            else:
                result.append(tok)
        return result

    def _read_floats_until_slash(self):
        vals = []
        for tok in self._read_until_slash():
            if isinstance(tok, (int, float)):
                vals.append(float(tok))
                continue
            exp = _expand_repeat(tok)
            if exp is not None:
                vals.extend(exp)
                continue
            try:
                vals.append(_to_float(tok))
            except ValueError:
                pass
        return vals

    def _read_floats_until_keyword(self):
        """
        读取所有浮点数，忽略 /，直到遇到关键字词元或文件结束。
        用于相渗表（SWFN/SGFN/SOF3）：每行有 / 但用关键字边界来停止整个块。
        """
        vals = []
        while self._peek():
            _, tok = self._peek()
            if self._is_kw_tok(tok):
                break           # 遇到关键字→停止，不消耗
            self.pos += 1
            if tok == "/":
                continue        # 跳过行内 /（每行分隔符）
            exp = _expand_repeat(tok)
            if exp is not None:
                vals.extend(exp)
                continue
            try:
                vals.append(_to_float(tok))
            except ValueError:
                pass
        return vals

    def _skip_to_slash(self):
        while self._peek():
            _, tok = self._next()
            if tok == "/":
                return

    def _parse_dimens(self, R):
        vals = self._read_floats_until_slash()
        if len(vals) >= 3:
            R["grid"]["ni"] = int(vals[0])
            R["grid"]["nj"] = int(vals[1])
            R["grid"]["nk"] = int(vals[2])
            R["grid"]["grid_type"] = "CART"

    def _parse_equals(self, R):
        """
        EQUALS 批量赋值块：
          'KW'  value  [I1 I2 J1 J2 K1 K2]  /
          ...
        /   (空记录终止)
        """
        kw_map = {
            "DX":     ("grid","di","ft"),
            "DY":     ("grid","dj","ft"),
            "DZ":     ("grid","dk","ft"),
            "TOPS":   ("grid","tops_ref","ft"),
            "DTHETA": ("grid","dtheta","deg"),   # 径向网格角度
            "PORO":   ("reservoir","porosity","fraction"),
            "PERMX":  ("reservoir","perm_i","md"),
            "PERMY":  ("reservoir","perm_j","md"),
            "PERMZ":  ("reservoir","perm_k","md"),
            "PERMR":  ("reservoir","perm_i","md"),  # 径向渗透率 → perm_i
        }
        while self._peek():
            row = self._read_until_slash()
            if not row:
                break   # 空 / → 块结束
            kw_raw = row[0].strip("'").upper()
            if kw_raw not in kw_map:
                continue
            section, key, unit = kw_map[kw_raw]

            nums = []
            for t in row[1:]:
                try:
                    nums.append(_to_float(t))
                except (ValueError, TypeError):
                    pass
            if not nums:
                continue
            value = nums[0]
            box   = [int(x) for x in nums[1:7]] if len(nums) >= 7 else None

            src = f"EQUALS {kw_raw}"
            ni  = R["grid"].get("ni", 1)
            nj  = R["grid"].get("nj", 1)
            nk  = R["grid"].get("nk", 1)

            if box and len(box) == 6:
                i1,i2,j1,j2,k1,k2 = box
                is_full_layer = (i1==1 and i2==ni and j1==1 and j2==nj)
                if is_full_layer and k1 == k2:
                    # 单层赋值 → 建立 KVAR 数组
                    existing = R[section].get(key)
                    if existing and existing["type"] == "array":
                        vals_list = existing["values"][:]
                    elif existing and existing["type"] == "scalar":
                        vals_list = [existing["value"]] * nk
                    else:
                        vals_list = [None] * nk
                    vals_list[k1-1] = value
                    vals_list = [v if v is not None else 0.0 for v in vals_list]
                    if len(set(vals_list)) == 1:
                        R[section][key] = _scalar(vals_list[0], unit, src, modifier="CON")
                    else:
                        R[section][key] = _array(vals_list, unit, src, modifier="KVAR")
                elif is_full_layer and k1 != k2:
                    # 多层连续赋值
                    existing = R[section].get(key)
                    if existing and existing["type"] == "array":
                        vals_list = existing["values"][:]
                    elif existing and existing["type"] == "scalar":
                        vals_list = [existing["value"]] * nk
                    else:
                        vals_list = [None] * nk
                    for k in range(k1-1, k2):
                        if k < nk:
                            vals_list[k] = value
                    vals_list = [v if v is not None else 0.0 for v in vals_list]
                    if len(set(vals_list)) == 1:
                        R[section][key] = _scalar(vals_list[0], unit, src, modifier="CON")
                    else:
                        R[section][key] = _array(vals_list, unit, src, modifier="KVAR")
                else:
                    # 局部 BOX（非全层）→ CON 简化
                    if R[section].get(key) is None:
                        R[section][key] = _scalar(value, unit, src+" BOX", modifier="CON")
            else:
                # 无 BOX → 全场常数，但如果已有值则累积到数组（SPE2 格式：每层单独赋值无 BOX）
                existing = R[section].get(key)
                if existing is None:
                    R[section][key] = _scalar(value, unit, src, modifier="CON")
                elif existing["type"] == "scalar":
                    # 第二次赋值：说明是逐层赋值，转为数组
                    R[section][key] = _array([existing["value"], value], unit, src, modifier="KVAR")
                elif existing["type"] == "array":
                    existing["values"].append(value)
                    existing["modifier"] = "KVAR"

    def _parse_copy(self, R):
        copy_map = {
            ("PERMX","PERMY"): ("perm_i","perm_j"),
            ("PERMX","PERMZ"): ("perm_i","perm_k"),
            ("PERMY","PERMZ"): ("perm_j","perm_k"),
            ("PERMR","PERMZ"): ("perm_i","perm_k"),  # SPE2: 径向渗透率复制到垂向
            ("PERMR","PERMY"): ("perm_i","perm_j"),
        }
        while self._peek():
            row = self._read_until_slash()
            if not row:
                break
            if len(row) < 2:
                continue
            src_kw = row[0].strip("'").upper()
            dst_kw = row[1].strip("'").upper()
            pair = (src_kw, dst_kw)
            if pair in copy_map:
                s_field, d_field = copy_map[pair]
                src_obj = R["reservoir"].get(s_field)
                if src_obj:
                    R["reservoir"][d_field] = copy.deepcopy(src_obj)
                    R["reservoir"][d_field]["source"] += f" (COPY {src_kw}→{dst_kw})"

    def _parse_simple_array(self, section, key, unit, R):
        vals = self._read_floats_until_slash()
        if not vals:
            return
        src = f"{section} {key}"
        if len(vals) == 1:
            R[section][key] = _scalar(vals[0], unit, src, modifier="CON")
        else:
            R[section][key] = _array(vals, unit, src)

    def _parse_pvtw(self, R):
        # REF_PRES  BWI  CW  VWI  CVW  /
        vals = self._read_floats_until_slash()
        if len(vals) >= 4:
            src = "PROPS PVTW"
            R["fluid"]["water_ref_pressure"]    = _scalar(vals[0], "psia", src)
            R["fluid"]["water_fvf"]             = _scalar(vals[1], "RB/STB", src)
            R["fluid"]["water_compressibility"] = _scalar(vals[2], "1/psi", src)
            R["fluid"]["water_viscosity"]       = _scalar(vals[3], "cp", src)
            if len(vals) >= 5:
                R["fluid"]["water_viscosity_coeff"] = _scalar(vals[4], "1/psi", src)

    def _parse_rock(self, R):
        # REF_PRES  COMPRESSIBILITY  /
        vals = self._read_floats_until_slash()
        if len(vals) >= 2:
            R["reservoir"]["rock_ref_pressure"]    = _scalar(vals[0], "psia", "PROPS ROCK")
            R["reservoir"]["rock_compressibility"] = _scalar(vals[1], "1/psi", "PROPS ROCK")

    def _parse_density(self, R):
        # OIL  WATER  GAS  /
        vals = self._read_floats_until_slash()
        if len(vals) >= 3:
            src = "PROPS DENSITY"
            R["fluid"]["oil_density"]   = _scalar(vals[0], "lb/ft3", src)
            R["fluid"]["water_density"] = _scalar(vals[1], "lb/ft3", src)
            R["fluid"]["gas_density"]   = _scalar(vals[2], "lb/ft3", src)

    def _parse_pvto(self, R):
        """
        PVTO 活油 PVT 表。Eclipse 格式：
          / 标记每个 RS 组的结束（不是每行结束）。
          空 / 标记整表结束。

          格式示例：
            RS  PSAT  BO  VISO  /          ← 简单组（只有饱和点）
            RS  PSAT  BO  VISO             ← 复杂组开始
                PUND  BO  VISO             ← 欠饱和点
                PUND  BO  VISO  /          ← 最后一行才有 /
          /                               ← 整表结束
        """
        rows = []
        src  = "PROPS PVTO"
        current_rs = None

        while self._peek():
            # 读取一个 RS 组（直到 /）
            group = self._read_until_slash()
            if not group:
                break   # 空 / → 整表结束

            nums = []
            for t in group:
                try:
                    nums.append(_to_float(t))
                except (ValueError, TypeError):
                    pass
            if not nums:
                break

            # 第一个值是 RS（4个及以上：饱和点组）
            if len(nums) >= 4:
                current_rs = nums[0]
                rows.append([current_rs, nums[1], nums[2], nums[3]])
                # 剩余每3个值是一个欠饱和点
                i = 4
                while i + 2 < len(nums):
                    rows.append([current_rs, nums[i], nums[i+1], nums[i+2]])
                    i += 3
            elif len(nums) == 3 and current_rs is not None:
                # 纯欠饱和行（仅在特殊格式中出现）
                rows.append([current_rs, nums[0], nums[1], nums[2]])

        if rows:
            R["fluid"]["pvto_table"] = _table(["rs","p","bo","viso"], rows, src)

    def _parse_pvdg(self, R):
        """
        PVDG 干气表。Eclipse 格式：全表共享一个末尾 /。
        所有行读到 / 结束，每行 3 列：PGAS  BG  VISGAS
        """
        rows = []
        # 一次性读到末尾 /，然后按3列切分
        nums = self._read_floats_until_slash()
        i = 0
        while i + 2 < len(nums):
            rows.append([nums[i], nums[i+1], nums[i+2]])
            i += 3
        if rows:
            R["fluid"]["pvdg_table"] = _table(["p","bg","visg"], rows, "PROPS PVDG")

    def _skip_rest_of_line(self):
        """跳过当前 token 所在行的所有剩余内容（不含 /），直到换行。
        用于处理关键字同行有垃圾文字的情况，如：
          SGFN   1 TABLES  19 NODES IN EACH   FIELD  16:31 18 JAN 85
        调用此方法后，下一个 token 将是下一行的第一个。
        """
        if not self._peek():
            return
        cur_lineno = self._peek()[0]
        while self._peek():
            lineno, tok = self._peek()
            if lineno != cur_lineno:
                break   # 换行了，停止
            self.pos += 1  # 跳过同行 token

    def _parse_table_kw(self, ncols, cols, key, section, src, R, kw_lineno=None):
        """通用相渗表解析：若关键字同行有垃圾内容则先跳过，再读表格数据"""
        # 只有当下一个 token 和关键字在同一行时，才跳过行内垃圾
        if kw_lineno is not None and self._peek() and self._peek()[0] == kw_lineno:
            self._skip_rest_of_line()
        nums = self._read_floats_until_keyword()
        rows = []
        i = 0
        while i + ncols - 1 < len(nums):
            rows.append(nums[i:i+ncols])
            i += ncols
        if rows:
            R[section][key] = _table(cols, rows, src)

    def _parse_swfn(self, R, lineno=None):
        self._parse_table_kw(3, ["sw","krw","pcow"], "swfn_table", "rockfluid", "PROPS SWFN", R, lineno)

    def _parse_sgfn(self, R, lineno=None):
        self._parse_table_kw(3, ["sg","krg","pcog"], "sgfn_table", "rockfluid", "PROPS SGFN", R, lineno)

    def _parse_sof3(self, R, lineno=None):
        self._parse_table_kw(3, ["so","krow","krog"], "sof3_table", "rockfluid", "PROPS SOF3", R, lineno)

    def _parse_swof(self, R, lineno=None):
        self._parse_table_kw(4, ["sw","krw","krow","pcow"], "swt_table", "rockfluid", "PROPS SWOF", R, lineno)

    def _parse_sgof(self, R, lineno=None):
        self._parse_table_kw(4, ["sg","krg","krog","pcog"], "slt_table", "rockfluid", "PROPS SGOF", R, lineno)

    def _parse_equil(self, R):
        # DATUM_DEPTH  DATUM_PRES  OWC  PCWOC  GOC  PCGOC  ...  /
        vals = self._read_floats_until_slash()
        if len(vals) >= 2:
            src = "SOLUTION EQUIL"
            R["initial"]["ref_depth"]    = _scalar(vals[0], "ft",   src)
            R["initial"]["ref_pressure"] = _scalar(vals[1], "psia", src)
            if len(vals) >= 3:
                R["initial"]["woc_depth"] = _scalar(vals[2], "ft", src)
            if len(vals) >= 5:
                R["initial"]["goc_depth"] = _scalar(vals[4], "ft", src)

    def _parse_rsvd(self, R):
        # DEPTH  RS  /  ...  /
        rows = []
        while self._peek():
            nums = self._read_floats_until_slash()
            if not nums: break
            if len(nums) >= 2:
                rows.append([nums[0], nums[1]])
        if rows:
            R["initial"]["rsvd_table"] = _table(["depth","rs"], rows, "SOLUTION RSVD")
            R["initial"]["solution_gor"] = _scalar(rows[0][1], "scf/STB",
                                                    "SOLUTION RSVD (first row)")

    def _find_well(self, name, R):
        name_clean = name.strip("'")
        for w in R["wells"]:
            if w["well_name"] == name_clean:
                return w
        return None

    def _parse_welspecs(self, R):
        """
        'WELLNAME' 'GROUP' I J REFDEPTH PHASE [...] /
        最后空 / 结束块。
        行首可能有时间戳垃圾（如 18 JAN 85），从第一个引号 token 开始解析。
        """
        while self._peek():
            row = self._read_until_slash()
            if not row:
                break
            # 找到第一个引号字符串的位置（井名必须是引号字符串）
            start = next((i for i, t in enumerate(row) if str(t).startswith("'")), None)
            if start is None:
                continue
            strs = [str(t).strip("'") for t in row[start:]]
            if len(strs) < 4:
                continue
            name  = strs[0]
            group = strs[1]
            try:
                ci = int(float(strs[2]))
                cj = int(float(strs[3]))
            except ValueError:
                continue
            phase = strs[5].upper() if len(strs) > 5 else "OIL"
            wtype = "INJECTOR" if phase in ("GAS","WATER") else "PRODUCER"
            R["wells"].append({
                "well_name":  name,
                "well_type":  wtype,
                "well_group": group,
                "well_i": ci, "well_j": cj,
                "phase":  phase,
                "bhp_max": None, "bhp_min": None,
                "rate_max": None, "rate_min": None,
                "perforations": [],
                "well_radius": None,
                "inj_fluid": None,
                "alter_schedule": [],
                "source": "SCHEDULE WELSPECS"
            })

    def _parse_compdat(self, R):
        """
        'WELLNAME' I J K1 K2 'OPEN/SHUT' SAT_TAB CF DIAM [...] /
        """
        while self._peek():
            row = self._read_until_slash()
            if not row:
                break
            strs = [str(t).strip("'") for t in row]
            if len(strs) < 5:
                continue
            name = strs[0]
            try:
                pi = int(strs[1])
                pj = int(strs[2])
                k1 = int(strs[3])
                k2 = int(strs[4])
            except ValueError:
                continue
            status = strs[5].upper() if len(strs) > 5 else "OPEN"
            # 井眼直径：跳过 N* 占位符，找第一个纯数字
            diam = None
            for s in strs[6:]:
                if re.match(r'^\d+\*$', s):
                    continue
                try:
                    diam = _to_float(s); break
                except ValueError:
                    continue
            w = self._find_well(name, R)
            if w is None:
                continue
            if diam is not None:
                w["well_radius"] = diam / 2.0
            for k in range(k1, k2+1):
                w["perforations"].append({
                    "i": pi, "j": pj, "k": k,
                    "wi": -1.0,
                    "status": status,
                    "perf_type": "COMPDAT"
                })

    def _parse_wconprod(self, R):
        """
        'WELLNAME' 'OPEN/SHUT' 'MODE' OIL WATER GAS LIQU RES BHP /
         0          1           2      3   4      5   6    7   8
        """
        while self._peek():
            row = self._read_until_slash()
            if not row:
                break
            strs = [str(t).strip("'") for t in row]
            if len(strs) < 3:
                continue
            name = strs[0]
            w = self._find_well(name, R)
            if w is None:
                continue
            w["well_type"] = "PRODUCER"

            def _gv(idx):
                if idx >= len(strs): return None
                s = strs[idx]
                if re.match(r'^\d+\*$', s): return None
                try: return _to_float(s)
                except ValueError: return None

            oil = _gv(3)
            bhp = _gv(8)
            if oil and oil > 0: w["rate_max"] = oil
            if bhp is not None: w["bhp_min"] = bhp

    def _parse_wconinje(self, R):
        """
        'WELLNAME' 'INJTYPE' 'OPEN/SHUT' 'MODE' RATE RESV BHP /
         0          1         2            3      4    5    6
        """
        while self._peek():
            row = self._read_until_slash()
            if not row:
                break
            strs = [str(t).strip("'") for t in row]
            if len(strs) < 4:
                continue
            name     = strs[0]
            inj_type = strs[1].upper() if len(strs) > 1 else "GAS"
            w = self._find_well(name, R)
            if w is None:
                continue
            w["well_type"]  = "INJECTOR"
            w["inj_fluid"]  = inj_type

            def _gv(idx):
                if idx >= len(strs): return None
                s = strs[idx]
                if re.match(r'^\d+\*$', s): return None
                try: return _to_float(s)
                except ValueError: return None

            rate = _gv(4)
            bhp  = _gv(6)
            if rate and rate > 0: w["rate_max"] = rate
            if bhp is not None:   w["bhp_max"] = bhp

    def _parse_tstep(self, R, current_time):
        vals = self._read_floats_until_slash()
        for dt in vals:
            current_time += dt
        return current_time

    def _parse_dates(self, R, current_time):
        row = self._read_until_slash()
        if not row:
            return current_time
        strs = [str(t).strip("'") for t in row]
        if len(strs) >= 3:
            try:
                day  = int(strs[0])
                mon  = _MONTH_MAP.get(strs[1].upper()[:3], 1)
                year = int(strs[2])
                date_str = f"{year:04d}-{mon:02d}-{day:02d}"
                R["meta"].setdefault("schedule_dates",[]).append(date_str)
            except (ValueError, IndexError):
                pass
        return current_time

    def _parse_multiply(self, R):
        """MULTIPLY: 对已有数组乘以系数。格式：'ARRAY'  FACTOR  [BOX]  /"""
        multiply_map = {
            "PERMX":("reservoir","perm_i"), "PERMY":("reservoir","perm_j"),
            "PERMZ":("reservoir","perm_k"), "PERMR":("reservoir","perm_i"),
            "PORO": ("reservoir","porosity"),
        }
        while self._peek():
            row = self._read_until_slash()
            if not row:
                break
            kw_raw = row[0].strip("'").upper()
            if kw_raw not in multiply_map:
                continue
            try:
                factor = _to_float(row[1])
            except (IndexError, ValueError):
                continue
            sec, key = multiply_map[kw_raw]
            obj = R[sec].get(key)
            if obj is None:
                continue
            if obj["type"] == "scalar":
                obj["value"] *= factor
            elif obj["type"] == "array":
                obj["values"] = [v * factor for v in obj["values"]]

    def _parse_weltarg(self, R):
        """WELTARG：动态修改井的操作目标。格式：'WELLNAME'  'TARGET'  VALUE  /"""
        while self._peek():
            row = self._read_until_slash()
            if not row:
                break
            strs = [str(t).strip("'") for t in row]
            if len(strs) < 3:
                continue
            name, target = strs[0], strs[1].upper()
            try:
                value = _to_float(strs[2])
            except ValueError:
                continue
            w = self._find_well(name, R)
            if w is None:
                continue
            w["alter_schedule"].append({"target": target, "value": value})
            if target == "ORAT":
                w["rate_max"] = value
            elif target == "BHP":
                w["bhp_min"] = value

    def _auto_consume_unknown(self, keyword, lineno, section, R):
        """
        【核心：拼音规则】
        遇到不认识的关键字，自动推断格式并消耗 tokens，存档备查。
        不再静默丢弃，而是记录下来。

        推断逻辑：
          下一个token是关键字/文件末 → flag（无参数）
          下一个token是 /           → 空记录
          下一个token是引号字符串   → 记录表（多行，空/结束）
          下一个token是数字         → 数值列表或数组
          其他                      → 跳到最近的 /
        """
        peek = self._peek()
        if peek is None:
            return {"format": "flag", "section": section, "line": lineno}

        _, next_tok = peek

        if self._is_kw_tok(next_tok):
            return {"format": "flag", "section": section, "line": lineno}

        if next_tok == "/":
            self.pos += 1
            return {"format": "empty_record", "section": section, "line": lineno}

        if next_tok.startswith("'"):
            rows = []
            while self._peek():
                row = self._read_until_slash()
                if not row:
                    break
                rows.append(row)
            return {"format": "record_table", "section": section,
                    "line": lineno, "rows": rows}

        try:
            _to_float(next_tok)
            saved_pos = self.pos
            vals = self._read_floats_until_slash()
            more = self._peek()
            if more and not self._is_kw_tok(more[1]) and more[1] != "/":
                self.pos = saved_pos
                all_vals = self._read_floats_until_keyword()
                return {"format": "array_or_table", "section": section,
                        "line": lineno, "values": all_vals, "count": len(all_vals)}
            return {"format": "value_list", "section": section,
                    "line": lineno, "values": vals, "count": len(vals)}
        except (ValueError, TypeError):
            pass

        self._skip_to_slash()
        return {"format": "unknown_skipped", "section": section, "line": lineno}

    # ── 主循环 ────────────────────────────────────────────────────────────────

    def parse(self):
        self.tokens = _tokenize(self.filepath)

        R = {
            "meta": {
                "source_software": "petrel_eclipse",
                "source_file": self.filepath.name,
                "unit_system": "field",
                "conversion_timestamp": datetime.now().isoformat(),
                "start_date": None,
            },
            "grid":      {},
            "reservoir": {},
            "fluid":     {},
            "rockfluid": {},
            "initial":   {},
            "numerical": {},
            "wells":     [],
        }

        current_time = 0.0

        # ── 关键字注册表：按"格式类型"分组，而非按关键字名称 ──────────────────
        #
        # 思路：Eclipse 有 1000+ 关键字，但格式只有几种。
        # 把关键字归类到格式类型里，parser 只学会读格式，不需要认识每个关键字。
        # 遇到注册表里没有的新关键字 → 自动推断格式类型 → 存入 unknown_keywords。
        #
        # 格式类型说明：
        #   flag          : 关键字单独一行，无参数（OIL, RADIAL, DISGAS...）
        #   unit_flag     : 同上，但影响单位系统（FIELD, METRIC, LAB）
        #   section_marker: 段名，标记当前解析段（RUNSPEC, GRID, PROPS...）
        #   skip_to_slash : 有参数但我们不关心，直接跳到 /（TUNING, EQLDIMS...）
        #   special       : 有专门解析函数的关键字

        FLAG_KWS = {
            "OIL","WATER","GAS","DISGAS","VAPOIL",
            "FMTOUT","FMTIN","UNIFOUT","UNIFIN","NONNC","RUNSUM","ALL",
            "MSUMLINES","MSUMNEWT","SEPARATE","IMPES","IMPLICIT",
            "RADIAL","CART","CORNER",  # 网格类型标志
        }
        UNIT_FLAG_KWS = {"FIELD": "field", "METRIC": "metric", "LAB": "lab", "SI": "si"}
        SECTION_KWS = {"RUNSPEC","GRID","EDIT","PROPS","REGIONS","SOLUTION","SUMMARY","SCHEDULE"}
        SKIP_TO_SLASH_KWS = {
            "EQLDIMS","TABDIMS","WELLDIMS","REGDIMS","NUPCOL","NSTACK","NUPCOIL",
            "TUNING","DRSDT","RPTSCHED","RPTGRID","RPTPROPS","RPTSOL","RPTSUM",
            "RPTREGS","RPTSMRY","FIPNUM","COLUMNS","DEBUG","NUPCOL",
            # SUMMARY 输出请求关键字（单独一行或带井名列表，跳过即可）
            "FOPR","FWPR","FLPR","FVPR","FWCT","FGOR","FPR","WBHP","WGOR",
            "BGSAT","BOSAT","BPR","PBVD","WOPR","WWPR","WGPR","WWCT",
            "MSUMLINS","MSUMNEWT","SEPARATE",
        }
        SPECIAL_KWS = {
            "TITLE","DIMENS","START",
            "DRV","INRAD","DTHETA",
            "DX","DY","DZ","TOPS","PORO","PERMX","PERMY","PERMZ",
            "PERMR","PERMZ",
            "EQUALS","COPY","MULTIPLY",
            "PVTW","ROCK","DENSITY","PVTO","PVDG","PVDO",
            "SWFN","SGFN","SOF3","SWOF","SGOF",
            "EQUIL","RSVD",
            "WELSPECS","COMPDAT","WCONPROD","WCONINJE","WELTARG",
            "TSTEP","DATES","END",
        }

        # 当前解析段（用于给 unknown_keywords 分类）
        current_section = "RUNSPEC"

        while self._peek():
            lineno, tok = self._next()
            u = tok.upper()

            # ── 1. 段名：更新当前段，不消耗数据 ─────────────────────────────
            if u in SECTION_KWS:
                current_section = u
                # RADIAL 网格标志在 GRID 段
                if u == "GRID":
                    R["grid"].setdefault("grid_type", "CART")
                continue

            # ── 2. 单位标志 ──────────────────────────────────────────────────
            if u in UNIT_FLAG_KWS:
                R["meta"]["unit_system"] = UNIT_FLAG_KWS[u]
                continue

            # ── 3. 纯标志关键字（无参数）────────────────────────────────────
            if u in FLAG_KWS:
                if u == "RADIAL":
                    R["grid"]["grid_type"] = "RADIAL"
                continue

            # ── 4. 跳过类关键字（有参数但不关心）───────────────────────────
            if u in SKIP_TO_SLASH_KWS:
                self._skip_to_slash()
                continue

            # ── 5. 有专门解析函数的关键字 ────────────────────────────────────
            if u == "END":
                break
            elif u == "TITLE":
                self._read_until_slash()
            elif u == "DIMENS":
                self._parse_dimens(R)
            elif u == "START":
                row = self._read_until_slash()
                strs = [str(t).strip("'") for t in row]
                if len(strs) >= 3:
                    try:
                        day  = int(strs[0])
                        mon  = _MONTH_MAP.get(strs[1].upper()[:3], 1)
                        year = int(strs[2])
                        R["meta"]["start_date"] = f"{year:04d}-{mon:02d}-{day:02d}"
                    except (ValueError, IndexError):
                        pass
            elif u in ("INRAD",):
                # 径向网格内径，单值
                vals = self._read_floats_until_slash()
                if vals:
                    R["grid"]["inrad"] = _scalar(vals[0], "ft", "GRID INRAD")
            elif u == "DRV":
                # 径向方向网格步长数组
                vals = self._read_floats_until_slash()
                if vals:
                    R["grid"]["drv"] = _array(vals, "ft", "GRID DRV")
            elif u in ("DX","DY","DZ","TOPS","PORO","PERMX","PERMY","PERMZ","PERMR"):
                km = {
                    "DX":("grid","di","ft"),    "DY":("grid","dj","ft"),
                    "DZ":("grid","dk","ft"),    "TOPS":("grid","tops_ref","ft"),
                    "PORO":("reservoir","porosity","fraction"),
                    "PERMX":("reservoir","perm_i","md"),
                    "PERMY":("reservoir","perm_j","md"),
                    "PERMZ":("reservoir","perm_k","md"),
                    "PERMR":("reservoir","perm_i","md"),  # 径向渗透率 → perm_i
                }
                sec, key, unt = km[u]
                self._parse_simple_array(sec, key, unt, R)
            elif u == "EQUALS":   self._parse_equals(R)
            elif u == "COPY":     self._parse_copy(R)
            elif u == "MULTIPLY": self._parse_multiply(R)
            elif u == "PVTW":     self._parse_pvtw(R)
            elif u == "ROCK":     self._parse_rock(R)
            elif u == "DENSITY":  self._parse_density(R)
            elif u == "PVTO":     self._parse_pvto(R)
            elif u in ("PVDG","PVDO"): self._parse_pvdg(R)
            elif u == "SWFN":     self._parse_swfn(R, lineno)
            elif u == "SGFN":     self._parse_sgfn(R, lineno)
            elif u == "SOF3":     self._parse_sof3(R, lineno)
            elif u == "SWOF":     self._parse_swof(R, lineno)
            elif u == "SGOF":     self._parse_sgof(R, lineno)
            elif u == "EQUIL":    self._parse_equil(R)
            elif u == "RSVD":     self._parse_rsvd(R)
            elif u == "WELSPECS": self._parse_welspecs(R)
            elif u == "COMPDAT":  self._parse_compdat(R)
            elif u == "WCONPROD": self._parse_wconprod(R)
            elif u == "WCONINJE": self._parse_wconinje(R)
            elif u == "WELTARG":  self._parse_weltarg(R)
            elif u == "TSTEP":    current_time = self._parse_tstep(R, current_time)
            elif u == "DATES":    current_time = self._parse_dates(R, current_time)

            # ── 6. 【核心】未知关键字：自动推断格式，存档备查 ───────────────
            #
            # 这里是"拼音规则"的实现：
            # 不认识这个关键字，但能看懂它后面跟的是什么格式。
            # 自动归类 + 存档，而不是静默丢弃。
            else:
                consumed = self._auto_consume_unknown(u, lineno, current_section, R)
                if consumed is not None:
                    R.setdefault("unknown_keywords", {})
                    R["unknown_keywords"][u] = consumed

        R["_total_sim_time"] = current_time
        return R


def parse_petrel(filepath, output_json=None):
    r = PetrelParser(filepath).parse()
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(r, f, indent=2, ensure_ascii=False)
    return r


if __name__ == "__main__":
    import sys
    default_input = Path("inputs/petrel/SPE1_ODEHIMPES.DATA")
    fp = Path(sys.argv[1]) if len(sys.argv) > 1 else default_input

    out_dir = Path("outputs/json")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{fp.stem}_parsed.json"

    d = parse_petrel(fp, str(out))
    g = d["grid"]
    print(f"Grid:      {g.get('ni')} x {g.get('nj')} x {g.get('nk')}  type={g.get('grid_type')}")
    print(f"Porosity:  {d['reservoir'].get('porosity',{}).get('type','not found')}  "
          f"val={d['reservoir'].get('porosity',{}).get('value','?')}")
    print(f"PermX:     {d['reservoir'].get('perm_i',{}).get('modifier','?')}  "
          f"vals={d['reservoir'].get('perm_i',{}).get('values', d['reservoir'].get('perm_i',{}).get('value','?'))}")
    print(f"PVTO rows: {len(d['fluid'].get('pvto_table',{}).get('rows',[]))}")
    print(f"PVDG rows: {len(d['fluid'].get('pvdg_table',{}).get('rows',[]))}")
    print(f"SWFN rows: {len(d['rockfluid'].get('swfn_table',{}).get('rows',[]))}")
    print(f"Wells:     {len(d['wells'])}")
    print(f"Start:     {d['meta'].get('start_date')}")
    print(f"Sim days:  {d.get('_total_sim_time', 0):.1f}")
    print(f"JSON:      {out}")
