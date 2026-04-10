from __future__ import annotations

from typing import Any, Dict, List


def collect_format_coverage_warnings(data: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []
    if data.get("unknown_keywords"):
        warnings.append(f"unknown_keywords exists: {len(data['unknown_keywords'])} items")
    if data.get("unparsed_blocks"):
        warnings.append(f"unparsed_blocks exists: {len(data['unparsed_blocks'])} items")
    return warnings
