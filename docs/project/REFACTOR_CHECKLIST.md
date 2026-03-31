# 分层重构清单（当前版）

> 目标：保持“规则声明 + 业务规则 + 解析/生成编排 + 校验闭环”的稳定结构。

## 1. 已完成或基本完成

### 架构层

- `transformers/uda_transformer.py` 已接入主流程
- `validators/schema.py` 已接入 `main.py`
- `business_rules.py` 已承接部分表融合、补全和推导逻辑
- 解析报告与生成报告已落地到 `output/generated/reports/`

### 能力层

- Petrel → CMG 主链路已能跑通多个样例
- CMG → Petrel 已具备基本链路
- `*KDIR` 解析已存在，不再作为待修项

---

## 2. 当前仍需推进的事项

### P0：高优先级

1. **修复 `cmg_parser` 的井与调度解析完整性**
   - 目标：`mxspe001`、`mxspe002` 解析后 `wells > 0`
   - 风险：反向链路可跑但语义不完整

2. **统一 unknown keyword 策略**
   - 目标：Petrel / CMG 两侧统一保留关键字、值、上下文与报告口径

3. **让标准模型与校验模型对齐**
   - 补齐 `timeline_events`、`unparsed_blocks` 及真实使用字段

### P1：中优先级

4. **继续抽离 WELL / SCHEDULE 语义到 `business_rules.py`**
   - 生成器只负责写格式
   - 语义归一放到规则层和业务层

5. **建立最小回归集**
   - 覆盖 `SPE1`、`SPE2`、`SPE5`、`mxspe001`、`mxspe002`
   - 校验井数、事件数、unknown 数量、关键段存在性

6. **统一规则源职责**
   - `keyword_registry.yaml`、`units.yaml`、`parameters.yaml`、`file_structure.yaml` 各自边界要更清晰

### P2：质量增强

7. **扩展报告体系**
   - 补充验证报告或对比报告

8. **完善工程卫生**
   - 清理生成物、缓存文件、重复文档入口
   - 持续收敛仓库中的阶段性产物

---

## 3. 推荐执行顺序

1. 先修 `cmg_parser` 的井/调度解析
2. 再统一 unknown keyword 和 schema 对齐
3. 然后补最小回归集
4. 最后再扩展报告和工程清理

这样可以优先解决“能跑但不够准”的核心问题。
