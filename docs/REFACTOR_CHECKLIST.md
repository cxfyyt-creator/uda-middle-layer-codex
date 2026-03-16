# 分层重构清单（Parser / Generator / Rules / Business Rules）

> 目标：形成“规则声明 + 业务逻辑 + 纯编排实现”的稳定架构，减少反复修补。

## 一、目标分层

- **Rules（rules/*.yaml）**：只声明映射、格式、硬性约束、单位规则。
- **Parsers / Generators**：只做语法解析与格式输出，不做复杂业务推导。
- **Business Rules（business_rules.py）**：集中处理智能逻辑、推导、补全、跨表融合。
- **Validators（validators/schema.py）**：强制校验输入/输出中间层合法性，作为闸门。

---

## 二、当前问题到目标归位

### P0（必须优先）

1. **把 CMG 生成器中的 rockfluid 合并逻辑迁到 `business_rules.py`**
   - 迁出：`generators/cmg_generator.py` `_merge_rockfluid/_merge_swt/_merge_slt/_interp1d`
   - 迁入：`business_rules.py`
   - 风险：SWT/SLT 端点与单调性变化
   - 回归：SPE1/SPE2 运行 + KROCHK warning数量对比

2. **修复 CMG 解析器中的 `*KDIR` handler 缺失问题**
   - 现状：规则里注册了 `_parse_kdir`，实现缺失
   - 动作：实现 `_parse_kdir` 或移除映射并明确策略
   - 风险：K层顺序判定不稳定

3. **统一 Unknown keyword 策略（petrel/cmg）**
   - 目标：都记录到 `unknown_keywords`，并进入解析报告

### P1（应尽快）

4. **提取 WELL/SCHEDULE 语义策略到 business_rules**
   - 包括 ALTER 格式策略、TIME 收尾策略
   - 生成器只负责按已规范事件写出

5. **让 `validators/schema.py` 覆盖当前真实中间层字段**
   - 增加 pvto/pvdg/swfn/sgfn/sof3/rsvd/alter_schedule 等
   - 在 parse/generate 主路径增加可选 `strict` 校验

6. **RuleLoader 合并加载规则源**
   - `keyword_registry.yaml`（执行）
   - `units.yaml`（执行）
   - `parameters.yaml`/`file_structure.yaml`（先对齐为文档或纳入执行，不混用）

### P2（质量增强）

7. **报告系统扩展到验证/对比层**
   - 解析报告、生成报告、验证报告三类

8. **增加回归脚本**
   - 一键跑 SPE1/SPE2：parse→generate→关键字段检查
   - 关键检查：`*CO/*PB/*PERMJ/*PVT`、unknown 数量、报告产出

---

## 三、新增报告功能（已落地）

当前已新增：

- `utils/reporting.py`：统一输出 Markdown + JSON 报告
- 解析报告目录：`outputs/reports/parsers/`
- 生成报告目录：`outputs/reports/generators/`

已接入：

- `parse_petrel()`
- `parse_cmg()`
- `generate_cmg()`
- `generate_petrel()`

报告内容包括：

- 概览指标（网格、井数量、表行数、unknown数量等）
- warnings/errors
- 详细信息（可机读 JSON）

---

## 四、执行顺序建议

1. 先完成 P0（业务迁移 + KDIR + unknown统一）
2. 再做 P1（validator 对齐 + schedule 语义抽离）
3. 最后做 P2（回归体系与质量指标）

这样可以保证每一步都可运行、可回归、可解释。
