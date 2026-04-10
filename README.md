# 通用数据适配中间层（UDA Middle Layer）

用于在油藏模拟输入文件之间建立统一中间层，当前围绕以下双向链路持续完善：

- Petrel Eclipse `.DATA` → 中间 JSON → CMG `.dat`
- CMG `.dat` → 中间 JSON → Petrel `.DATA`

## 当前状态

- 已有统一 CLI 入口：`cli.py`
- `Petrel -> JSON -> CMG` 主链路已可跑通多个样例
- `CMG -> JSON -> Petrel` 基本可跑，但解析完整性仍需提升
- 当前重点是 IR 表达、工程依赖、unknown keyword 统一、校验闭环和回归测试

## 快速开始

```bash
python cli.py parse-petrel inputs/petrel/SPE1_ODEHIMPLI.DATA -o output/generated/json/
python cli.py generate-cmg output/generated/json/SPE1_ODEHIMPLI_parsed.json -o output/generated/cmg/

python cli.py parse-cmg inputs/cmg/mxspe002.dat -o output/generated/json/
python cli.py generate-petrel output/generated/json/mxspe002_parsed.json -o output/generated/petrel/
```

## 目录说明

- `inputs/`：原始输入文件
- `output/`：统一产物根目录
  - `generated/`：日常转换结果与报告
  - `deliverables/`：正式交付文件
  - `tmp_tests/`：测试临时产物
- `source_readers/`：Petrel / CMG 源格式读取器
- `standardizers/`：原始解析结果到标准模型的标准化流程
- `checks/`：标准模型校验与检查
- `target_writers/`：目标格式写出器
- `registries/`：关键字、单位和结构注册表
- `docs/`：当前文档与历史归档

## 当前文档

- 主上下文：`docs/project/PROJECT_CONTEXT.md`
- 开发路线：`docs/project/REFACTOR_CHECKLIST.md`
- 历史归档：`docs/archive/project_context_1_legacy.md`

## 说明

- CMG→CMG 只作为解析器/生成器局部验证手段，不再作为项目最终目标
- `output/` 中多数内容是可再生产物
- 静态映射优先落在 `registries/*.yaml`，共享支撑放在 `infra/`
- 当前仓库仍包含部分阶段性产物，后续会继续清理
