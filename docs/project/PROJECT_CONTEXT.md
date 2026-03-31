# UDA Middle Layer — Current Project Context

> 更新时间：2026-03-18
>
> 本文件是当前项目的唯一主上下文文档，用于说明现状、风险与后续计划。

---

## 1. 项目定位

本项目是一个油藏模拟输入文件的中间层转换器，当前目标是围绕统一 JSON 中间层，支持以下双向链路：

- Petrel Eclipse `.DATA` → 中间 JSON → CMG `.dat`
- CMG `.dat` → 中间 JSON → Petrel `.DATA`

核心流程如下：

`parse -> transform_raw_to_standard -> validate_standard_model -> generate`

---

## 2. 当前代码结构

- `main.py`：统一 CLI 入口
- `parsers/`
  - `petrel_parser.py`
  - `cmg_parser.py`
- `transformers/`
  - `uda_transformer.py`
- `validators/`
  - `schema.py`
- `generators/`
  - `cmg_generator.py`
  - `petrel_generator.py`
- `business_rules.py`：表合并、补全、推导逻辑
- `rules/`：关键字、单位和结构规则

---

## 3. 已确认可用能力

### 3.1 主流程

- `main.py` 已统一接入 `parse-petrel`、`parse-cmg`、`generate-cmg`、`generate-petrel`
- `transform_raw_to_standard()` 已接入主流程
- `validate_standard_model()` 已作为主路径校验闸门
- 解析与生成报告已写入 `output/generated/reports/`

### 3.2 已跑通样例

- Petrel → CMG：`SPE1_ODEHIMPLI`、`SPE1_ODEHIMPES`、`SPE2_CHAP`、`SPE5_MISCIBLE`
- CMG → Petrel / CMG：`mxspe001`、`mxspe002` 基本可跑通

### 3.3 当前产物特征

- 生成器可输出 CMG `.dat`
- Petrel 解析侧已能提取网格、PVT、井、时间事件等关键结构
- Transformer 会补充 `uda_version`、`timeline_events`、`unparsed_blocks`

---

## 4. 当前主要问题

### 4.1 CMG 解析完整性仍不足

- `parse-cmg` 仍存在较多 `unknown keyword`
- 某些样例中井和调度信息进入标准模型不完整
- 当前主要风险不在“能不能跑”，而在“语义是否保真”

### 4.2 unknown keyword 策略尚未统一

- Petrel 侧会尽量保留未知关键字的值
- CMG 侧目前主要保留关键字名
- 两侧报告粒度还不一致

### 4.3 标准模型与校验模型尚未完全对齐

- `StandardModel` 已包含 `timeline_events`、`unparsed_blocks`
- `validators/schema.py` 仍需继续覆盖真实中间层字段

### 4.4 自动化回归不足

- 当前以样例文件和手工跑通为主
- 还缺少稳定的最小回归脚本和断言集

---

## 5. 当前优先级

1. 修复 `cmg_parser` 的井与调度解析
2. 统一 unknown keyword 的记录和报告策略
3. 对齐 `StandardModel` 与 `validators/schema.py`
4. 建立最小回归集，覆盖 `SPE1`、`SPE2`、`SPE5`、`mxspe001`、`mxspe002`
5. 持续清理工程产物与文档冗余

---

## 6. 推荐命令

```bash
python main.py parse-petrel inputs/petrel/SPE1_ODEHIMPLI.DATA -o output/generated/json/
python main.py generate-cmg output/generated/json/SPE1_ODEHIMPLI_parsed.json -o output/generated/cmg/

python main.py parse-petrel inputs/petrel/SPE2_CHAP.DATA -o output/generated/json/
python main.py generate-cmg output/generated/json/SPE2_CHAP_parsed.json -o output/generated/cmg/

python main.py parse-cmg inputs/cmg/mxspe002.dat -o output/generated/json/
python main.py generate-petrel output/generated/json/mxspe002_parsed.json -o output/generated/petrel/
```

---

## 7. 文档约定

- 当前主文档：`docs/project/PROJECT_CONTEXT.md`
- 当前开发路线：`docs/project/REFACTOR_CHECKLIST.md`
- 历史归档文档：`docs/archive/project_context_1_legacy.md`

不再维护多个“current context”并行文档，避免信息分叉。
