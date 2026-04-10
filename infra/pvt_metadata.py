from __future__ import annotations

from typing import Any, Dict, Optional


def apply_pvt_role(
    table_obj: Optional[Dict[str, Any]],
    *,
    pvt_form: str,
    representation_role: str,
    preferred_backend: Optional[str] = None,
    derived_from: Optional[list[str]] = None,
) -> Optional[Dict[str, Any]]:
    if not table_obj:
        return table_obj

    obj = dict(table_obj)
    obj["pvt_form"] = pvt_form
    obj["representation_role"] = representation_role
    if preferred_backend:
        obj["preferred_backend"] = preferred_backend
    if derived_from:
        obj["derived_from"] = list(derived_from)
    return obj
