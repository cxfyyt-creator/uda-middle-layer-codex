# 通用数据适配中间层（UDA Middle Layer）

用于在油藏模拟输入文件之间建立统一中间层，当前围绕以下双向链路持续完善：

- Petrel Eclipse `.DATA` → 中间 JSON → CMG `.dat`
- CMG `.dat` → 中间 JSON → Petrel `.DATA`

## 当前状态

- 已有统一 CLI 入口：`main.py`
- `Petrel -> JSON -> CMG` 主链路已可跑通多个样例
- `CMG -> JSON -> Petrel` 基本可跑，但解析完整性仍需提升
- 当前重点是语义保真、unknown keyword 统一、校验闭环和回归测试

## 快速开始

```bash
python main.py parse-petrel inputs/petrel/SPE1_ODEHIMPLI.DATA -o output/generated/json/
python main.py generate-cmg output/generated/json/SPE1_ODEHIMPLI_parsed.json -o output/generated/cmg/

python main.py parse-cmg inputs/cmg/mxspe002.dat -o output/generated/json/
python main.py generate-petrel output/generated/json/mxspe002_parsed.json -o output/generated/petrel/
```

## 目录说明

- `inputs/`：原始输入文件
- `output/`：统一产物根目录
  - `generated/`：日常转换结果与报告
  - `deliverables/`：正式交付文件
  - `tmp_tests/`：测试临时产物
- `parsers/`：Petrel / CMG 解析器
- `transformers/`：原始解析结果到标准模型的转换
- `validators/`：标准模型校验
- `generators/`：目标格式生成器
- `rules/`：关键字、单位和结构规则
- `docs/`：当前文档与历史归档

## 当前文档

- 主上下文：`docs/project/PROJECT_CONTEXT.md`
- 开发路线：`docs/project/REFACTOR_CHECKLIST.md`
- 历史归档：`docs/archive/project_context_1_legacy.md`

## 说明

- `output/` 中多数内容是可再生产物
- 规则优先落在 `rules/*.yaml`，复杂推导集中在 `business_rules.py`
- 当前仓库仍包含部分阶段性产物，后续会继续清理
