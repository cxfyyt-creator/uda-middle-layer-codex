# =============================================================================
# utils/rule_loader.py
# 规则加载器 — 统一读取 rules/ 目录下所有 YAML 规则文件
# Parser 和 Generator 通过此类获取关键字映射、格式类型、单位换算
# =============================================================================

import yaml
from pathlib import Path

# 默认 rules 目录：相对于本文件两级上目录
_DEFAULT_RULES_DIR = Path(__file__).parent.parent / "rules"


class RuleLoader:
    """
    单例-友好的规则加载器。
    用法：
        rl = RuleLoader()
        kw_map = rl.petrel_kw_map()   # {KEYWORD_UPPER: entry_dict}
        gen_cfg = rl.cmg_gen_config() # generators.cmg 配置
    """

    def __init__(self, rules_dir=None):
        rules_dir = Path(rules_dir) if rules_dir else _DEFAULT_RULES_DIR
        with open(rules_dir / "keyword_registry.yaml", encoding="utf-8") as f:
            self._reg = yaml.safe_load(f)
        with open(rules_dir / "units.yaml", encoding="utf-8") as f:
            self._units = yaml.safe_load(f)

    # ── Petrel 相关 ─────────────────────────────────────────────────────────

    def petrel_kw_map(self):
        """返回 {KEYWORD_UPPER: entry_dict}，供 petrel_parser 主循环分发"""
        return {k.upper(): v
                for k, v in self._reg["petrel"]["keywords"].items()}

    def petrel_sections(self):
        return [s.upper() for s in self._reg["petrel"]["sections"]]

    def petrel_unit_flags(self):
        return [f.upper() for f in self._reg["petrel"]["unit_flags"]]

    # ── CMG 相关 ────────────────────────────────────────────────────────────

    def cmg_kw_map(self):
        """返回 {*KEYWORD_UPPER: entry_dict}，供 cmg_parser 主循环分发"""
        return {k.upper(): v
                for k, v in self._reg["cmg"]["keywords"].items()}

    def cmg_ignore_set(self):
        """返回应当忽略的 CMG 关键字集合（大写）"""
        return {k.upper() for k in self._reg["cmg"].get("ignore_keywords", [])}

    # ── 生成器配置 ──────────────────────────────────────────────────────────

    def cmg_gen_config(self):
        """返回 generators.cmg 配置字典"""
        return self._reg["generators"]["cmg"]

    def petrel_gen_config(self):
        """返回 generators.petrel 配置字典"""
        return self._reg["generators"]["petrel"]

    # ── 单位换算 ────────────────────────────────────────────────────────────

    def convert(self, value, from_unit, to_unit):
        """
        根据 units.yaml 进行单位换算。
        如果无对应规则，返回原值（不报错）。
        温度等非线性换算由 formula 字段描述，此处仅支持 factor 类型。
        """
        if from_unit is None or to_unit is None or from_unit == to_unit:
            return value
        if value is None:
            return None
        for conv in self._units.values():
            if (conv.get("from_unit") == from_unit and
                    conv.get("to_unit") == to_unit):
                factor = conv.get("factor")
                if factor is not None:
                    return value * factor
        # 未找到换算规则
        return value

    def unit_factor(self, from_unit, to_unit):
        """返回换算系数，找不到返回 1.0"""
        if from_unit is None or to_unit is None or from_unit == to_unit:
            return 1.0
        for conv in self._units.values():
            if (conv.get("from_unit") == from_unit and
                    conv.get("to_unit") == to_unit):
                f = conv.get("factor")
                if f is not None:
                    return f
        return 1.0


# 模块级单例（大多数场景直接 import 使用）
_loader = None


def get_loader(rules_dir=None):
    """返回全局单例 RuleLoader（懒初始化）"""
    global _loader
    if _loader is None or rules_dir is not None:
        _loader = RuleLoader(rules_dir)
    return _loader
