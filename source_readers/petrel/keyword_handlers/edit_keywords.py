from __future__ import annotations

import copy

from source_readers.petrel.value_builders import scalar, to_float


def parse_equals(parser, R):
    reverse = parser._build_array_keyword_reverse(include_unit=True)
    ni = R["grid"].get("ni", 1)
    nj = R["grid"].get("nj", 1)
    nk = R["grid"].get("nk", 1)
    last_box = None

    while parser._peek():
        row, block_end = parser._read_edit_record()
        if block_end:
            break
        if not row:
            continue

        kw_raw = parser._normalize_edit_keyword(row[0])
        if kw_raw not in reverse:
            continue
        section, key, unit = reverse[kw_raw]

        nums = parser._row_numbers(row[1:])
        if not nums:
            continue

        value = nums[0]
        src = f"EQUALS {kw_raw}"
        box = parser._extract_box(nums[1:], fallback_box=last_box)
        if len(nums) >= 7 and box is not None:
            last_box = box

        if box and parser._box_is_full_layer(box, ni, nj):
            _, _, _, _, k1, k2 = box
            vals_list = parser._expand_obj_to_k_values(R[section].get(key), nk)
            for k in range(max(k1 - 1, 0), min(k2, nk)):
                vals_list[k] = value
            R[section][key] = parser._collapse_k_values(
                vals_list,
                unit,
                src,
                distribution="by_layer" if nk > 1 else "constant",
                axis="k",
                format_hint={"keyword": "EQUALS", "box_scope": "full_layer"},
            )
        elif box and len(box) == 6:
            if R[section].get(key) is None:
                R[section][key] = scalar(
                    value,
                    unit,
                    src + " BOX",
                    distribution="constant",
                    format_hint={"keyword": "EQUALS", "box_scope": "partial_box"},
                )
            else:
                parser._record_unparsed(parser._last_lineno(), f"EQUALS {kw_raw}", reason="partial box update not represented exactly")
        else:
            R[section][key] = scalar(
                value,
                unit,
                src,
                distribution="constant",
                format_hint={"keyword": "EQUALS", "box_scope": "global"},
            )


def parse_copy(parser, R):
    reverse = parser._build_array_keyword_reverse(include_unit=False)
    ni = R["grid"].get("ni", 1)
    nj = R["grid"].get("nj", 1)
    nk = R["grid"].get("nk", 1)

    while parser._peek():
        row, block_end = parser._read_edit_record()
        if block_end:
            break
        if not row or len(row) < 2:
            continue

        src_kw = parser._normalize_edit_keyword(row[0])
        dst_kw = parser._normalize_edit_keyword(row[1])
        if src_kw not in reverse or dst_kw not in reverse:
            continue

        s_sec, s_key = reverse[src_kw]
        d_sec, d_key = reverse[dst_kw]
        src_obj = R[s_sec].get(s_key)
        if not src_obj:
            continue

        box = parser._extract_box(parser._row_numbers(row[2:]))
        if box and parser._box_is_full_layer(box, ni, nj):
            _, _, _, _, k1, k2 = box
            src_vals = parser._expand_obj_to_k_values(src_obj, nk)
            dst_vals = parser._expand_obj_to_k_values(R[d_sec].get(d_key), nk)
            for k in range(max(k1 - 1, 0), min(k2, nk)):
                dst_vals[k] = src_vals[k]
            R[d_sec][d_key] = parser._collapse_k_values(
                dst_vals,
                src_obj.get("unit", ""),
                f"{src_obj.get('source', src_kw)} (COPY {src_kw}->{dst_kw})",
                distribution="by_layer" if nk > 1 else "constant",
                axis="k",
                format_hint={"keyword": "COPY", "box_scope": "full_layer"},
            )
        elif box and len(box) == 6:
            parser._record_unparsed(parser._last_lineno(), f"COPY {src_kw} {dst_kw}", reason="partial box copy not represented exactly")
        else:
            R[d_sec][d_key] = copy.deepcopy(src_obj)
            R[d_sec][d_key]["source"] = f"{src_obj.get('source', src_kw)} (COPY {src_kw}->{dst_kw})"


def parse_multiply(parser, R):
    reverse = parser._build_array_keyword_reverse(include_unit=False)
    ni = R["grid"].get("ni", 1)
    nj = R["grid"].get("nj", 1)
    nk = R["grid"].get("nk", 1)

    while parser._peek():
        row, block_end = parser._read_edit_record()
        if block_end:
            break
        if not row or len(row) < 2:
            continue

        kw_raw = parser._normalize_edit_keyword(row[0])
        if kw_raw not in reverse:
            continue
        try:
            factor = to_float(row[1])
        except (ValueError, IndexError):
            continue

        section, key = reverse[kw_raw]
        obj = R[section].get(key)
        if obj is None:
            continue

        box = parser._extract_box(parser._row_numbers(row[2:]))
        if box and parser._box_is_full_layer(box, ni, nj):
            _, _, _, _, k1, k2 = box
            vals = parser._expand_obj_to_k_values(obj, nk)
            for k in range(max(k1 - 1, 0), min(k2, nk)):
                if vals[k] is not None:
                    vals[k] *= factor
            R[section][key] = parser._collapse_k_values(
                vals,
                obj.get("unit", ""),
                f"{obj.get('source', kw_raw)} (MULTIPLY {factor})",
                distribution="by_layer" if nk > 1 else "constant",
                axis="k",
                format_hint={"keyword": "MULTIPLY", "box_scope": "full_layer"},
            )
        elif box and len(box) == 6:
            parser._record_unparsed(parser._last_lineno(), f"MULTIPLY {kw_raw}", reason="partial box multiply not represented exactly")
        elif obj["type"] == "scalar":
            obj["value"] *= factor
        elif obj["type"] == "array":
            obj["values"] = [v * factor for v in obj["values"]]
