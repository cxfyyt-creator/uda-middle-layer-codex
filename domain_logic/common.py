from __future__ import annotations

from typing import Any, Dict, List, Optional

from infra.registry_loader import get_loader


def scalar_obj(
    value: float,
    unit: str,
    *,
    modifier: Optional[str] = None,
    source: str = "domain_logic",
) -> Dict[str, Any]:
    obj = {
        "type": "scalar",
        "value": float(value),
        "unit": unit,
        "source": source,
        "confidence": 0.9,
    }
    if modifier:
        obj["modifier"] = modifier
    return obj


def table_obj(columns: List[str], rows: List[List[float]], *, source: str) -> Dict[str, Any]:
    return {
        "type": "table",
        "columns": columns,
        "rows": rows,
        "source": source,
        "confidence": 0.9,
    }


def factor(rule_name: str, default: float = 1.0) -> float:
    rl = get_loader()
    rule = rl.unit_rule(rule_name) or {}
    raw_factor = rule.get("factor")
    return default if raw_factor is None else float(raw_factor)


def convert_by_rule(
    value: float,
    rule_name: str,
    *,
    context: Optional[Dict[str, Any]] = None,
) -> float:
    rl = get_loader()
    rule = rl.unit_rule(rule_name) or {}
    raw_factor = rule.get("factor")
    if raw_factor is not None:
        return float(value) * float(raw_factor)
    formula = str(rule.get("formula", "")).strip().lower()
    ctx = context or {}
    if rule_name == "eclipse_bg_to_cmg_eg" or "1000.0 /" in formula:
        bg = float(ctx.get("bg_eclipse", value))
        return 0.0 if bg == 0 else 1000.0 / bg
    return float(value)
