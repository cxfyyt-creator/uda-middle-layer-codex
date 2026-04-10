# 现有文件到目标架构的迁移映射

## 1. 说明

这份文档是硬重构的第 1 步成果。

目的只有一个：
- 把当前仓库里的主要代码文件，明确映射到目标架构中的新位置和新职责。

后续所有重命名、拆分、删旧文件、改 import，都以这份映射为依据。

---

## 2. 目标架构回顾

目标主链路：

`原始文件 -> source_readers -> Source IR -> standardizers -> Standard IR -> target_mappers -> Target IR -> target_writers -> 目标文件`

目标一级目录：

- `source_readers/`
- `standardizers/`
- `domain_logic/`
- `target_mappers/`
- `target_writers/`
- `checks/`
- `infra/`
- `registries/`
- `ir_contracts/`
- `application/`
- `docs/`
- `tests/`
- `cli.py`

---

## 3. 当前目录到目标目录映射

| 当前目录/文件 | 目标位置 | 处理方式 | 说明 |
| --- | --- | --- | --- |
| `parsers/` | `source_readers/` | 重命名并拆分 | 表达“读取源格式”，后续按 `eclipse/`、`cmg/` 子目录拆。 |
| `transformers/` | `standardizers/` | 重命名并拆分 | 当前真实职责是标准化，不用再叫 transformer。 |
| `domain_rules/` | `domain_logic/` | 重命名 | 保留领域语义逻辑。 |
| `generators/` | `target_writers/` | 重命名并拆分 | 当前是真正在写目标文件。 |
| `validators/` | `checks/` | 重命名并拆分 | 以后拆成 `schema/`、`physics/`、`readiness/`。 |
| `utils/` | `infra/` | 重命名并筛分 | 保留基础设施与共享能力。 |
| `rules/` | `registries/` | 重命名并拆子目录 | 当前更像映射表和注册表。 |
| `models/` | `ir_contracts/` | 重命名并扩展 | 强调 IR 契约，不是泛 model。 |
| `main.py` | `cli.py` | 重命名 | 当前就是 CLI 入口。 |
| `run_convert.py` | `application/quick_convert.py` 或删除 | 降级或移除 | 历史快捷脚本，不作为主入口。 |
| `business_rules.py` | 删除 | 删除 | 不再保留旧门面，统一走新架构。 |

---

## 4. 当前 Python 文件到目标位置映射

### 4.1 入口与流程编排

| 当前文件 | 目标文件 | 处理方式 | 目标职责 |
| --- | --- | --- | --- |
| `main.py` | `cli.py` | 重命名 | CLI 参数入口。 |
| `run_convert.py` | `application/quick_convert.py` 或删除 | 视需要保留 | 快捷转换脚本，不进入核心主链。 |

### 4.2 源格式读取层

| 当前文件 | 目标文件 | 处理方式 | 目标职责 |
| --- | --- | --- | --- |
| `parsers/petrel_parser.py` | `source_readers/eclipse/reader_pipeline.py` + 多个子 reader | 拆分 | 读取 Eclipse/Petrel 源文件。 |
| `parsers/cmg_parser.py` | `source_readers/cmg/reader_pipeline.py` + 多个子 reader | 拆分 | 读取 CMG 源文件。 |

建议从这两个大文件中拆出的子模块：

- `meta_reader.py`
- `grid_reader.py`
- `fluid_reader.py`
- `pvt_reader.py`
- `rockfluid_reader.py`
- `well_reader.py`
- `schedule_reader.py`
- `reader_pipeline.py`

### 4.3 标准化层

| 当前文件 | 目标文件 | 处理方式 | 目标职责 |
| --- | --- | --- | --- |
| `transformers/uda_transformer.py` | `standardizers/standardize_pipeline.py` | 重命名并拆分 | 把 `Source IR` 整理成 `Standard IR`。 |
| `transformers/__init__.py` | `standardizers/__init__.py` | 同步重命名 | 导出标准化入口。 |

后续建议补出的文件：

- `standardizers/standard_pipeline.py`
- `standardizers/standardize_pipeline.py`

### 4.4 领域语义层

| 当前文件 | 目标文件 | 处理方式 | 目标职责 |
| --- | --- | --- | --- |
| `domain_rules/fluid_rules.py` | `domain_logic/fluid_logic.py` | 重命名并筛分 | 纯流体语义补全与推导。 |
| `domain_rules/reference_rules.py` | `domain_logic/reference_logic.py` | 重命名 | 引用、EQUALSI、网格方向语义。 |
| `domain_rules/common.py` | `domain_logic/common_logic.py` 或 `infra/semantic_helpers.py` | 再判定 | 看是否仍属于领域层。 |
| `domain_rules/__init__.py` | `domain_logic/__init__.py` | 同步重命名 | 导出领域逻辑。 |

注意：
- `domain_rules/pvt_rules.py`
- `domain_rules/rockfluid_rules.py`

这两个文件中目前混了“领域逻辑”和“目标适配逻辑”，不能原样平移。

### 4.5 目标适配层

| 当前文件 | 目标文件 | 处理方式 | 目标职责 |
| --- | --- | --- | --- |
| `domain_rules/pvt_rules.py` | `target_mappers/cmg/pvt_mapping.py` | 主要迁移 | 处理 `pvto+pvdg -> cmg_pvt_table` 这类目标适配。 |
| `domain_rules/rockfluid_rules.py` | `target_mappers/cmg/rockfluid_mapping.py` | 主要迁移 | 处理 `swfn+sof3 -> swt`、`sgof -> slt` 这类目标适配。 |

后续还应补出：

- `target_mappers/cmg/target_ir_builder.py`
- `target_mappers/petrel/target_ir_builder.py`
- `target_mappers/petrel/pvt_mapping.py`

### 4.6 目标写出层

| 当前文件 | 目标文件 | 处理方式 | 目标职责 |
| --- | --- | --- | --- |
| `generators/cmg_generator.py` | `target_writers/cmg/writer_pipeline.py` + 多个 writer | 拆分 | 写出 CMG 文件。 |
| `generators/petrel_generator.py` | `target_writers/petrel/writer_pipeline.py` + 多个 writer | 拆分 | 写出 Petrel/Eclipse 文件。 |

建议拆出的子 writer：

- `grid_writer.py`
- `fluid_writer.py`
- `rockfluid_writer.py`
- `initial_writer.py`
- `well_writer.py`
- `writer_pipeline.py`

### 4.7 校验与生成前检查

| 当前文件 | 目标文件 | 处理方式 | 目标职责 |
| --- | --- | --- | --- |
| `validators/schema.py` | `checks/schema/standard_model_schema.py` | 重命名并后续拆分 | 标准 IR 结构约束。 |
| `validators/__init__.py` | `checks/__init__.py` | 同步重命名 | 导出检查入口。 |
| `utils/target_preflight.py` | `checks/readiness/target_readiness.py` | 迁移并拆分 | 目标生成前就绪检查。 |
| `utils/confidence_checks.py` | `checks/readiness/confidence_checks.py` | 迁移 | 置信度检查。 |

后续建议继续细分：

- `checks/schema/`
- `checks/physics/`
- `checks/readiness/`

### 4.8 基础设施层

| 当前文件 | 目标文件 | 处理方式 | 目标职责 |
| --- | --- | --- | --- |
| `utils/project_paths.py` | `infra/project_paths.py` | 重命名 | 路径约定。 |
| `utils/reporting.py` | `infra/reporting.py` | 重命名 | 报告写出。 |
| `utils/rule_loader.py` | `infra/registry_loader.py` | 重命名 | 加载 YAML 注册表。 |
| `utils/value_semantics.py` | `infra/value_semantics.py` | 重命名 | 值语义辅助。 |
| `utils/ir_normalization.py` | `infra/ir_normalization.py` | 重命名 | IR 归一化。 |
| `utils/case_materialization.py` | `infra/case_materialization.py` | 重命名 | 运行时文件物化。 |
| `utils/cmg_case_dependencies.py` | `infra/case_dependencies.py` | 重命名 | 案例依赖分析。 |
| `utils/generation_orchestration.py` | `checks/readiness/generation_gate.py` | 重命名并迁移 | 生成前统一编排。 |
| `utils/pvt_metadata.py` | `infra/pvt_metadata.py` | 重命名 | PVT 元信息辅助。 |
| `utils/unit_converter.py` | `infra/unit_converter.py` | 重命名 | 单位换算辅助。 |

### 4.9 注册表与静态映射

| 当前文件 | 目标文件 | 处理方式 | 目标职责 |
| --- | --- | --- | --- |
| `rules/keyword_registry.yaml` | `registries/source_formats/keywords.yaml` 或按格式拆分 | 拆分 | 源格式关键字映射。 |
| `rules/units.yaml` | `registries/units.yaml` | 平移 | 单位换算规则。 |
| `rules/parameters.yaml` | `registries/parameters.yaml` | 平移或再命名 | 参数模板与配置。 |
| `rules/file_structure.yaml` | `registries/file_structure.yaml` | 平移 | 文件结构相关静态规则。 |

### 4.10 IR 契约层

| 当前文件 | 目标文件 | 处理方式 | 目标职责 |
| --- | --- | --- | --- |
| `models/standard_model.py` | `ir_contracts/standard_ir.py` | 重命名 | `Standard IR` 契约。 |
| `models/__init__.py` | `ir_contracts/__init__.py` | 同步重命名 | 导出 IR 契约。 |

后续建议新增：

- `ir_contracts/source_ir.py`
- `ir_contracts/target_ir.py`
- `ir_contracts/value_objects.py`

---

## 5. 当前测试到目标测试结构映射

| 当前文件 | 建议目标位置 | 说明 |
| --- | --- | --- |
| `tests/test_schema_alignment.py` | `tests/contracts/test_standard_ir_alignment.py` | 更偏契约对齐。 |
| `tests/test_ir_upgrade_v1.py` | `tests/pipelines/test_ir_upgrade_v1.py` | 更偏升级链路。 |
| `tests/test_flxb_dependency_chain.py` | `tests/infra/test_case_dependencies.py` | 更偏基础设施能力。 |
| `tests/test_target_preflight_layers.py` | `tests/checks/test_target_readiness.py` | 更偏 readiness。 |
| `tests/test_cmg_inputs_regression.py` | `tests/regression/test_cmg_inputs.py` | 输入回归。 |
| `tests/test_petrel_generation_smoke.py` | `tests/writers/test_petrel_writer_smoke.py` | 目标写出冒烟。 |
| `tests/test_business_rules_facade.py` | 删除 | 硬重构后不再保留旧门面。 |

---

## 6. 第一阶段正式实施顺序

建议先做这 5 件事：

1. `transformers/` 正式改为 `standardizers/`
2. `generators/` 正式改为 `target_writers/`
3. `utils/` 正式改为 `infra/`
4. `models/` 正式改为 `ir_contracts/`
5. `main.py` 正式改为 `cli.py`

原因：
- 这些改名主要是“术语纠正”，收益高。
- 对架构理解帮助最大。
- 还不会马上触发大量细粒度逻辑拆分。

---

## 7. 当前结论

第 1 步不是改代码逻辑，而是先把迁移地图画清楚。

这样后面的每一步都能明确回答：
- 这个文件为什么要改名。
- 这个文件改完以后归哪层。
- 这个逻辑是领域语义、目标适配、校验，还是基础设施。
