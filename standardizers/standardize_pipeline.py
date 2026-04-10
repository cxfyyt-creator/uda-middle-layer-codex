from __future__ import annotations

from typing import Any, Dict

from standardizers.model_assembly import assemble_standard_model
from standardizers.section_normalizers import normalize_standard_sections
from standardizers.timeline_builder import build_timeline_events


def normalize_standard_ir(data: Dict[str, Any]) -> Dict[str, Any]:
    return normalize_standard_sections(data)


def build_standard_ir(raw: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_standard_ir(raw)
    timeline_events = build_timeline_events(raw)
    return assemble_standard_model(normalized, raw, timeline_events)
