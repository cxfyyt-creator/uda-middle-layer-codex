from __future__ import annotations

from typing import Any, Dict, List


LAYER_ORDER = [
    "format_coverage",
    "generator_capability",
    "validation_rule",
    "completeness",
]
REASON_TYPES = [
    "format_coverage",
    "ir_expression",
    "generator_capability",
    "validation_rule",
]
REASON_LABELS = {
    "format_coverage": "解析器还没读全",
    "ir_expression": "IR 还存不下这类信息",
    "generator_capability": "生成器这一步还处理不了",
    "validation_rule": "校验器这一步没放行",
}


def make_issue(layer: str, reason_type: str, severity: str, message: str) -> Dict[str, str]:
    return {
        "layer": layer,
        "reason_type": reason_type,
        "severity": severity,
        "message": message,
    }


def append_issue_messages(
    issues: List[Dict[str, str]],
    *,
    layer: str,
    reason_type: str,
    blockers: List[str],
    warnings: List[str],
) -> None:
    issues.extend(make_issue(layer, reason_type, "blocker", message) for message in blockers)
    issues.extend(make_issue(layer, reason_type, "warning", message) for message in warnings)


def build_layer_view(issues: List[Dict[str, str]]) -> Dict[str, Dict[str, Any]]:
    view: Dict[str, Dict[str, Any]] = {}
    for layer in LAYER_ORDER:
        layer_issues = [item for item in issues if item["layer"] == layer]
        view[layer] = {
            "ok": not any(item["severity"] == "blocker" for item in layer_issues),
            "blockers": [item["message"] for item in layer_issues if item["severity"] == "blocker"],
            "warnings": [item["message"] for item in layer_issues if item["severity"] == "warning"],
            "issues": layer_issues,
        }
    return view


def build_reason_summary(issues: List[Dict[str, str]]) -> Dict[str, Dict[str, int]]:
    summary: Dict[str, Dict[str, int]] = {}
    for reason_type in REASON_TYPES:
        type_issues = [item for item in issues if item["reason_type"] == reason_type]
        summary[reason_type] = {
            "blockers": sum(1 for item in type_issues if item["severity"] == "blocker"),
            "warnings": sum(1 for item in type_issues if item["severity"] == "warning"),
            "total": len(type_issues),
        }
    return summary


def _human_message_from_issue(issue: Dict[str, str]) -> str:
    message = str(issue.get("message", ""))
    reason_type = str(issue.get("reason_type", ""))
    if message.startswith("missing required CMG runtime input:"):
        detail = message.split(":", 1)[1].strip()
        return f"当前缺少运行时依赖文件：{detail}"
    if "structured backend does not yet support ref values" in message:
        return "当前卡在生成器：IR 里已有外部引用，但目标生成器还不会完整写出"
    if message.startswith("unknown_keywords exists:"):
        return "解析器还没完全覆盖这个样例里的关键字"
    if "active cells with zero porosity" in message:
        return "当前卡在校验：活跃网格里出现了 0 孔隙度"
    if reason_type == "format_coverage":
        return "解析器还没读全这个样例"
    if reason_type == "ir_expression":
        return "IR 里还缺正式表达位置"
    if reason_type == "generator_capability":
        return "生成器这一步还不会处理这类内容"
    if reason_type == "validation_rule":
        return "校验器认为当前数据还不满足生成条件"
    return message


def _next_action_from_issue(issue: Dict[str, str]) -> str:
    message = str(issue.get("message", ""))
    reason_type = str(issue.get("reason_type", ""))
    if message.startswith("missing required CMG runtime input:"):
        return "先补齐依赖文件，或把案例产物关系正式写进工程 IR"
    if "structured backend does not yet support ref values" in message:
        return "先补目标生成器对 ref 外部引用的写出能力"
    if reason_type == "format_coverage":
        return "先补解析器和关键字映射，不要先改案例"
    if reason_type == "ir_expression":
        return "先补 IR 字段或值类型，让中间层存得下"
    if reason_type == "generator_capability":
        return "先补生成器能力，再谈批量扩案例"
    if reason_type == "validation_rule":
        return "先确认数据是否真的有问题，再决定是否调整校验规则"
    return "先定位这条 blocker 属于哪一层，再决定改解析器、IR、生成器还是校验器"


def build_human_summary(issues: List[Dict[str, str]]) -> Dict[str, Any]:
    blockers = [item for item in issues if item["severity"] == "blocker"]
    warnings = [item for item in issues if item["severity"] == "warning"]
    if not blockers:
        headline = "当前预检查已通过"
        return {
            "status": "ok",
            "headline": headline,
            "primary_reason": "",
            "plain_message": headline,
            "next_action": "可以继续生成；若要增强稳定性，再看 warnings",
            "top_blockers": [],
            "top_warnings": [_human_message_from_issue(item) for item in warnings[:3]],
        }

    primary = blockers[0]
    primary_reason = str(primary.get("reason_type", ""))
    reason_label = REASON_LABELS.get(primary_reason, "当前存在未处理问题")
    plain_message = _human_message_from_issue(primary)
    headline = f"当前主要卡点：{reason_label}"
    return {
        "status": "blocked",
        "headline": headline,
        "primary_reason": primary_reason,
        "plain_message": plain_message,
        "next_action": _next_action_from_issue(primary),
        "top_blockers": [_human_message_from_issue(item) for item in blockers[:3]],
        "top_warnings": [_human_message_from_issue(item) for item in warnings[:3]],
    }
