# =============================================================================
# parsers/petrel_parser.py  —  Petrel Eclipse .DATA → 通用 JSON dict
# 架构：规则驱动 + 自定义处理器
#   - 简单关键字（array/scalar/table/flag）全部由通用 handler 处理
#   - 复杂关键字（PVTO/WELSPECS/EQUIL 等）由专属方法处理
#   - 新增简单关键字：只需在 rules/keyword_registry.yaml 中添加一行
# =============================================================================

import re
import json
import copy
import sys
import logging
from datetime import datetime
from pathlib import Path

# 把 utils 目录加入搜索路径
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.pvt_metadata import apply_pvt_role
from utils.project_paths import JSON_OUTPUT_DIR, PARSER_REPORTS_DIR
from utils.rule_loader import get_loader
from utils.reporting import write_report_bundle
from utils.value_semantics import apply_value_semantics

# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _strip_comment(line):
    # -- 注释
    idx = line.find("--")
    if idx >= 0:
        line = line[:idx]
    line = line.strip()
    # 纯分隔符行（如 ===...、---...、***...）直接丢弃
    if line and all(c in "=-*+#" for c in line):
        return ""
    return line

def _to_float(s):
    return float(str(s).replace("d", "e").replace("D", "E"))

def _expand_repeat(tok):
    m = re.match(r'^(\d+)\*([0-9.eEdD+\-]+)$', str(tok))
    if m:
        return [_to_float(m.group(2))] * int(m.group(1))
    return None

def _scalar(v, unit, src, modifier=None, distribution=None, axis=None, format_hint=None):
    d = {"type": "scalar", "value": v, "unit": unit,
         "confidence": 0.99, "source": src}
    return apply_value_semantics(
        d,
        value_type="scalar",
        modifier=modifier,
        software="petrel_eclipse",
        distribution=distribution,
        axis=axis,
        format_hint=format_hint,
    )

def _array(vs, unit, src, modifier=None, distribution=None, axis=None, format_hint=None):
    d = {"type": "array", "values": vs, "unit": unit,
         "grid_order": "IJK", "confidence": 0.99, "source": src}
    return apply_value_semantics(
        d,
        value_type="array",
        modifier=modifier,
        software="petrel_eclipse",
        distribution=distribution,
        axis=axis,
        format_hint=format_hint,
    )

def _table(cols, rows, src):
    return {"type": "table", "columns": cols, "rows": rows,
            "confidence": 0.99, "source": src}

_MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4,
    "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
    "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

# 行内噪声词（SPE文件中无注释符的说明文字）
_NOISE_WORDS = {
    "TABLES", "NODES", "IN", "EACH", "DEFAULTS", "TO", "THE",
    "WHOLE", "GRID", "BOX", "FROM", "AT", "AND", "OR", "WITH",
}

# ── 词元化 ────────────────────────────────────────────────────────────────────

def _tokenize(filepath):
    tokens = []
    with open(filepath, encoding="utf-8", errors="ignore") as f:
        for lineno, raw in enumerate(f, 1):
            line = _strip_comment(raw)
            if not line:
                continue
            # 逗号作为分隔符（部分文件用逗号分隔）
            line = line.replace(",", " ")
            i = 0
            while i < len(line):
                c = line[i]
                if c in (" ", "\t", "\r"):
                    i += 1
                elif c == "'":
                    j = line.find("'", i + 1)
                    if j < 0:
                        j = len(line) - 1
                    tokens.append((lineno, line[i:j + 1]))
                    i = j + 1
                elif c == "/":
                    tokens.append((lineno, "/"))
                    i += 1
                else:
                    j = i + 1
                    while j < len(line) and line[j] not in (" ", "\t", "\r", "/", "'"):
                        j += 1
                    tokens.append((lineno, line[i:j]))
                    i = j
    return tokens


# ── 主解析器 ──────────────────────────────────────────────────────────────────

class PetrelParser:

    def __init__(self, filepath, _load_stack=None):
        self.filepath = Path(filepath)
        self.tokens = []
        self.pos = 0
        self._current_time = 0.0
        self._time_checkpoints = [0.0]
        self._rl = get_loader()
        self.logger = logging.getLogger(__name__)
        self.unparsed_blocks = []
        self._load_stack = set(_load_stack or [])
        try:
            self._load_stack.add(str(self.filepath.resolve()).lower())
        except Exception:
            self._load_stack.add(str(self.filepath).lower())
        self._loaded_base_raw = None

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

    # ── 词元访问 ──────────────────────────────────────────────────────────────



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

    # ── 关键字识别 ────────────────────────────────────────────────────────────

    def _is_kw_tok(self, tok):
        """判断 token 是否为 Eclipse 关键字（大写字母开头，不是数值/引号/斜杠）"""
        if not tok or tok == "/" or tok.startswith("'"):
            return False
        if tok[0] in "0123456789.-+":
            return False
        try:
            _to_float(tok)
            return False
        except ValueError:
            pass
        # 含 : 的是时间戳，不是关键字
        if ":" in tok:
            return False
        return bool(re.match(r'^[A-Z_][A-Z0-9_]*$', tok))

    def _is_noise(self, tok):
        """行内噪声词（无注释符的说明文字）"""
        if ":" in tok:
            return True
        tok_u = tok.upper()
        if tok_u in _MONTH_MAP:
            return True
        if tok_u in _NOISE_WORDS:
            return True
        return False

    # ── 基础读取 ──────────────────────────────────────────────────────────────

    def _read_until_slash(self):
        """读取 token 直到遇到 /，返回中间的字符串列表（不含 /）。
        自动跳过行内噪声词。遇到关键字停止（不消耗）。"""
        result = []
        while self._peek():
            _, tok = self._peek()
            if tok == "/":
                self.pos += 1
                return result
            if self._is_kw_tok(tok):
                return result  # 不消耗关键字
            if self._is_noise(tok):
                self.pos += 1
                continue
            self.pos += 1
            exp = _expand_repeat(tok)
            if exp is not None:
                result.extend([str(v) for v in exp])
            else:
                result.append(tok)
        return result

    def _read_floats_until_slash(self):
        """读到 /，返回浮点数列表"""
        vals = []
        for tok in self._read_until_slash():
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
        """读取所有浮点数，跳过 /，直到下一个关键字（不消耗关键字）"""
        vals = []
        while self._peek():
            _, tok = self._peek()
            if self._is_kw_tok(tok):
                break
            self.pos += 1
            if tok == "/":
                continue
            if self._is_noise(tok):
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

    def _skip_to_slash(self):
        """消耗直到 / 结束（忽略内容）。
        遇到已注册的关键字（kw_map 中的条目）则停止但不消耗，
        单位制词（FIELD/METRIC等）和段名不算停止条件。"""
        kw_map = self._rl.petrel_kw_map()
        sections = set(self._rl.petrel_sections())
        unit_flags = set(self._rl.petrel_unit_flags())
        while self._peek():
            _, tok = self._peek()
            u = tok.upper()
            # 真正的关键字（在注册表里且不是单位词/段名）→ 停止
            if self._is_kw_tok(tok) and u in kw_map and u not in sections and u not in unit_flags:
                return
            self.pos += 1
            if tok == "/":
                return

    def _parse_tuning(self, R):
        """TUNING 有3行，每行以/结尾，跳过全部3行"""
        for _ in range(3):
            self._skip_to_slash()
            # 如果下一个token已经是关键字，提前结束
            t = self._peek()
            if not t or self._is_kw_tok(t[1]):
                break

    def _parse_title(self, R):
        """TITLE：消耗紧接的下一行文字（标题行），停止在真正的关键字前"""
        if not self._peek():
            return
        # 先找到标题行行号（TITLE 本身的下一行）
        kw_lineno = self.tokens[self.pos - 1][0]
        # 读到下一行结束（非空行）
        title_lineno = None
        while self._peek():
            ln, tok = self._peek()
            if tok == "/":
                self.pos += 1
                return
            if title_lineno is None:
                if ln != kw_lineno:
                    title_lineno = ln
                else:
                    self.pos += 1
                    continue
            # 已经在标题行了
            if ln != title_lineno:
                return  # 到了下一行，停止
            self.pos += 1

    def _skip_rest_of_kw_line(self, kw_lineno):
        """跳过与关键字同行的剩余内容（处理行内注释文字）"""
        while self._peek():
            ln, tok = self._peek()
            if ln != kw_lineno:
                break
            if tok == "/":
                self.pos += 1
                break
            self.pos += 1

    # ── 通用 handler：flag ─────────────────────────────────────────────────────

    def _handle_flag(self, entry, R):
        json_spec = entry.get("json", {})
        section = json_spec.get("section")
        key = json_spec.get("key")
        value = entry.get("value", True)
        if section and key and key != "_dummy" and value is not None:
            R[section][key] = value

    # ── 通用 handler：array ────────────────────────────────────────────────────

    def _handle_array(self, entry, R):
        json_spec = entry["json"]
        unit = entry.get("unit", "")
        src = f"{json_spec['section']} {json_spec['key']}"
        vals = self._read_floats_until_slash()
        if not vals:
            return
        if len(vals) == 1:
            obj = _scalar(vals[0], unit, src, modifier="CON")
        else:
            obj = _array(vals, unit, src)
        R[json_spec["section"]][json_spec["key"]] = obj

    # ── 通用 handler：scalar ───────────────────────────────────────────────────

    def _handle_scalar(self, entry, R):
        json_spec = entry["json"]
        unit = entry.get("unit", "")
        src = f"{json_spec['section']} {json_spec['key']}"
        vals = self._read_floats_until_slash()
        if vals:
            R[json_spec["section"]][json_spec["key"]] = _scalar(vals[0], unit, src)

    # ── 通用 handler：table ────────────────────────────────────────────────────

    def _read_table_sets(self, kw_lineno, ncols):
        self._skip_rest_of_kw_line(kw_lineno)
        tables = []
        current_table = []
        current_row = []
        current_lineno = None

        def flush_row():
            nonlocal current_row, current_table
            if not current_row:
                return
            chunks = []
            for i in range(0, len(current_row), ncols):
                chunk = current_row[i:i + ncols]
                if any(v is not None for v in chunk):
                    if len(chunk) < ncols:
                        chunk = chunk + [None] * (ncols - len(chunk))
                    chunks.append(chunk)
            current_table.extend(chunks)
            current_row = []

        def flush_table():
            nonlocal current_table
            if current_table:
                tables.append(current_table)
                current_table = []

        while self._peek():
            ln, tok = self._peek()
            if tok == '/':
                self.pos += 1
                flush_row()
                flush_table()
                current_lineno = None
                continue
            if self._is_kw_tok(tok):
                break
            self.pos += 1
            if self._is_noise(tok):
                continue
            if current_lineno is None:
                current_lineno = ln
            elif ln != current_lineno:
                flush_row()
                current_lineno = ln

            m_null = re.match(r'^(\d+)\*$', str(tok))
            if m_null:
                current_row.extend([None] * int(m_null.group(1)))
                continue

            exp = _expand_repeat(tok)
            if exp is not None:
                current_row.extend(exp)
                continue

            try:
                current_row.append(_to_float(tok))
            except ValueError:
                pass

        flush_row()
        flush_table()
        return tables

    def _handle_table(self, entry, kw_lineno, R):
        json_spec = entry["json"]
        columns = entry.get("columns", [])
        ncols = entry.get("ncols", len(columns))
        src = f"{json_spec['section']} {json_spec['key']}"

        table_sets = self._read_table_sets(kw_lineno, ncols)
        if not table_sets:
            return

        objs = []
        for idx, rows in enumerate(table_sets, start=1):
            obj = _table(columns, rows, src if idx == 1 else f"{src} set#{idx}")
            objs.append(obj)

        R[json_spec["section"]][json_spec["key"]] = objs[0]
        if len(objs) > 1:
            R[json_spec["section"]][f"{json_spec['key']}_sets"] = objs

    def _handle_dimens(self, R):
        vals = self._read_floats_until_slash()
        if len(vals) >= 3:
            R["grid"]["ni"] = int(vals[0])
            R["grid"]["nj"] = int(vals[1])
            R["grid"]["nk"] = int(vals[2])
            if "grid_type" not in R["grid"]:
                R["grid"]["grid_type"] = "CART"

    # ── JSON 存储辅助 ──────────────────────────────────────────────────────────

    def _set_json(self, R, json_spec, value):
        section = json_spec["section"]
        key = json_spec["key"]
        if section not in R:
            R[section] = {}
        R[section][key] = value

    def _normalize_phase_or_fluid(self, value):
        if value is None:
            return None
        txt = str(value).strip("'").strip().upper()
        if txt in ("", "1*", "NONE"):
            return None
        alias_map = {
            "WAT": "WATER",
            "WTR": "WATER",
            "SOLV": "SOLVENT",
        }
        return alias_map.get(txt, txt)

    def _resolve_related_datafile(self, stem_text):
        raw = str(stem_text).strip("'").strip()
        if not raw:
            return None
        candidate = Path(raw)
        search_dir = self.filepath.parent

        candidates = []
        if candidate.suffix:
            candidates.extend([search_dir / candidate, candidate if candidate.is_absolute() else None])
        else:
            candidates.extend([
                search_dir / f"{raw}.DATA",
                search_dir / f"{raw}.data",
                search_dir / f"{raw}.DAT",
                search_dir / raw,
            ])

        for item in candidates:
            if item and item.exists():
                return item

        raw_upper = raw.upper()
        for item in search_dir.glob('*'):
            if item.is_file() and item.stem.upper() == raw_upper and item.suffix.upper() in (".DATA", ".DAT"):
                return item
        return None

    def _merge_loaded_base(self, R, base_raw):
        if not base_raw:
            return

        for section in ("grid", "reservoir", "fluid", "rockfluid", "initial", "numerical"):
            merged = copy.deepcopy(base_raw.get(section, {}))
            merged.update(copy.deepcopy(R.get(section, {})))
            R[section] = merged

        protected_meta = {"source_software", "source_file", "conversion_timestamp"}
        base_meta = copy.deepcopy(base_raw.get("meta", {}))
        for key, value in base_meta.items():
            if key in protected_meta:
                continue
            if key not in R["meta"] or R["meta"].get(key) in (None, [], {}, ""):
                R["meta"][key] = value

        merged_wells = {str(w.get("well_name", "")).strip(): copy.deepcopy(w) for w in base_raw.get("wells", [])}
        for well in R.get("wells", []):
            merged_wells[str(well.get("well_name", "")).strip()] = copy.deepcopy(well)
        R["wells"] = [merged_wells[name] for name in sorted(merged_wells.keys()) if name]

    # ── 自定义处理器 ──────────────────────────────────────────────────────────

    def _parse_equals(self, R):
        """
        EQUALS 批量赋值块：'KW' value [I1 I2 J1 J2 K1 K2] /

        Eclipse 规则：如果某行没有指定 BOX，沿用上一行指定的 BOX。
        SPE2 正是利用这一规则：DZ/PERMR/PORO 一组，只有 DZ 带 BOX，
        后续条目继承同一层的 BOX。
        """
        kw_map_full = self._rl.petrel_kw_map()
        reverse = {}
        for kw, entry in kw_map_full.items():
            if entry.get("format") == "array" and "json" in entry:
                js = entry["json"]
                reverse[kw.upper()] = (js["section"], js["key"], entry.get("unit", ""))
        reverse.update({
            "PERMR": ("reservoir", "perm_i", "md"),
            "DTHETA": ("grid", "dtheta", "deg"),
            "TOPS": ("grid", "tops_ref", "ft"),
        })

        ni = R["grid"].get("ni", 1)
        nj = R["grid"].get("nj", 1)
        nk = R["grid"].get("nk", 1)
        last_box = None   # ← 记住最后一次指定的 BOX

        while self._peek():
            # EQUALS 每行必须以 'ARRAY_NAME' 引号 token 开头。
            # 跳过所有非引号 token（LAYER、1、IS、TERMINATED 等噪声词）。
            # 空 / 代表整个块结束。
            while self._peek():
                _, tok = self._peek()
                if tok == "/":
                    slash_lineno = self._peek()[0]
                    self.pos += 1   # 消耗 /
                    # 把同一行上 / 后面的残余 token 也消耗掉
                    # （例如 "/  EQUALS IS TERMINATED BY A NULL RECORD"）
                    while self._peek():
                        ln2, tok2 = self._peek()
                        if ln2 != slash_lineno:
                            break
                        self.pos += 1
                    return
                if tok.startswith("'"):
                    break           # 引号括起的关键字 → 是真正的数据行
                self.pos += 1       # 其他一切（数字/噪声词）均跳过

            if not self._peek():
                break

            row = self._read_until_slash()
            if not row:
                break

            kw_raw = row[0].strip("'").strip().upper()
            if kw_raw not in reverse:
                continue
            section, key, unit = reverse[kw_raw]

            nums = []
            for t in row[1:]:
                try:
                    nums.append(_to_float(t))
                except (ValueError, TypeError):
                    pass
            if not nums:
                continue

            value = nums[0]
            src = f"EQUALS {kw_raw}"

            # ── BOX 解析 ──────────────────────────────────────────────────────
            # 本行有 6 个以上的数值 → 本行显式指定了 BOX
            if len(nums) >= 7:
                box = [int(x) for x in nums[1:7]]
                last_box = box          # 更新"当前 BOX"
            elif len(nums) >= 2:
                # 有数值但不足 6 个：可能是 2~6 个，视作部分BOX或无BOX
                # 安全起见：仅当恰好 6 个整数时才算 BOX，否则沿用 last_box
                candidate = nums[1:]
                if len(candidate) == 6 and all(float(x) == int(x) for x in candidate):
                    box = [int(x) for x in candidate]
                    last_box = box
                else:
                    box = last_box      # 沿用上一行的 BOX
            else:
                box = last_box          # 无 BOX → 沿用上一行

            # ── 写入 JSON ──────────────────────────────────────────────────────
            if box and len(box) == 6:
                i1, i2, j1, j2, k1, k2 = box
                is_full_layer = (i1 == 1 and i2 == ni and j1 == 1 and j2 == nj)
                if is_full_layer:
                    # 按层写入 KVAR 数组
                    existing = R[section].get(key)
                    if existing and existing.get("type") == "array":
                        vals_list = existing["values"][:]
                    elif existing and existing.get("type") == "scalar":
                        vals_list = [existing["value"]] * nk
                    else:
                        vals_list = [None] * nk
                    for k in range(k1 - 1, min(k2, nk)):
                        vals_list[k] = value
                    vals_list = [v if v is not None else 0.0 for v in vals_list]
                    if len(set(vals_list)) == 1:
                        R[section][key] = _scalar(
                            vals_list[0],
                            unit,
                            src,
                            distribution="constant",
                            format_hint={"keyword": "EQUALS", "box_scope": "full_layer"},
                        )
                    else:
                        R[section][key] = _array(
                            vals_list,
                            unit,
                            src,
                            distribution="by_layer",
                            axis="k",
                            format_hint={"keyword": "EQUALS", "box_scope": "full_layer"},
                        )
                else:
                    # 局部 BOX（非整层）→ 简单标量，不做精细网格展开
                    if R[section].get(key) is None:
                        R[section][key] = _scalar(
                            value,
                            unit,
                            src + " BOX",
                            distribution="constant",
                            format_hint={"keyword": "EQUALS", "box_scope": "partial_box"},
                        )
            else:
                # 没有任何 BOX 信息（包括 last_box 也是 None）→ 全场常数
                R[section][key] = _scalar(
                    value,
                    unit,
                    src,
                    distribution="constant",
                    format_hint={"keyword": "EQUALS", "box_scope": "global"},
                )

    def _parse_copy(self, R):
        """COPY 'SRC' 'DST' /"""
        kw_map_full = self._rl.petrel_kw_map()
        reverse = {}
        for kw, entry in kw_map_full.items():
            if entry.get("format") == "array" and "json" in entry:
                js = entry["json"]
                reverse[kw.upper()] = (js["section"], js["key"])
        reverse["PERMR"] = ("reservoir", "perm_i")

        while self._peek():
            row = self._read_until_slash()
            if not row:
                break
            if len(row) < 2:
                continue
            src_kw = row[0].strip("'").upper()
            dst_kw = row[1].strip("'").upper()
            if src_kw in reverse and dst_kw in reverse:
                s_sec, s_key = reverse[src_kw]
                d_sec, d_key = reverse[dst_kw]
                src_obj = R[s_sec].get(s_key)
                if src_obj:
                    import copy as _copy
                    R[d_sec][d_key] = _copy.deepcopy(src_obj)
                    R[d_sec][d_key]["source"] += f" (COPY {src_kw}→{dst_kw})"

    def _parse_multiply(self, R):
        """MULTIPLY 'KW' factor /"""
        kw_map_full = self._rl.petrel_kw_map()
        reverse = {}
        for kw, entry in kw_map_full.items():
            if entry.get("format") == "array" and "json" in entry:
                js = entry["json"]
                reverse[kw.upper()] = (js["section"], js["key"])
        reverse["PERMR"] = ("reservoir", "perm_i")

        while self._peek():
            row = self._read_until_slash()
            if not row:
                break
            if len(row) < 2:
                continue
            kw_raw = row[0].strip("'").upper()
            if kw_raw not in reverse:
                continue
            try:
                factor = _to_float(row[1])
            except (ValueError, IndexError):
                continue
            section, key = reverse[kw_raw]
            obj = R[section].get(key)
            if obj is None:
                continue
            if obj["type"] == "scalar":
                obj["value"] *= factor
            elif obj["type"] == "array":
                obj["values"] = [v * factor for v in obj["values"]]

    def _parse_pvtw(self, R):
        self._skip_rest_of_kw_line(self._last_lineno())
        vals = self._read_floats_until_slash()
        if len(vals) >= 4:
            src = "PROPS PVTW"
            R["fluid"]["water_ref_pressure"] = _scalar(vals[0], "psia", src)
            R["fluid"]["water_fvf"] = _scalar(vals[1], "RB/STB", src)
            R["fluid"]["water_compressibility"] = _scalar(vals[2], "1/psi", src)
            R["fluid"]["water_viscosity"] = _scalar(vals[3], "cp", src)
            if len(vals) >= 5:
                R["fluid"]["water_viscosity_coeff"] = _scalar(vals[4], "1/psi", src)

    def _parse_rock(self, R):
        self._skip_rest_of_kw_line(self._last_lineno())
        vals = self._read_floats_until_slash()
        if len(vals) >= 2:
            R["reservoir"]["rock_ref_pressure"] = _scalar(vals[0], "psia", "PROPS ROCK")
            R["reservoir"]["rock_compressibility"] = _scalar(vals[1], "1/psi", "PROPS ROCK")

    def _parse_miscible(self, R):
        """MISCIBLE 关键字：作为模型标志，不消费后续数据。"""
        R["meta"]["model_type"] = "miscible"
        R["fluid"]["model"] = "MISCIBLE"


    def _parse_density(self, R):
        self._skip_rest_of_kw_line(self._last_lineno())
        vals = self._read_floats_until_slash()
        if len(vals) >= 3:
            src = "PROPS DENSITY"
            R["fluid"]["oil_density"] = _scalar(vals[0], "lb/ft3", src)
            R["fluid"]["water_density"] = _scalar(vals[1], "lb/ft3", src)
            R["fluid"]["gas_density"] = _scalar(vals[2], "lb/ft3", src)

    def _parse_pvto(self, R):
        self._skip_rest_of_kw_line(self._last_lineno())
        """
        PVTO 活油表。格式：
          RS  PSAT  BO  VISO  /      ← 简单组（饱和点）
          RS  PSAT  BO  VISO          ← 复杂组开始
               PUND BO  VISO          ← 欠饱和点
               PUND BO  VISO /        ← 最后一行带 /
          /                           ← 整表结束
        """
        rows = []
        current_rs = None
        while self._peek():
            group = self._read_until_slash()
            if not group:
                break
            nums = []
            for t in group:
                try:
                    nums.append(_to_float(t))
                except (ValueError, TypeError):
                    pass
            if not nums:
                break
            if len(nums) >= 4:
                current_rs = nums[0]
                rows.append([current_rs, nums[1], nums[2], nums[3]])
                i = 4
                while i + 2 < len(nums):
                    rows.append([current_rs, nums[i], nums[i + 1], nums[i + 2]])
                    i += 3
            elif len(nums) == 3 and current_rs is not None:
                rows.append([current_rs, nums[0], nums[1], nums[2]])
        if rows:
            R["fluid"]["pvto_table"] = apply_pvt_role(
                _table(["rs", "p", "bo", "viso"], rows, "PROPS PVTO"),
                pvt_form="eclipse_pvto",
                representation_role="native_source",
                preferred_backend="petrel",
            )

    def _parse_pvdg(self, R):
        self._skip_rest_of_kw_line(self._last_lineno())
        """PVDG 干气表，3列：p bg visg，整表共享一个末尾 /"""
        nums = self._read_floats_until_slash()
        rows = []
        i = 0
        while i + 2 < len(nums):
            rows.append([nums[i], nums[i + 1], nums[i + 2]])
            i += 3
        if rows:
            R["fluid"]["pvdg_table"] = apply_pvt_role(
                _table(["p", "bg", "visg"], rows, "PROPS PVDG"),
                pvt_form="eclipse_pvdg",
                representation_role="native_source",
                preferred_backend="petrel",
            )

    def _parse_equil(self, R):
        vals = self._read_floats_until_slash()
        if len(vals) >= 2:
            src = "SOLUTION EQUIL"
            R["initial"]["ref_depth"] = _scalar(vals[0], "ft", src)
            R["initial"]["ref_pressure"] = _scalar(vals[1], "psia", src)
            if len(vals) >= 3:
                R["initial"]["woc_depth"] = _scalar(vals[2], "ft", src)
            if len(vals) >= 5:
                R["initial"]["goc_depth"] = _scalar(vals[4], "ft", src)

    def _parse_rsvd(self, R):
        rows = []
        while self._peek():
            nums = self._read_floats_until_slash()
            if not nums:
                break
            if len(nums) >= 2:
                rows.append([nums[0], nums[1]])
        if rows:
            R["initial"]["rsvd_table"] = _table(["depth", "rs"], rows, "SOLUTION RSVD")

    def _parse_pbvd(self, R):
        rows = []
        while self._peek():
            nums = self._read_floats_until_slash()
            if not nums:
                break
            if len(nums) >= 2:
                rows.append([nums[0], nums[1]])
        if rows:
            R["initial"]["pbvd_table"] = _table(["pb", "depth"], rows, "SOLUTION PBVD")

    def _parse_start(self, R):
        row = self._read_until_slash()
        strs = [str(t).strip("'") for t in row]
        if len(strs) >= 3:
            try:
                dy = int(strs[0])
                mon = _MONTH_MAP.get(strs[1].upper()[:3], 1)
                yr = int(strs[2])
                R["meta"]["start_date"] = f"{yr:04d}-{mon:02d}-{dy:02d}"
            except (ValueError, IndexError):
                pass

    def _parse_load(self, R):
        row = self._read_until_slash()
        strs = [str(t).strip("'").strip() for t in row]
        if not strs:
            return
        base_path = self._resolve_related_datafile(strs[0])
        if not base_path:
            self._record_unparsed(self._last_lineno(), f"LOAD {strs[0]}", reason="load target not found")
            return
        try:
            resolved_key = str(base_path.resolve()).lower()
        except Exception:
            resolved_key = str(base_path).lower()
        if resolved_key in self._load_stack:
            self._record_unparsed(self._last_lineno(), f"LOAD {base_path.name}", reason="recursive load detected")
            return

        base_raw = PetrelParser(base_path, _load_stack=self._load_stack | {resolved_key}).parse()
        self._loaded_base_raw = base_raw
        self._merge_loaded_base(R, base_raw)
        R["meta"]["load_source_file"] = base_path.name

    def _parse_restart(self, R):
        row = self._read_until_slash()
        strs = [str(t).strip("'").strip() for t in row]
        if not strs:
            return

        restart_name = strs[0]
        restart_step = None
        if len(strs) >= 2:
            try:
                restart_step = int(float(strs[1]))
            except (ValueError, TypeError):
                restart_step = None

        if self._loaded_base_raw is None:
            base_path = self._resolve_related_datafile(restart_name)
            if base_path:
                try:
                    resolved_key = str(base_path.resolve()).lower()
                except Exception:
                    resolved_key = str(base_path).lower()
                if resolved_key not in self._load_stack:
                    self._loaded_base_raw = PetrelParser(base_path, _load_stack=self._load_stack | {resolved_key}).parse()
                    self._merge_loaded_base(R, self._loaded_base_raw)

        if self._loaded_base_raw:
            checkpoints = self._loaded_base_raw.get("_time_checkpoints") or [0.0]
            if restart_step is not None and checkpoints:
                idx = max(0, min(restart_step, len(checkpoints) - 1))
                self._current_time = float(checkpoints[idx])
                self._time_checkpoints = [self._current_time]

        R["meta"]["restart_source_file"] = restart_name
        if restart_step is not None:
            R["meta"]["restart_step"] = restart_step

    def _find_well(self, name, R):
        name_clean = str(name).strip("'").strip()
        for w in R["wells"]:
            wname = str(w["well_name"]).strip()
            if wname == name_clean:
                return w
        return None

    def _find_wells(self, name_pattern, R):
        pattern = str(name_pattern).strip("'").strip()
        if "*" in pattern:
            prefix = pattern.split("*", 1)[0]
            return [w for w in R["wells"] if str(w.get("well_name", "")).strip().startswith(prefix)]
        w = self._find_well(pattern, R)
        return [w] if w else []

    def _parse_welspecs(self, R):
        # 跳过关键字同行的时间戳等噪声（找第一个引号 token）
        while self._peek():
            _, tok = self._peek()
            if tok.startswith("'"):
                break
            if tok == "/":
                self.pos += 1
                break
            self.pos += 1

        while self._peek():
            row = self._read_until_slash()
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
            phase = self._normalize_phase_or_fluid(strs[5] if len(strs) > 5 else "OIL") or "OIL"
            wtype = "PRODUCER" if phase == "OIL" else None
            existing = self._find_well(name, R)
            if existing is None:
                R["wells"].append({
                    "well_name": name,
                    "well_type": wtype,
                    "well_group": group,
                    "well_i": ci, "well_j": cj,
                    "phase": phase,
                    "bhp_max": None, "bhp_min": None,
                    "rate_max": None, "rate_min": None,
                    "perforations": [],
                    "well_radius": None,
                    "inj_fluid": None,
                    "alter_schedule": [],
                    "source": "SCHEDULE WELSPECS"
                })
            else:
                existing.update({
                    "well_group": group,
                    "well_i": ci,
                    "well_j": cj,
                    "phase": phase,
                    "source": "SCHEDULE WELSPECS",
                })
                if wtype and not existing.get("well_type"):
                    existing["well_type"] = wtype

    def _parse_compdat(self, R):
        self._skip_rest_of_kw_line(self._last_lineno())
        while self._peek():
            row = self._read_until_slash()
            if not row:
                break
            strs = [str(t).strip("'") for t in row]
            if len(strs) < 5:
                continue
            name = strs[0].strip()
            w = self._find_well(name, R)
            if w is None:
                continue
            fields = []
            for token in strs[1:]:
                m = re.match(r'^(\d+)\*$', token)
                if m:
                    fields.extend([None] * int(m.group(1)))
                else:
                    fields.append(token)
            if len(fields) < 5:
                continue
            try:
                pi = w.get("well_i") if fields[0] is None else int(fields[0])
                pj = w.get("well_j") if fields[1] is None else int(fields[1])
                k1 = int(fields[2])
                k2 = int(fields[3])
            except (ValueError, TypeError):
                continue
            status = str(fields[4] or "OPEN").upper()
            diam = None
            for s in fields[5:]:
                if s is None or re.match(r'^\d+\*$', str(s)):
                    continue
                try:
                    diam = _to_float(s)
                    break
                except ValueError:
                    continue
            if diam is not None and diam > 0:
                w["well_radius"] = diam / 2.0
            for k in range(k1, k2 + 1):
                w["perforations"].append({
                    "i": pi, "j": pj, "k": k,
                    "wi": -1.0, "status": status,
                    "perf_type": "COMPDAT"
                })

    def _parse_wconprod(self, R):
        self._skip_rest_of_kw_line(self._last_lineno())
        while self._peek():
            row = self._read_until_slash()
            if not row:
                break
            strs = [str(t).strip("'") for t in row]
            if len(strs) < 3:
                continue
            name = strs[0].strip()
            wells = self._find_wells(name, R)
            if not wells:
                continue

            def _gv(idx):
                if idx >= len(strs):
                    return None
                s = strs[idx]
                if re.match(r'^\d+\*$', s):
                    return None
                try:
                    return _to_float(s)
                except ValueError:
                    return None

            oil = _gv(3)
            bhp = _gv(8)
            for w in wells:
                w["well_type"] = "PRODUCER"
                if oil is not None and oil > 0:
                    w["rate_max"] = oil
                if bhp is not None:
                    w["bhp_min"] = bhp

    def _parse_wconinje(self, R):
        self._skip_rest_of_kw_line(self._last_lineno())
        while self._peek():
            row = self._read_until_slash()
            if not row:
                break
            strs = [str(t).strip("'") for t in row]
            if len(strs) < 4:
                continue
            name = strs[0].strip()
            inj_type = self._normalize_phase_or_fluid(strs[1] if len(strs) > 1 else "GAS") or "GAS"
            wells = self._find_wells(name, R)
            if not wells:
                continue

            def _gv(idx):
                if idx >= len(strs):
                    return None
                s = strs[idx]
                if re.match(r'^\d+\*$', s):
                    return None
                try:
                    return _to_float(s)
                except ValueError:
                    return None

            rate = _gv(4)
            bhp = _gv(6)
            for w in wells:
                w["well_type"] = "INJECTOR"
                w["inj_fluid"] = inj_type
                if rate is not None and rate > 0:
                    w["rate_max"] = rate
                if bhp is not None:
                    w["bhp_max"] = bhp

    def _parse_weltarg(self, R):
        """WELTARG 'WELLNAME' 'TARGET' value /"""
        self._skip_rest_of_kw_line(self._last_lineno())
        while self._peek():
            row = self._read_until_slash()
            if not row:
                break
            strs = [str(t).strip("'") for t in row]
            if len(strs) < 3:
                continue
            name = strs[0].strip()
            target = strs[1].upper()
            try:
                value = _to_float(strs[2])
            except (ValueError, IndexError):
                continue
            for w in self._find_wells(name, R):
                w["alter_schedule"].append({
                    "target": target,
                    "value": value,
                    "time": self._current_time,  # 记录当前累积时间
                })

    def _parse_tstep(self, R):
        vals = self._read_floats_until_slash()
        for dt in vals:
            self._current_time += dt
            self._time_checkpoints.append(self._current_time)

    def _parse_dates(self, R):
        row = self._read_until_slash()
        strs = [str(t).strip("'") for t in row]
        if len(strs) >= 3:
            try:
                dy = int(strs[0])
                mon = _MONTH_MAP.get(strs[1].upper()[:3], 1)
                yr = int(strs[2])
                R["meta"].setdefault("schedule_dates", []).append(
                    f"{yr:04d}-{mon:02d}-{dy:02d}"
                )
            except (ValueError, IndexError):
                pass

    # ── 未知关键字自动消耗 ────────────────────────────────────────────────────

    def _auto_consume(self, keyword, R):
        """遇到未知关键字，自动推断格式并消耗 token，存入 unknown_keywords"""
        first = self._peek()
        if not first:
            return
        _, tok = first

        # 如果下一个 token 是数值或 /，按 array 处理
        is_num = False
        try:
            _to_float(tok)
            is_num = True
        except (ValueError, TypeError):
            pass

        if tok == "/" or is_num:
            vals = self._read_floats_until_slash()
            R.setdefault("unknown_keywords", {})[keyword] = vals
            self._record_unparsed(first[0], keyword, reason="unknown keyword")
        else:
            # 可能是纯标志或下一个关键字，不消耗
            pass

    # ── 主解析流程 ────────────────────────────────────────────────────────────

    def parse(self):
        self.tokens = _tokenize(self.filepath)
        self._current_time = 0.0
        self._time_checkpoints = [0.0]

        kw_map = self._rl.petrel_kw_map()
        sections = set(self._rl.petrel_sections())
        unit_flags = set(self._rl.petrel_unit_flags())

        R = {
            "meta": {
                "source_software": "petrel_eclipse",
                "source_file": self.filepath.name,
                "unit_system": "field",
                "conversion_timestamp": datetime.now().isoformat(),
                "start_date": None,
            },
            "grid": {},
            "reservoir": {},
            "fluid": {},
            "rockfluid": {},
            "initial": {},
            "numerical": {},
            "wells": [],
        }

        while self._peek():
            lineno, tok = self._next()

            # 非关键字 token（数字/引号/噪声）直接跳过
            if not self._is_kw_tok(tok):
                continue

            u = tok.upper()

            # 段名标记
            if u in sections:
                continue

            # 单位制标志
            if u in unit_flags:
                R["meta"]["unit_system"] = u.lower()
                continue

            # 文件结束
            if u == "END":
                break

            # 已知可安全跳过的调度辅助关键字
            if u == "NEXTSTEP":
                self._skip_to_slash()
                continue

            # 已知可安全忽略的 SUMMARY 输出请求
            if u in {"WMCTL", "BOKR", "BWSAT"}:
                self._skip_to_slash()
                continue

            if u == "PBVD":
                self._parse_pbvd(R)
                continue

                        # YAML 注册的关键字
            if u in kw_map:
                entry = kw_map[u]
                fmt = entry["format"]

                if fmt == "flag":
                    self._handle_flag(entry, R)
                elif fmt == "skip_slash":
                    self._skip_to_slash()
                elif fmt == "array":
                    self._handle_array(entry, R)
                elif fmt == "scalar":
                    self._handle_scalar(entry, R)
                elif fmt == "table":
                    self._handle_table(entry, lineno, R)
                elif fmt == "dimens":
                    self._handle_dimens(R)
                elif fmt == "custom":
                    handler = getattr(self, entry["handler"])
                    handler(R)
            else:
                # 未注册关键字：尝试自动消耗
                self._auto_consume(u, R)



        if self.unparsed_blocks:
            R["unparsed_blocks"] = self.unparsed_blocks
        R["_total_sim_time"] = self._current_time
        R["_time_checkpoints"] = list(self._time_checkpoints)
        return R


# ── 对外接口 ──────────────────────────────────────────────────────────────────

def parse_petrel(filepath, output_json=None, report_dir=PARSER_REPORTS_DIR):
    r = PetrelParser(filepath).parse()
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
        ("井数量", len(r.get("wells", []))),
        ("PVTO 行数", len(r.get("fluid", {}).get("pvto_table", {}).get("rows", []))),
        ("PVDG 行数", len(r.get("fluid", {}).get("pvdg_table", {}).get("rows", []))),
        ("未知关键字数", len(unknown)),
        ("累计模拟天数", f"{r.get('_total_sim_time', 0.0):.2f}"),
    ]

    md_path, json_path = write_report_bundle(
        report_dir=report_dir,
        source_name=Path(filepath).name,
        report_type="parse_petrel",
        title="Petrel 解析报告",
        summary_items=summary,
        warnings=warnings,
        errors=[],
        details={
            "unknown_keywords": unknown,
            "start_date": r.get("meta", {}).get("start_date"),
            "unit_system": r.get("meta", {}).get("unit_system"),
        },
    )
    r["_parse_report"] = {"md": str(md_path), "json": str(json_path)}
    return r


if __name__ == "__main__":
    default_input = Path("inputs/petrel/SPE1_ODEHIMPES.DATA")
    fp = Path(sys.argv[1]) if len(sys.argv) > 1 else default_input

    out_dir = JSON_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{fp.stem}_parsed.json"

    d = parse_petrel(fp, str(out))
    g = d["grid"]
    print(f"Grid:      {g.get('ni')} x {g.get('nj')} x {g.get('nk')}  type={g.get('grid_type')}")
    print(f"Porosity:  {d['reservoir'].get('porosity', {}).get('type', 'not found')}")
    print(f"PVTO rows: {len(d['fluid'].get('pvto_table', {}).get('rows', []))}")
    print(f"PVDG rows: {len(d['fluid'].get('pvdg_table', {}).get('rows', []))}")
    print(f"SWFN rows: {len(d['rockfluid'].get('swfn_table', {}).get('rows', []))}")
    print(f"Wells:     {len(d['wells'])}")
    print(f"Start:     {d['meta'].get('start_date')}")
    print(f"Sim days:  {d.get('_total_sim_time', 0):.1f}")
    print(f"Unknown:   {list(d.get('unknown_keywords', {}).keys())}")
    print(f"JSON:      {out}")
