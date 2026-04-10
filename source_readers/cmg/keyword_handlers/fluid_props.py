from __future__ import annotations

from source_readers.cmg.token_stream import is_kw
from source_readers.cmg.value_builders import expand_repeat, scalar, table, to_float


def parse_density_typed(parser, R):
    token = parser._peek()
    if not token or not is_kw(token[1]):
        return
    _, density_type = parser._next()
    density_type_upper = density_type.lstrip("*").upper()
    token = parser._peek()
    if not token or is_kw(token[1]):
        return
    try:
        value = to_float(token[1])
        parser.pos += 1
    except ValueError:
        return
    lineno = parser._last_lineno()
    source = f"fluid *DENSITY *{density_type_upper} line {lineno}"
    key_map = {
        "OIL": "oil_density",
        "GAS": "gas_density",
        "WATER": "water_density",
        "SOLVENT": "solvent_density",
    }
    key = key_map.get(density_type_upper)
    if key:
        R["fluid"][key] = scalar(value, "lb/ft3", source)


def parse_model(parser, R):
    token = parser._peek()
    if token and is_kw(token[1]):
        _, model_keyword = parser._next()
        model = model_keyword.lstrip("*").upper()
        R["fluid"]["model"] = model
        if model.startswith("MIS"):
            R["meta"]["model_type"] = "miscible"


def parse_gravity(parser, R):
    token = parser._peek()
    if not token or not is_kw(token[1]):
        return
    _, gravity_type = parser._next()
    gravity_type_upper = gravity_type.lstrip("*").upper()
    token = parser._peek()
    if not token or is_kw(token[1]):
        return
    try:
        value = to_float(token[1])
        parser.pos += 1
    except ValueError:
        return
    R.setdefault("fluid", {})[f"{gravity_type_upper.lower()}_gravity"] = scalar(
        value,
        "",
        f"fluid *GRAVITY *{gravity_type_upper}",
    )


def parse_zg(parser, R):
    rows = []
    while parser._peek():
        lineno, tok = parser._peek()
        if parser._is_top_level_kw_token(tok):
            break
        row_tokens = parser._read_same_line_tokens(lineno)
        nums = []
        for item in row_tokens:
            expanded = expand_repeat(item)
            if expanded is not None:
                nums.extend(expanded)
                continue
            try:
                nums.append(to_float(item))
            except ValueError:
                pass
        if len(nums) >= 6:
            rows.append(nums[:6])
    if rows:
        R.setdefault("fluid", {})["zg_table"] = table(
            ["p", "c1", "c2", "c3", "c4", "c5"],
            rows,
            "fluid *ZG",
        )
