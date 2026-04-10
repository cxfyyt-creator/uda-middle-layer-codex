from __future__ import annotations

from typing import Any, Dict, List


def check_wells_validation(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    wells = data.get("wells", []) or []
    timeline_events = data.get("timeline_events", []) or []

    for w in wells:
        name = str(w.get("well_name") or "<unnamed>").strip()
        wtype = str(w.get("well_type") or "").upper()
        if wtype == "INJECTOR" and w.get("bhp_min") is not None:
            warnings.append(f"injector well {name} has bhp_min which is unusual")
        if wtype == "PRODUCER" and w.get("bhp_max") is not None:
            warnings.append(f"producer well {name} has bhp_max which is unusual")
        if w.get("rate_max") is not None and float(w.get("rate_max")) <= 0:
            warnings.append(f"well {name} has non-positive rate_max")
        if w.get("bhp_max") is not None and float(w.get("bhp_max")) <= 0:
            warnings.append(f"well {name} has non-positive bhp_max")
        if w.get("bhp_min") is not None and float(w.get("bhp_min")) <= 0:
            warnings.append(f"well {name} has non-positive bhp_min")

    for ev_idx, ev in enumerate(timeline_events):
        if ev.get("absolute_days") is not None and float(ev.get("absolute_days")) < 0:
            blockers.append(f"timeline_events[{ev_idx}] has negative absolute_days")
        if ev.get("event_type") and ev.get("event_type") != "WELL_TARGET_CHANGE":
            warnings.append(f"timeline_events[{ev_idx}] has unsupported event_type={ev.get('event_type')}")
