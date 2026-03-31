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
from utils.cmg_case_dependencies import build_cmg_case_manifest, scan_cmg_case_dependencies
from utils.project_paths import JSON_OUTPUT_DIR, PARSER_REPORTS_DIR
from utils.pvt_metadata import apply_pvt_role
from utils.value_semantics import apply_value_semantics

_TOKEN_RE = re.compile(r"'[^']*'|\"[^\"]*\"|\S+")
_TITLE_KWS = {"*TITLE1", "*TITLE2", "*TITLE3"}
_LINE_IGNORE_KWS = {
    "*RESULTS", "*WPRN", "*OUTPRN", "*WSRF", "*OUTSRF",
    "*MONITOR", "*GROUP", "*AIMWELL", "*AIMGROUP", "*OUTDIARY",
}
_STARLESS_TOP_LEVEL_KWS = {"FILENAMES"}

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
    return apply_value_semantics(
        d,
        value_type="scalar",
        modifier=modifier,
        software="cmg_imex",
    )

def _array(vs, unit, src, modifier=None):
    d = {"type": "array", "values": vs, "unit": unit,
         "grid_order": "IJK", "confidence": 0.99, "source": src}
    if modifier:
        d["modifier"] = modifier
    return apply_value_semantics(
        d,
        value_type="array",
        modifier=modifier,
        software="cmg_imex",
    )

def _table(cols, rows, src):
    return {"type": "table", "columns": cols, "rows": rows,
            "confidence": 0.99, "source": src}


# ── 主解析器 ──────────────────────────────────────────────────────────────────

class CMGParser:

    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self.tokens = []
        self.pos = 0
        self.raw_lines = []
        self._rl = get_loader()
        self._cmg_kw_keys = set(self._rl.cmg_kw_map().keys())
        self.logger = logging.getLogger(__name__)
        self.unparsed_blocks = []
        self.active_well_indices = []
        self.last_geometry = None
        self.default_geometry = None
        self._case_dependencies = {}

    # ── Token 管理 ────────────────────────────────────────────────────────────

    def _load_tokens(self):
        with open(self.filepath, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        self.raw_lines = [line.rstrip("\r\n") for line in lines]

        skip_next_text_line = False
        for lineno, raw in enumerate(lines, 1):
            line = _strip_comments(raw)
            if not line:
                continue

            toks = _TOKEN_RE.findall(line)
            if not toks:
                continue

            first = toks[0].upper()
            normalized_first = first if first.startswith("*") else f"*{first}" if first.isalpha() else first

            if skip_next_text_line and not first.startswith("*"):
                skip_next_text_line = False
                continue

            if normalized_first in _TITLE_KWS:
                skip_next_text_line = len(toks) == 1
                continue

            if normalized_first in _LINE_IGNORE_KWS or first == "RESULTS":
                continue

            for tok in toks:
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

    def _skip_same_line_tokens(self, lineno):
        while self._peek() and self._peek()[0] == lineno:
            self.pos += 1

    def _read_same_line_tokens(self, lineno):
        toks = []
        while self._peek() and self._peek()[0] == lineno:
            toks.append(self._next()[1])
        return toks

    def _is_line_first_token(self, off=0):
        i = self.pos + off
        if i >= len(self.tokens):
            return False
        if i == 0:
            return True
        return self.tokens[i][0] != self.tokens[i - 1][0]

    def _normalize_top_level_keyword(self, tok):
        tok_u = str(tok or "").upper()
        if not tok_u:
            return tok_u
        if tok_u in {"RUN", "RESULTS", "SIMULATOR", "IMEX"}:
            return tok_u
        if tok_u.startswith("*"):
            return tok_u
        alias = f"*{tok_u}"
        if alias in self._cmg_kw_keys:
            return alias
        return tok_u

    def _normalize_inline_token(self, tok):
        tok_u = str(tok or "").upper()
        return tok_u.lstrip("*")

    def _current_keyword_token(self):
        if self.pos <= 0:
            return ""
        return str(self.tokens[self.pos - 1][1])

    def _resolve_external_source_file(self, dependency_kind):
        dependency_kind = str(dependency_kind or "").upper()
        meta = getattr(self, "_case_dependencies", {}) or {}
        for item in meta.get("runtime_inputs", []) or []:
            item_type = str(item.get("type", "")).upper().lstrip("*")
            if item_type == dependency_kind:
                return item.get("path")
        return None

    def _peek_external_ref(self, unit, src):
        t = self._peek()
        if not t:
            return None
        token = self._normalize_inline_token(t[1])
        dependency_kind = None
        if token == "SIP_DATA":
            dependency_kind = "SIPDATA-IN"
        elif token == "BINARY_DATA":
            dependency_kind = "BINDATA-IN"
        if not dependency_kind:
            return None

        keyword = self._normalize_inline_token(self._current_keyword_token())
        self.pos += 1
        source_file = self._resolve_external_source_file(dependency_kind)
        return apply_value_semantics(
            {
                "type": "ref",
                "source_file": source_file or "",
                "dataset": keyword,
                "format": token,
                "unit": unit,
                "confidence": 0.99,
                "source": src,
                "required": True,
                "source_format_hint": {
                    "software": "cmg_imex",
                    "keyword": token,
                    "dependency_kind": dependency_kind,
                },
            },
            value_type="ref",
            software="cmg_imex",
        )

    def _is_top_level_kw_token(self, tok, *, off=0):
        if not tok:
            return False
        tok_u = self._normalize_top_level_keyword(tok)
        if tok_u in {"RUN", "RESULTS", "SIMULATOR", "IMEX"}:
            return self._is_line_first_token(off=off)
        if _is_kw(tok) and self._is_line_first_token(off=off):
            return True
        if self._is_line_first_token(off=off):
            raw_u = str(tok).upper()
            if tok_u in self._cmg_kw_keys or raw_u in _STARLESS_TOP_LEVEL_KWS:
                return True
        return False

    def _peek_next_top_level_kw(self):
        off = 0
        while self._peek(off):
            _, tok = self._peek(off)
            if self._is_top_level_kw_token(tok, off=off):
                return self._peek(off)
            off += 1
        return None

    def _consume_unknown_block(self, first_lineno, first_tok):
        parts = [str(first_tok)]

        while self._peek() and self._peek()[0] == first_lineno:
            parts.append(str(self._next()[1]))

        while self._peek():
            lineno, tok = self._peek()
            if self._is_top_level_kw_token(tok):
                break
            parts.append(str(self._next()[1]))

        next_kw = self._peek_next_top_level_kw()
        reason = "unknown top-level keyword"
        if next_kw:
            reason += f"; stopped before {next_kw[1]}"
        self._record_unparsed(first_lineno, " ".join(parts), reason=reason)
        return parts

    def _consume_unknown_inline(self, lineno, first_tok):
        parts = [str(first_tok)]
        while self._peek() and self._peek()[0] == lineno:
            parts.append(str(self._next()[1]))
        self._record_unparsed(lineno, " ".join(parts), reason="unknown inline token")
        return parts

    def _expand_int_token(self, tok):
        text = str(tok).strip()
        if not text:
            return None
        m = re.match(r'^(-?\d+):(-?\d+)$', text)
        if m:
            start = int(m.group(1))
            end = int(m.group(2))
            step = 1 if end >= start else -1
            return list(range(start, end + step, step))
        if re.match(r'^-?\d+$', text):
            return [int(text)]
        return None

    def _collect_numeric_tokens_until_kw(self):
        toks = []
        while self._peek() and not _is_kw(self._peek()[1]):
            toks.append(self._next()[1])
        return toks

    def _expand_numeric_tokens(self, toks):
        vals = []
        for tok in toks:
            expanded = _expand_repeat(tok)
            if expanded is not None:
                vals.extend(expanded)
                continue
            try:
                vals.append(_to_float(tok))
            except ValueError:
                pass
        return vals

    def _find_well(self, R, well_index):
        for well in R['wells']:
            if well.get('well_index') == well_index:
                return well
        return None

    def _ensure_well(self, R, well_index, well_name=None):
        well = self._find_well(R, well_index)
        if well is None:
            well = {
                'well_name': well_name or f'W{well_index}',
                'well_index': well_index,
                'well_type': None,
                'perforations': [],
                'well_radius': None,
                'bhp_max': None, 'bhp_min': None,
                'rate_max': None,
                'inj_fluid': None,
                'alter_schedule': [],
                'geofac': None, 'wfrac': None, 'skin': None,
            }
            if self.default_geometry:
                well['well_radius'] = self.default_geometry.get('well_radius')
                well['geofac'] = self.default_geometry.get('geofac')
                well['wfrac'] = self.default_geometry.get('wfrac')
                well['skin'] = self.default_geometry.get('skin')
            R['wells'].append(well)
        elif well_name and (not well.get('well_name') or str(well.get('well_name', '')).startswith('W')):
            well['well_name'] = well_name
        return well

    def _resolve_well_indices(self, R, selector=None):
        if selector:
            resolved = []
            for idx in selector:
                if idx not in resolved:
                    resolved.append(idx)
            return resolved
        if self.active_well_indices:
            return list(self.active_well_indices)
        if R['wells']:
            return [R['wells'][-1]['well_index']]
        return []

    def _wells_for_selector(self, R, selector=None):
        return [self._ensure_well(R, idx) for idx in self._resolve_well_indices(R, selector)]

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
        """?????token??? *CON/*KVAR/*IVAR/*JVAR/*ALL/*IJK ???"""
        t = self._peek()
        if not t:
            return None
        _, tok = t
        token = self._normalize_inline_token(tok)
        if token in ("CON", "KVAR", "IVAR", "JVAR", "ALL", "IJK"):
            return f"*{token}"
        return None

    def _infer_equalsi_source_key(self, section, key):
        key = str(key or "")
        if key.endswith("_j") or key.endswith("_k"):
            return key[:-1] + "i"
        return None

    def _peek_equalsi_relation(self, section, key, unit, src):
        t = self._peek()
        if not t or self._normalize_inline_token(t[1]) != "EQUALSI":
            return None

        source_key = self._infer_equalsi_source_key(section, key)
        if not source_key:
            return None

        self.pos += 1
        same_line_tokens = self._read_same_line_tokens(self._last_lineno())
        scale = 1.0
        for tok in same_line_tokens:
            if str(tok).strip() == "*":
                continue
            try:
                scale = _to_float(tok)
                break
            except ValueError:
                continue

        return {
            "type": "reference",
            "relation": "EQUALSI",
            "source_section": section,
            "source_key": source_key,
            "scale": float(scale),
            "unit": unit,
            "confidence": 0.99,
            "source": src,
            "source_format_hint": {
                "software": "cmg_imex",
                "keyword": "*EQUALSI",
            },
        }

    # ?? ?? handler?array??????????????????????????????????????????????

    def _handle_array(self, entry, R):
        json_spec = entry["json"]
        unit = entry.get("unit", "")
        lineno = self._last_lineno()
        src = f"{json_spec['section']} {json_spec['key']} 第{lineno}行"
        section = json_spec["section"]
        key = json_spec["key"]

        relation = self._peek_equalsi_relation(section, key, unit, src)
        if relation is not None:
            R[section][key] = relation
            return

        external_ref = self._peek_external_ref(unit, src)
        if external_ref is not None:
            R[section][key] = external_ref
            return

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
        if self._normalize_inline_token(tok) == "CON":
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
            R["fluid"]["pvt_table"] = apply_pvt_role(
                _table(cols, rows, "fluid *PVT"),
                pvt_form="cmg_pvt_table",
                representation_role="native_source",
                preferred_backend="cmg",
            )

    def _handle_table(self, entry, R):
        """通用n列浮点表，直到下一个*关键字。"""
        json_spec = entry["json"]
        cols = entry.get("columns", [])
        ncols = int(entry.get("ncols", len(cols) or 1))
        src = f"{json_spec['section']} {json_spec['key']}"

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
            R[json_spec["section"]][json_spec["key"]] = _table(cols, rows, src)

    # ── 通用 handler：rpt_table（相渗表）────────────────────────────────────

    def _handle_rpt_table(self, entry, R):
        json_spec = entry["json"]
        columns = entry.get("columns", [])
        ncols = len(columns)
        src = f"rockfluid {json_spec['key']}"

        rows = []
        while self._peek():
            lineno, tok = self._peek()
            if self._is_top_level_kw_token(tok):
                break

            row_tokens = self._read_same_line_tokens(lineno)
            nums = []
            for item in row_tokens:
                expanded = _expand_repeat(item)
                if expanded is not None:
                    nums.extend(expanded)
                    continue
                try:
                    nums.append(_to_float(item))
                except ValueError:
                    pass

            if len(nums) == ncols - 1 and ncols >= 4:
                nums.append(0.0)

            if len(nums) >= ncols:
                rows.append(nums[:ncols])
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

        lineno = self._last_lineno()
        tokens = self._read_same_line_tokens(lineno)
        selector = []
        name = None
        vert = None
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            expanded = self._expand_int_token(tok)
            if expanded and not selector:
                selector = expanded
                i += 1
                continue
            if tok.startswith("'") and tok.endswith("'") and name is None:
                name = tok.strip("'")
                i += 1
                continue
            if tok.upper() == '*VERT' and i + 2 < len(tokens):
                try:
                    vert = (int(float(tokens[i + 1])), int(float(tokens[i + 2])))
                    i += 3
                    continue
                except ValueError:
                    pass
            i += 1

        well_index = selector[0] if selector else len(R['wells']) + 1
        well = self._ensure_well(R, well_index, name)
        if name:
            well['well_name'] = name
        if vert:
            well['well_i'], well['well_j'] = vert
        self.active_well_indices = [well_index]

    def _parse_producer(self, R, in_run_section):
        if not in_run_section or not R['wells']:
            return

        lineno = self._last_lineno()
        tokens = self._read_same_line_tokens(lineno)
        selector = []
        for tok in tokens:
            expanded = self._expand_int_token(tok)
            if expanded:
                selector = expanded
                break
        wells = self._wells_for_selector(R, selector)
        for well in wells:
            well['well_type'] = 'PRODUCER'
        self.active_well_indices = [w['well_index'] for w in wells]

    def _parse_injector(self, R, in_run_section):
        if not in_run_section or not R['wells']:
            return

        lineno = self._last_lineno()
        tokens = self._read_same_line_tokens(lineno)
        selector = []
        for tok in tokens:
            expanded = self._expand_int_token(tok)
            if expanded:
                selector = expanded
                break
        wells = self._wells_for_selector(R, selector)
        for well in wells:
            well['well_type'] = 'INJECTOR'
        self.active_well_indices = [w['well_index'] for w in wells]

    def _parse_incomp(self, R, in_run_section):
        if not in_run_section or not R['wells']:
            return

        lineno = self._last_lineno()
        tokens = self._read_same_line_tokens(lineno)
        fluid_kw = next((tok for tok in tokens if _is_kw(tok)), None)
        if fluid_kw:
            for well in self._wells_for_selector(R):
                well['inj_fluid'] = fluid_kw.lstrip('*').upper()

    def _parse_operate(self, R, in_run_section):
        if not in_run_section or not R['wells']:
            return

        lineno = self._last_lineno()
        parts = self._read_same_line_tokens(lineno)

        mode = None
        target = None
        value = None
        for p in parts:
            pu = p.upper()
            if pu in ('*MAX', '*MIN'):
                mode = pu.lstrip('*')
            elif pu in ('*BHP', '*STO', '*STG', '*STW', '*RESV'):
                target = pu.lstrip('*')
            else:
                try:
                    value = _to_float(p)
                except ValueError:
                    pass
        if target and value is not None:
            for w in self._wells_for_selector(R):
                if target == 'BHP':
                    if mode == 'MAX':
                        w['bhp_max'] = value
                    else:
                        w['bhp_min'] = value
                elif target in ('STO', 'STG', 'STW'):
                    if mode == 'MAX':
                        w['rate_max'] = value

    def _parse_perf(self, R, in_run_section, perf_kw='*PERF'):
        if not in_run_section or not R['wells']:
            return

        lineno = self._last_lineno()
        header_tokens = self._read_same_line_tokens(lineno)
        selector = []
        use_geo = False
        for tok in header_tokens:
            if tok.upper() == '*GEO':
                use_geo = True
                continue
            expanded = self._expand_int_token(tok)
            if expanded:
                selector = expanded
                break

        wells = self._wells_for_selector(R, selector)
        if use_geo and self.last_geometry:
            for w in wells:
                w['well_radius'] = self.last_geometry.get('well_radius')
                w['geofac'] = self.last_geometry.get('geofac')
                w['wfrac'] = self.last_geometry.get('wfrac')
                w['skin'] = self.last_geometry.get('skin')

        while self._peek() and not _is_kw(self._peek()[1]):
            row_lineno = self._peek()[0]
            row_tokens = self._read_same_line_tokens(row_lineno)
            if not row_tokens:
                continue

            if perf_kw == '*PERFV':
                k_vals = self._expand_int_token(row_tokens[0]) or []
                try:
                    wi = _to_float(row_tokens[1]) if len(row_tokens) > 1 else -1.0
                except ValueError:
                    wi = -1.0
                if wi <= 0:
                    wi = -1.0
                for w in wells:
                    wi_i = w.get('well_i')
                    wi_j = w.get('well_j')
                    if wi_i is None or wi_j is None:
                        continue
                    for k in k_vals:
                        w['perforations'].append({
                            'i': int(wi_i), 'j': int(wi_j), 'k': int(k),
                            'wi': wi,
                            'perf_type': perf_kw.lstrip('*'),
                        })
                continue

            if len(row_tokens) < 3:
                break
            i_vals = self._expand_int_token(row_tokens[0]) or []
            j_vals = self._expand_int_token(row_tokens[1]) or []
            k_vals = self._expand_int_token(row_tokens[2]) or []
            try:
                wi = _to_float(row_tokens[3]) if len(row_tokens) > 3 else -1.0
            except ValueError:
                wi = -1.0
            if wi <= 0:
                wi = -1.0
            for w in wells:
                for ii in i_vals:
                    for jj in j_vals:
                        for kk in k_vals:
                            w['perforations'].append({
                                'i': int(ii), 'j': int(jj), 'k': int(kk),
                                'wi': wi,
                                'perf_type': perf_kw.lstrip('*'),
                            })

    def _parse_perfv(self, R, in_run_section):
        self._parse_perf(R, in_run_section, '*PERFV')

    def _parse_geometry(self, R, in_run_section):
        if not in_run_section:
            return

        lineno = self._last_lineno()
        tokens = self._read_same_line_tokens(lineno)
        nums = []
        for tok in tokens:
            if _is_kw(tok):
                continue
            try:
                nums.append(_to_float(tok))
            except ValueError:
                pass
        if nums:
            geom = {
                'well_radius': nums[0],
                'geofac': nums[1] if len(nums) > 1 else None,
                'wfrac': nums[2] if len(nums) > 2 else None,
                'skin': nums[3] if len(nums) > 3 else None,
            }
            self.last_geometry = geom
            self.default_geometry = geom
            for w in self._wells_for_selector(R):
                w['well_radius'] = geom['well_radius']
                if geom['geofac'] is not None:
                    w['geofac'] = geom['geofac']
                if geom['wfrac'] is not None:
                    w['wfrac'] = geom['wfrac']
                if geom['skin'] is not None:
                    w['skin'] = geom['skin']

    def _parse_alter(self, R, in_run_section):
        if not in_run_section or not R['wells']:
            return

        lineno = self._last_lineno()
        raw_tokens = self._read_same_line_tokens(lineno)
        raw_tokens.extend(self._collect_numeric_tokens_until_kw())

        selector = []
        if raw_tokens:
            maybe_selector = self._expand_int_token(raw_tokens[0])
            if maybe_selector and len(raw_tokens) > 1:
                selector = maybe_selector
                raw_tokens = raw_tokens[1:]

        values = self._expand_numeric_tokens(raw_tokens)
        well_indices = self._resolve_well_indices(R, selector)
        if not well_indices or not values:
            return

        if len(values) == 1:
            values = values * len(well_indices)
        elif len(values) < len(well_indices):
            values.extend([values[-1]] * (len(well_indices) - len(values)))

        for idx, new_rate in zip(well_indices, values):
            well = self._find_well(R, idx)
            if well is None:
                continue
            well['alter_schedule'].append({
                'time': R.get('_current_time', 0.0),
                'rate': new_rate,
            })

    def _parse_well_status_action(self, R, in_run_section, action):
        if not in_run_section or not R['wells']:
            return

        lineno = self._last_lineno()
        tokens = self._read_same_line_tokens(lineno)
        selector = []
        for tok in tokens:
            expanded = self._expand_int_token(tok)
            if expanded:
                selector = expanded
                break

        for well in self._wells_for_selector(R, selector):
            well.setdefault('status_schedule', []).append({
                'time': R.get('_current_time', 0.0),
                'action': action,
            })

    def _parse_open(self, R, in_run_section):
        self._parse_well_status_action(R, in_run_section, 'OPEN')

    def _parse_shutin(self, R, in_run_section):
        self._parse_well_status_action(R, in_run_section, 'SHUTIN')

    def _parse_control_directive(self, R, in_run_section=None):
        lineno = self._last_lineno()
        keyword = self.tokens[self.pos - 1][1].upper() if self.pos > 0 else ""
        tokens = self._read_same_line_tokens(lineno)
        bucket = R.setdefault("numerical", {}).setdefault("_cmg_control_directives", [])
        bucket.append({
            "keyword": keyword,
            "line": lineno,
            "tokens": [str(t) for t in tokens],
            "time": R.get("_current_time", 0.0),
        })

    def _parse_solver_directive(self, R, in_run_section=None):
        lineno = self._last_lineno()
        keyword = self.tokens[self.pos - 1][1].upper() if self.pos > 0 else ""
        tokens = self._read_same_line_tokens(lineno)
        bucket = R.setdefault("numerical", {}).setdefault("_cmg_solver_directives", [])
        bucket.append({
            "keyword": keyword,
            "line": lineno,
            "tokens": [str(t) for t in tokens],
            "time": R.get("_current_time", 0.0),
        })

    def _parse_equalsi(self, R):
        lineno = self._last_lineno()
        tokens = self._read_same_line_tokens(lineno)
        bucket = R.setdefault("reservoir", {}).setdefault("_cmg_equalities", [])
        bucket.append({
            "keyword": "*EQUALSI",
            "line": lineno,
            "tokens": [str(t) for t in tokens],
        })

    def _parse_grid_directive(self, R):
        lineno = self._last_lineno()
        keyword = self.tokens[self.pos - 1][1].upper() if self.pos > 0 else ""
        tokens = self._read_same_line_tokens(lineno)
        bucket = R.setdefault("grid", {}).setdefault("_cmg_grid_directives", [])
        bucket.append({
            "keyword": keyword,
            "line": lineno,
            "tokens": [str(t) for t in tokens],
        })

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
        """*DENSITY *OIL/*GAS/*WATER/*SOLVENT value"""
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
        key_map = {"OIL": "oil_density", "GAS": "gas_density", "WATER": "water_density", "SOLVENT": "solvent_density"}
        unit_map = {"OIL": "lb/ft3", "GAS": "lb/ft3", "WATER": "lb/ft3", "SOLVENT": "lb/ft3"}
        key = key_map.get(dtype_u)
        if key:
            R["fluid"][key] = _scalar(val, unit_map.get(dtype_u, "lb/ft3"), src)

    def _parse_model(self, R):
        """*MODEL *BLACKOIL/*MISNCG/..."""
        t = self._peek()
        if t and _is_kw(t[1]):
            _, model_kw = self._next()
            model = model_kw.lstrip("*").upper()
            R["fluid"]["model"] = model
            if model.startswith("MIS"):
                R["meta"]["model_type"] = "miscible"

    def _parse_gravity(self, R):
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
        R.setdefault("fluid", {})[f"{dtype_u.lower()}_gravity"] = _scalar(val, "", f"fluid *GRAVITY *{dtype_u}")

    def _parse_zg(self, R):
        rows = []
        while self._peek():
            lineno, tok = self._peek()
            if self._is_top_level_kw_token(tok):
                break
            row_tokens = self._read_same_line_tokens(lineno)
            nums = []
            for item in row_tokens:
                expanded = _expand_repeat(item)
                if expanded is not None:
                    nums.extend(expanded)
                    continue
                try:
                    nums.append(_to_float(item))
                except ValueError:
                    pass
            if len(nums) >= 6:
                rows.append(nums[:6])
        if rows:
            R.setdefault("fluid", {})["zg_table"] = _table(
                ["p", "c1", "c2", "c3", "c4", "c5"],
                rows,
                "fluid *ZG",
            )

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

        self._case_dependencies = (
            scan_cmg_case_dependencies(self.raw_lines, self.filepath.parent)
            if self.raw_lines else {}
        )

        in_run_section = False
        unknown_keys = []

        while self._peek():
            lineno, tok = self._next()
            u = tok.upper()
            u_dispatch = self._normalize_top_level_keyword(tok) if self._is_line_first_token(off=-1) else u

            if u_dispatch in {'*RUN', 'RUN'}:
                in_run_section = True
                continue

            if u_dispatch in ignore_set:
                self._skip_same_line_tokens(lineno)
                continue

            if u_dispatch in _LINE_IGNORE_KWS or u_dispatch in {'RESULTS', 'SIMULATOR', 'IMEX', '*WELLNN', '*WELLN'}:
                self._skip_same_line_tokens(lineno)
                continue

            if u_dispatch in kw_map:
                entry = kw_map[u_dispatch]
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
                elif fmt == "table":
                    self._handle_table(entry, R)
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
                if self._is_top_level_kw_token(tok, off=-1):
                    self._consume_unknown_block(lineno, tok)
                else:
                    self._consume_unknown_inline(lineno, tok)

                if (u_dispatch.startswith("*") or _is_kw(tok)) and u_dispatch not in unknown_keys:
                    unknown_keys.append(u_dispatch)

        if unknown_keys:
            R["unknown_keywords"] = {k: [] for k in unknown_keys}

        if self.unparsed_blocks:
            R["unparsed_blocks"] = self.unparsed_blocks

        if self.raw_lines:
            R["meta"]["_cmg_roundtrip_mode"] = "source_faithful"
            R["meta"]["_cmg_raw_deck_lines"] = list(self.raw_lines)
            R["meta"]["_cmg_source_dir"] = str(self.filepath.parent)
            self._case_dependencies = scan_cmg_case_dependencies(
                self.raw_lines,
                self.filepath.parent,
            )
            R["meta"]["_cmg_case_dependencies"] = self._case_dependencies
            R["case_manifest"] = build_cmg_case_manifest(self.filepath, self._case_dependencies)

        R.pop("_current_time", None)
        return R


# ── 对外接口 ──────────────────────────────────────────────────────────────────

def parse_cmg(filepath, output_json=None, report_dir=PARSER_REPORTS_DIR):
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
        ("运行依赖文件", len((r.get("meta", {}).get("_cmg_case_dependencies", {}) or {}).get("runtime_inputs", []))),
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
            "case_dependencies": r.get("meta", {}).get("_cmg_case_dependencies", {}),
        },
    )
    r["_parse_report"] = {"md": str(md_path), "json": str(json_path)}
    return r


if __name__ == "__main__":
    default_input = Path("inputs/cmg/mxspe001.dat")
    f = Path(sys.argv[1]) if len(sys.argv) > 1 else default_input

    out_dir = JSON_OUTPUT_DIR
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
