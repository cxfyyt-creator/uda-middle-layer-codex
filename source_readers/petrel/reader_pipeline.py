# =============================================================================
# source_readers/petrel_reader.py  —  Petrel Eclipse .DATA → 通用 JSON dict
# 架构：规则驱动 + 自定义处理器
#   - 简单关键字（array/scalar/table/flag）全部由通用 handler 处理
#   - 复杂关键字（PVTO/WELSPECS/EQUIL 等）由专属方法处理
#   - 新增简单关键字：只需在 registries/keyword_registry.yaml 中添加一行
# =============================================================================

import re
import copy
import sys
import logging
from datetime import datetime
from pathlib import Path

# 把 infra 目录加入搜索路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from infra.pvt_metadata import apply_pvt_role
from infra.registry_loader import get_loader
from infra.value_semantics import apply_value_semantics
from source_readers.petrel import token_stream as petrel_token_stream
from source_readers.petrel import value_builders as petrel_value_builders
from source_readers.petrel.keyword_handlers import edit_keywords as petrel_edit_keywords
from source_readers.petrel.keyword_handlers import pvt_solution as petrel_pvt_solution
from source_readers.petrel.keyword_handlers import run_control as petrel_run_control
from source_readers.petrel.keyword_handlers import wells_schedule as petrel_wells_schedule

# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _strip_comment(line):
    return petrel_token_stream.strip_comment(line)
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
    return petrel_value_builders.to_float(s)
    return float(str(s).replace("d", "e").replace("D", "E"))

def _expand_repeat(tok):
    return petrel_value_builders.expand_repeat(tok)
    m = re.match(r'^(\d+)\*([0-9.eEdD+\-]+)$', str(tok))
    if m:
        return [_to_float(m.group(2))] * int(m.group(1))
    return None

def _scalar(v, unit, src, modifier=None, distribution=None, axis=None, format_hint=None):
    return petrel_value_builders.scalar(
        v,
        unit,
        src,
        modifier=modifier,
        distribution=distribution,
        axis=axis,
        format_hint=format_hint,
    )
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
    return petrel_value_builders.array(
        vs,
        unit,
        src,
        modifier=modifier,
        distribution=distribution,
        axis=axis,
        format_hint=format_hint,
    )
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
    return petrel_value_builders.table(cols, rows, src)
    return {"type": "table", "columns": cols, "rows": rows,
            "confidence": 0.99, "source": src}

_MONTH_MAP = petrel_token_stream.MONTH_MAP

# 行内噪声词（SPE文件中无注释符的说明文字）
_NOISE_WORDS = petrel_token_stream.NOISE_WORDS

# ── 词元化 ────────────────────────────────────────────────────────────────────

def _tokenize(filepath):
    return petrel_token_stream.tokenize_petrel_file(filepath)
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

    def _record_unparsed(self, lineno, text, reason="", *, keyword=None, raw_content=None):
        msg = f"未解析内容 line={lineno}: {text}"
        if reason:
            msg += f" | reason={reason}"
        self.logger.warning(msg)
        entry = {
            "line": lineno,
            "text": str(text),
            "reason": reason,
            "source": "petrel",
        }
        if keyword:
            entry["keyword"] = str(keyword)
        if raw_content is not None:
            entry["raw_content"] = str(raw_content)
        self.unparsed_blocks.append(entry)

    def _record_unknown_keyword(self, R, keyword, lineno, raw_content, *, reason="unknown keyword", values=None):
        entry = {
            "line": lineno,
            "raw_content": str(raw_content),
            "reason": reason,
            "source": "petrel",
        }
        if values is not None:
            entry["values"] = values
        R.setdefault("unknown_keywords", {}).setdefault(str(keyword), []).append(entry)

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


    def _build_array_keyword_reverse(self, include_unit=False):
        kw_map_full = self._rl.petrel_kw_map()
        reverse = {}
        for kw, entry in kw_map_full.items():
            if entry.get("format") == "array" and "json" in entry:
                js = entry["json"]
                if include_unit:
                    reverse[kw.upper()] = (js["section"], js["key"], entry.get("unit", ""))
                else:
                    reverse[kw.upper()] = (js["section"], js["key"])
        if include_unit:
            reverse.update({
                "PERMR": ("reservoir", "perm_i", "md"),
                "DTHETA": ("grid", "dtheta", "deg"),
                "TOPS": ("grid", "tops_ref", "ft"),
            })
        else:
            reverse["PERMR"] = ("reservoir", "perm_i")
        return reverse

    def _read_edit_record(self):
        """
        Read one EQUALS/COPY/MULTIPLY-style record.
        A single slash-only record terminates the whole block.
        Unlike _read_until_slash, this allows bare array names like PORO/PERMX.
        """
        row = []
        while self._peek():
            ln, tok = self._peek()
            self.pos += 1
            if tok == "/":
                while self._peek():
                    ln2, _ = self._peek()
                    if ln2 != ln:
                        break
                    self.pos += 1
                return row, (len(row) == 0)
            row.append(tok)
        return row, bool(not row)

    def _row_numbers(self, tokens):
        nums = []
        for tok in tokens:
            exp = _expand_repeat(tok)
            if exp is not None:
                nums.extend(exp)
                continue
            try:
                nums.append(_to_float(tok))
            except (ValueError, TypeError):
                pass
        return nums

    def _normalize_edit_keyword(self, tok):
        return str(tok).strip("'").strip().upper()

    def _extract_box(self, numeric_tokens, fallback_box=None):
        if len(numeric_tokens) >= 6:
            candidate = numeric_tokens[:6]
            if all(float(v) == int(v) for v in candidate):
                return [int(v) for v in candidate]
        return fallback_box

    def _box_is_full_layer(self, box, ni, nj):
        if not box or len(box) != 6:
            return False
        i1, i2, j1, j2, _, _ = box
        return i1 == 1 and i2 == ni and j1 == 1 and j2 == nj

    def _expand_obj_to_k_values(self, obj, nk):
        nk = max(int(nk or 1), 1)
        if obj is None:
            return [None] * nk
        if obj.get("type") == "scalar":
            return [obj.get("value")] * nk
        if obj.get("type") == "array":
            vals = list(obj.get("values") or [])
            if len(vals) == nk:
                return vals[:]
            if len(vals) == 1:
                return vals * nk
            if len(vals) < nk:
                return vals + [None] * (nk - len(vals))
            return vals[:nk]
        return [None] * nk

    def _collapse_k_values(self, values, unit, src, *, distribution=None, axis=None, format_hint=None):
        cleaned = [0.0 if v is None else v for v in values]
        if len(cleaned) == 1 or len(set(cleaned)) == 1:
            return _scalar(
                cleaned[0],
                unit,
                src,
                distribution=distribution or "constant",
                axis=axis,
                format_hint=format_hint,
            )
        return _array(
            cleaned,
            unit,
            src,
            distribution=distribution or "by_layer",
            axis=axis or "k",
            format_hint=format_hint,
        )

    def _parse_equals(self, R):
        return petrel_edit_keywords.parse_equals(self, R)

    def _parse_copy(self, R):
        return petrel_edit_keywords.parse_copy(self, R)

    def _parse_multiply(self, R):
        return petrel_edit_keywords.parse_multiply(self, R)

    def _parse_pvtw(self, R):
        return petrel_pvt_solution.parse_pvtw(self, R)

    def _parse_rock(self, R):
        return petrel_pvt_solution.parse_rock(self, R)

    def _parse_miscible(self, R):
        return petrel_pvt_solution.parse_miscible(self, R)

    def _parse_density(self, R):
        return petrel_pvt_solution.parse_density(self, R)

    def _parse_pvto(self, R):
        return petrel_pvt_solution.parse_pvto(self, R)

    def _parse_pvdg(self, R):
        return petrel_pvt_solution.parse_pvdg(self, R)

    def _parse_equil(self, R):
        return petrel_pvt_solution.parse_equil(self, R)

    def _parse_rsvd(self, R):
        return petrel_pvt_solution.parse_rsvd(self, R)

    def _parse_pbvd(self, R):
        return petrel_pvt_solution.parse_pbvd(self, R)

    def _parse_start(self, R):
        return petrel_run_control.parse_start(self, R)

    def _parse_load(self, R):
        return petrel_run_control.parse_load(self, R)

    def _parse_restart(self, R):
        return petrel_run_control.parse_restart(self, R)

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
        return petrel_wells_schedule.parse_welspecs(self, R)

    def _parse_compdat(self, R):
        return petrel_wells_schedule.parse_compdat(self, R)

    def _parse_wconprod(self, R):
        return petrel_wells_schedule.parse_wconprod(self, R)

    def _parse_wconinje(self, R):
        return petrel_wells_schedule.parse_wconinje(self, R)

    def _parse_weltarg(self, R):
        return petrel_wells_schedule.parse_weltarg(self, R)

    def _parse_tstep(self, R):
        return petrel_wells_schedule.parse_tstep(self, R)

    def _parse_dates(self, R):
        return petrel_wells_schedule.parse_dates(self, R)

    def _auto_consume(self, keyword, R):
        """遇到未知关键字，自动推断格式并消耗 token，存入 unknown_keywords"""
        first = self._peek()
        if not first:
            return
        lineno = self._last_lineno()
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
            raw_content = f"{keyword} {' '.join(str(v) for v in vals)}".strip()
            self._record_unknown_keyword(R, keyword, lineno, raw_content, values=vals)
            self._record_unparsed(lineno, keyword, reason="unknown keyword", keyword=keyword, raw_content=raw_content)
        else:
            # 可能是纯标志或下一个关键字，不消耗
            self._record_unknown_keyword(R, keyword, lineno, keyword, reason="unknown keyword without payload", values=[])
            self._record_unparsed(
                lineno,
                keyword,
                reason="unknown keyword without payload",
                keyword=keyword,
                raw_content=keyword,
            )

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

