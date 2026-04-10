from __future__ import annotations

import re

from infra.value_semantics import apply_value_semantics


def to_float(raw):
    return float(str(raw).replace("d", "e").replace("D", "E"))


def expand_repeat(token):
    match = re.match(r"^(\d+)\*([0-9.eEdD+\-]+)$", token)
    if match:
        return [to_float(match.group(2))] * int(match.group(1))
    return None


def scalar(value, unit, source, modifier=None):
    payload = {"type": "scalar", "value": value, "unit": unit, "confidence": 0.99, "source": source}
    if modifier:
        payload["modifier"] = modifier
    return apply_value_semantics(
        payload,
        value_type="scalar",
        modifier=modifier,
        software="cmg_imex",
    )


def array(values, unit, source, modifier=None):
    payload = {
        "type": "array",
        "values": values,
        "unit": unit,
        "grid_order": "IJK",
        "confidence": 0.99,
        "source": source,
    }
    if modifier:
        payload["modifier"] = modifier
    return apply_value_semantics(
        payload,
        value_type="array",
        modifier=modifier,
        software="cmg_imex",
    )


def table(columns, rows, source):
    return {"type": "table", "columns": columns, "rows": rows, "confidence": 0.99, "source": source}
