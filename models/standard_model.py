from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class StandardModel:
    """UDA Standard Model v1 (minimal contract)."""

    uda_version: str = "1.0.0"
    meta: Dict[str, Any] = field(default_factory=dict)
    grid: Dict[str, Any] = field(default_factory=dict)
    reservoir: Dict[str, Any] = field(default_factory=dict)
    fluid: Dict[str, Any] = field(default_factory=dict)
    rockfluid: Dict[str, Any] = field(default_factory=dict)
    initial: Dict[str, Any] = field(default_factory=dict)
    numerical: Dict[str, Any] = field(default_factory=dict)
    wells: List[Dict[str, Any]] = field(default_factory=list)
    timeline_events: List[Dict[str, Any]] = field(default_factory=list)
    unparsed_blocks: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uda_version": self.uda_version,
            "meta": self.meta,
            "grid": self.grid,
            "reservoir": self.reservoir,
            "fluid": self.fluid,
            "rockfluid": self.rockfluid,
            "initial": self.initial,
            "numerical": self.numerical,
            "wells": self.wells,
            "timeline_events": self.timeline_events,
            "unparsed_blocks": self.unparsed_blocks,
        }
