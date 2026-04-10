from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Tuple

from infra.reporting import write_report_bundle
from .confidence_checks import evaluate_confidence
from .target_readiness import evaluate_target_readiness


def _default_preflight(target: str) -> Dict[str, Any]:
    return {
        "target": target,
        "model": "UNKNOWN",
        "warnings": [],
        "blockers": [],
        "ok": True,
        "issues": [],
        "plain_message": "",
        "next_action": "",
    }


def _default_confidence(target: str) -> Dict[str, Any]:
    return {
        "warnings": [],
        "blockers": [],
        "low_confidence_items": [],
        "checked_item_count": 0,
        "warning_threshold": 0.9,
        "block_threshold": 0.5,
        "target": target,
    }


def _attach_report_paths(data: Any, md_path: Path, json_path: Path) -> None:
    if isinstance(data, dict):
        data.setdefault("_generate_report", {"md": str(md_path), "json": str(json_path)})


def write_generation_report(
    data: Any,
    *,
    report_dir: str | Path,
    source_name: str,
    report_type: str,
    title: str,
    summary_items: Iterable[Tuple[str, Any]],
    warnings: List[str] | None = None,
    errors: List[str] | None = None,
    details: Dict[str, Any] | None = None,
) -> Tuple[Path, Path]:
    md_path, json_path = write_report_bundle(
        report_dir=report_dir,
        source_name=Path(source_name).name,
        report_type=report_type,
        title=title,
        summary_items=summary_items,
        warnings=warnings,
        errors=errors,
        details=details,
    )
    _attach_report_paths(data, md_path, json_path)
    return md_path, json_path


def append_capped_prefixed_warnings(
    warnings: List[str],
    *,
    prefix: str,
    items: List[str],
    limit: int = 10,
) -> None:
    warnings.extend(f"{prefix}: {item}" for item in items[:limit])
    if len(items) > limit:
        warnings.append(f"{prefix}: omitted {len(items) - limit} more items")


def _build_preflight_error_message(target_label: str, blockers: List[str], preflight: Dict[str, Any]) -> str:
    message = f"{target_label} generation blocked by preflight checks: " + "; ".join(blockers)
    if preflight.get("plain_message"):
        message += f" | plain: {preflight.get('plain_message')} | next: {preflight.get('next_action')}"
    return message


def _build_confidence_error_message(
    target_label: str,
    confidence_check: Dict[str, Any],
) -> str:
    blockers = list(confidence_check.get("blockers", []))
    return (
        f"{target_label} generation blocked by very low-confidence critical fields: "
        + "; ".join(blockers)
    )


def run_generation_gate(
    data: Any,
    *,
    target: str,
    target_label: str,
    source_name: str,
    report_dir: str | Path,
    report_type: str,
    title: str,
    failed_summary_items: Iterable[Tuple[str, Any]],
    failure_details: Dict[str, Any] | None = None,
    effective_preflight_blockers: List[str] | None = None,
    preflight_blocker_filter: Callable[[Dict[str, Any]], List[str]] | None = None,
    preflight_report_warnings: List[str] | None = None,
) -> Dict[str, Any]:
    if isinstance(data, dict):
        preflight = evaluate_target_readiness(data, target=target)
        confidence_check = evaluate_confidence(data, target=target)
    else:
        preflight = _default_preflight(target)
        confidence_check = _default_confidence(target)

    details = {
        "stage": "pre_generation_validation",
        "preflight": preflight,
        "confidence_check": confidence_check,
    }
    if failure_details:
        details.update(failure_details)

    preflight_blockers = list(
        effective_preflight_blockers
        if effective_preflight_blockers is not None
        else preflight_blocker_filter(preflight)
        if preflight_blocker_filter is not None
        else preflight.get("blockers", [])
    )
    if preflight_blockers:
        write_generation_report(
            data,
            report_dir=report_dir,
            source_name=source_name,
            report_type=report_type,
            title=title,
            summary_items=failed_summary_items,
            warnings=preflight_report_warnings or list(preflight.get("warnings", [])),
            errors=preflight_blockers,
            details=details,
        )
        raise ValueError(_build_preflight_error_message(target_label, preflight_blockers, preflight))

    confidence_blockers = list(confidence_check.get("blockers", []))
    if confidence_blockers:
        write_generation_report(
            data,
            report_dir=report_dir,
            source_name=source_name,
            report_type=report_type,
            title=title,
            summary_items=failed_summary_items,
            warnings=list(preflight.get("warnings", [])) + list(confidence_check.get("warnings", [])),
            errors=confidence_blockers,
            details=details,
        )
        raise ValueError(_build_confidence_error_message(target_label, confidence_check))

    return {
        "preflight": preflight,
        "confidence_check": confidence_check,
    }
