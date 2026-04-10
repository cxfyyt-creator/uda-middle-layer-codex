from __future__ import annotations

from typing import Any, Dict, List

from checks.physics import (
    check_blackoil_validation,
    check_pvt_table_physics,
    check_relperm_table_physics,
    check_wells_validation,
    collect_porosity_physics_issues,
)
from checks.readiness.capability_checks import (
    check_case_runtime_dependencies,
    check_ref_support,
    check_schedule_support,
)
from checks.readiness.completeness_checks import (
    check_blackoil_completeness,
    check_grid_completeness,
    check_meta_completeness,
    check_miscible_completeness,
    check_pvt_table_shapes,
    check_relperm_table_shapes,
    check_water_properties_completeness,
    check_wells_completeness,
)
from checks.readiness.format_coverage_checks import collect_format_coverage_warnings
from checks.readiness.issue_reporting import (
    append_issue_messages,
    build_human_summary,
    build_layer_view,
    build_reason_summary,
    make_issue,
)


def _run_check(fn, *args, **kwargs) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    fn(*args, blockers, warnings, **kwargs)
    return blockers, warnings


def _check_reservoir_physics(data: Dict[str, Any], blockers: List[str], warnings: List[str]) -> None:
    reservoir = data.get("reservoir", {}) or {}
    blockers.extend(collect_porosity_physics_issues(data.get("grid", {}) or {}, reservoir))


def _run_format_coverage_checks(data: Dict[str, Any]) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for message in collect_format_coverage_warnings(data):
        issues.append(make_issue("format_coverage", "format_coverage", "warning", message))
    return issues


def _run_generator_capability_checks(data: Dict[str, Any], *, target: str, model: str) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    blockers, warnings = _run_check(check_schedule_support, data, target=target)
    append_issue_messages(
        issues,
        layer="generator_capability",
        reason_type="generator_capability",
        blockers=blockers,
        warnings=warnings,
    )

    blockers, warnings = _run_check(check_ref_support, data, target=target)
    append_issue_messages(
        issues,
        layer="generator_capability",
        reason_type="generator_capability",
        blockers=blockers,
        warnings=warnings,
    )

    if model.startswith("MIS") and target == "petrel":
        issues.append(
            make_issue(
                "generator_capability",
                "generator_capability",
                "blocker",
                "current Petrel backend does not support miscible export",
            )
        )
    return issues


def _run_validation_rule_checks(data: Dict[str, Any], *, model: str) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    for fn in (
        check_pvt_table_physics,
        check_relperm_table_physics,
        _check_reservoir_physics,
        check_wells_validation,
    ):
        blockers, warnings = _run_check(fn, data)
        append_issue_messages(
            issues,
            layer="validation_rule",
            reason_type="validation_rule",
            blockers=blockers,
            warnings=warnings,
        )

    if model.startswith("MIS"):
        return issues

    blockers, warnings = _run_check(check_blackoil_validation, data)
    append_issue_messages(
        issues,
        layer="validation_rule",
        reason_type="validation_rule",
        blockers=blockers,
        warnings=warnings,
    )
    return issues


def _run_completeness_checks(data: Dict[str, Any], *, target: str, model: str) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    for fn in (
        check_meta_completeness,
        check_grid_completeness,
        check_water_properties_completeness,
        check_pvt_table_shapes,
        check_relperm_table_shapes,
        check_wells_completeness,
    ):
        blockers, warnings = _run_check(fn, data)
        append_issue_messages(
            issues,
            layer="completeness",
            reason_type="ir_expression",
            blockers=blockers,
            warnings=warnings,
        )

    blockers, warnings = _run_check(check_case_runtime_dependencies, data, target=target)
    append_issue_messages(
        issues,
        layer="completeness",
        reason_type="generator_capability",
        blockers=blockers,
        warnings=warnings,
    )

    if model.startswith("MIS"):
        blockers, warnings = _run_check(check_miscible_completeness, data)
    else:
        blockers, warnings = _run_check(check_blackoil_completeness, data, target=target)
    append_issue_messages(
        issues,
        layer="completeness",
        reason_type="ir_expression",
        blockers=blockers,
        warnings=warnings,
    )
    return issues


def evaluate_target_readiness(data: Dict[str, Any], *, target: str) -> Dict[str, Any]:
    fluid = data.get("fluid", {}) or {}
    model = str(fluid.get("model", "BLACKOIL")).upper()
    normalized_target = target.lower()

    issues: List[Dict[str, str]] = []
    issues.extend(_run_format_coverage_checks(data))
    issues.extend(_run_generator_capability_checks(data, target=normalized_target, model=model))
    issues.extend(_run_validation_rule_checks(data, model=model))
    issues.extend(_run_completeness_checks(data, target=normalized_target, model=model))

    blockers = [item["message"] for item in issues if item["severity"] == "blocker"]
    warnings = [item["message"] for item in issues if item["severity"] == "warning"]
    human_summary = build_human_summary(issues)

    return {
        "target": target,
        "model": model,
        "warnings": warnings,
        "blockers": blockers,
        "ok": not blockers,
        "issues": issues,
        "layers": build_layer_view(issues),
        "reason_summary": build_reason_summary(issues),
        "headline": human_summary["headline"],
        "plain_message": human_summary["plain_message"],
        "next_action": human_summary["next_action"],
        "human_summary": human_summary,
    }
