# CODEX_ACTION_PLAN

> 更新时间：2026-04-01
>
> 这是一份按当前仓库真实状态整理后的简版行动清单，只保留接下来最值得做的事。

---

## 当前判断

项目现在已经不是“从零开始搭框架”的阶段，而是“主流程基本能跑，但稳定性、可读性和一致性还不够”的阶段。所以后面的工作重点不应该是大改结构，而应该先把基础问题修稳，再补强测试，最后再做重构。

简单说：**先修基础，再补防线，最后整理结构。**

---

## 接下来的优先顺序

### P0：先做，越快越好

#### 1. 修复全仓乱码

先把代码、文档、报错信息里的乱码统一修掉。当前不只是文档有问题，`main.py`、`business_rules.py`、`validators/schema.py`、`utils/reporting.py`、`utils/rule_loader.py` 等文件也有乱码。这个问题虽然不一定直接让功能失效，但会明显拖慢理解、排查和后续修改。

**目标：**
- 代码注释能正常读
- 文档能正常读
- 报错和报告信息能正常读

**优先文件：**
- `main.py`
- `business_rules.py`
- `validators/schema.py`
- `utils/reporting.py`
- `utils/rule_loader.py`
- `docs/project/CODEX_ACTION_PLAN.md`
- `docs/project/FAILURE_RECORD.md`

#### 2. 对齐标准模型和校验器

当前 `models/standard_model.py` 里已经有 `timeline_events`、`unparsed_blocks`、`case_manifest` 等字段，但 `validators/schema.py` 里还没有完整接住。这样会造成“前面能产出，后面没真正检查”的问题。

**目标：**
- 标准模型里有的关键字段，校验器里都要有
- `validate_standard_model()` 对这些字段真正生效
- 字段含义前后一致，不要一边新增，一边漏校验

**重点字段：**
- `timeline_events`
- `unparsed_blocks`
- `case_manifest`

#### 3. 统一 unknown / unparsed 记录方式

Petrel 和 CMG 现在都能记录“暂时没处理好的内容”，但格式和粒度还不统一。后面查问题、看报告、做测试时会很别扭。

**目标：**
- 两边统一记录结构
- 至少记录清楚：行号、原文、原因、来源
- 报告里展示方式一致

**建议统一结构：**
```python
{
    "line": int,
    "text": str,
    "reason": str,
    "source": "cmg" | "petrel"
}
```

#### 4. 清理关键位置的 `pass`

现在仓库里还有一批 `pass`，主要集中在两个 parser 里。它们的问题不是“代码不优雅”，而是“出错时会悄悄跳过”，这样最难排查。

**目标：**
- 关键位置不要静默吞错
- 至少写日志，或者写入 `unparsed_blocks`
- 能给默认值的给默认值，不能给的至少留痕

**重点文件：**
- `parsers/cmg_parser.py`
- `parsers/petrel_parser.py`
- `generators/petrel_generator.py`
- `business_rules.py`

---

### P1：P0 做完后立刻跟上

#### 5. 加固现有测试，不重新发明测试

当前仓库已经有一批很有价值的测试，所以现在不是“从零建立测试集”，而是“把已有测试补强，变成稳定基线”。

**当前已有重点测试：**
- `test_cmg_inputs_regression.py`
- `test_cmg_combinative_templates.py`
- `test_ir_upgrade_v1.py`
- `test_flxb_dependency_chain.py`
- `test_petrel_edit_keywords.py`
- `test_active_cell_validation.py`
- `test_target_preflight_layers.py`

**下一步目标：**
- 断言更具体，不只是“能跑”
- 检查井数量、关键表格行数、关键输出片段
- 把常用样例固定成回归基线

#### 6. 检查三条主流程的稳定性

后续修改都要围绕主链路来，不要只盯单个函数。

**重点链路：**
- `Petrel -> JSON -> CMG`
- `CMG -> JSON -> Petrel`
- `CMG -> JSON -> CMG`（仅用于解析/生成校验，不作为最终目标）

**目标：**
- 主流程常见样例能稳定跑通
- 报告、校验、生成三者结果一致
- 不因为小改动破坏现有成功案例

---

### P2：基础稳定后再做

#### 7. 再做结构整理和职责拆分

等前面的基础问题稳定以后，再做结构优化会更安全。否则现在太早大改，容易把已经能跑的能力弄坏。

**可放在后面的工作：**
- WELL / SCHEDULE 语义进一步抽离
- `rules/*.yaml` 职责边界整理
- parser / transformer / generator 的边界清理
- 报告体系继续扩展

**目标：**
- 代码更清楚
- 模块职责更稳定
- 后续扩展更容易

---

## 建议执行顺序

### 第一阶段
1. 修乱码  
2. 对齐标准模型和校验器  
3. 统一 unknown / unparsed  
4. 清理关键 `pass`

### 第二阶段
5. 加固现有测试  
6. 回归三条主流程

### 第三阶段
7. 再做结构整理

---

## 一句话版本

**先把字看清，再把规则对齐，再把错误留痕，再把测试补牢，最后再重构。**

---

## 说明

这份文档是对旧版计划的更新，不再把“从零建测试”或“只要能解析出 wells > 0 就算通过”当成当前目标，而是更强调：**修基础问题、强化已有能力、减少静默失败、稳住主流程。**
