from __future__ import annotations

from typing import Any, Dict, List


def build_timeline_events(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for well in raw.get("wells", []):
        well_name = well.get("well_name", "UNKNOWN")
        for event in well.get("alter_schedule", []):
            item = {
                "well_name": well_name,
                "absolute_days": float(event.get("time", 0.0)),
                "event_type": "WELL_TARGET_CHANGE",
            }
            if "rate" in event:
                item["target"] = "RATE"
                item["value"] = event.get("rate")
            else:
                item["target"] = event.get("target", "ORATE")
                item["value"] = event.get("value")
            events.append(item)
    events.sort(key=lambda x: x.get("absolute_days", 0.0))
    return events
