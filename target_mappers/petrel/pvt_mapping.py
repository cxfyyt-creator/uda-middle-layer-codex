from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from infra.pvt_metadata import apply_pvt_role


def build_petrel_pvt_tables(fluid: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    pvto = fluid.get("pvto_table")
    pvdg = fluid.get("pvdg_table")
    if pvto or pvdg:
        return pvto, pvdg

    pvt6 = fluid.get("pvt_table")
    if not pvt6 or not pvt6.get("rows"):
        return None, None

    rows6 = pvt6.get("rows", [])
    pvto_rows = [[row[1], row[0], row[2], row[4]] for row in rows6 if len(row) >= 6]
    pvdg_rows = [[row[0], 1.0 / row[3] if row[3] > 0 else 0.0, row[5]] for row in rows6 if len(row) >= 6]

    pvto = apply_pvt_role(
        {
            "type": "table",
            "columns": ["rs", "p", "bo", "viso"],
            "rows": pvto_rows,
            "confidence": 0.9,
            "source": "target_mappers.petrel.pvt_mapping.build_petrel_pvt_tables",
        },
        pvt_form="eclipse_pvto",
        representation_role="derived_for_petrel",
        preferred_backend="petrel",
        derived_from=["fluid.pvt_table"],
    )
    pvdg = apply_pvt_role(
        {
            "type": "table",
            "columns": ["p", "bg", "visg"],
            "rows": pvdg_rows,
            "confidence": 0.9,
            "source": "target_mappers.petrel.pvt_mapping.build_petrel_pvt_tables",
        },
        pvt_form="eclipse_pvdg",
        representation_role="derived_for_petrel",
        preferred_backend="petrel",
        derived_from=["fluid.pvt_table"],
    )
    return pvto, pvdg
