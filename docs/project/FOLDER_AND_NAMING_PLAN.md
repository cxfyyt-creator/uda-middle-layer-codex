# 文件夹职责与命名整改方案

## 1. 目标

这份文档只做两件事：
- 说明当前各文件夹实际在放什么、负责什么。
- 给出一版更清晰的命名方案，减少 `transformers`、`utils`、`generators` 这类过宽或有歧义的名字。

命名原则如下：
- 名字要直接表达职责，不要表达模糊动作。
- 同一层只做一种事。
- “读源格式”“整理标准语义”“适配目标格式”“写目标文件”四层必须分开。

---

## 2. 当前目录职责

### `parsers/`
- 当前职责：读取 Eclipse / CMG 原始文件，把文本解析成项目内部原始结构。
- 当前问题：名字还行，但文件太大，且内部混了关键字分发、段落识别、表解析、特殊语义处理。

### `transformers/`
- 当前职责：把解析结果整理成标准中间表示，并串起若干规则。
- 当前问题：`transformer` 这个词太泛，不知道是在“标准化”“映射”“改格式”还是“适配目标”。

### `domain_rules/`
- 当前职责：放领域规则、补全规则、推导规则。
- 当前问题：目前里面仍混了一部分目标适配逻辑，例如 `pvto+pvdg -> cmg_pvt_table` 这类规则。

### `generators/`
- 当前职责：把整理好的数据写成 CMG / Petrel 目标文件。
- 当前问题：`generator` 这个词偏泛，真实职责其实是“目标文件写出器”。

### `validators/`
- 当前职责：schema 校验、结构约束、部分物理约束。
- 当前问题：目录名本身问题不大，但未来应继续细分 `schema`、`physics`、`preflight`。

### `utils/`
- 当前职责：路径、报告、规则加载、文件物化、预检、置信度、IR 小工具等。
- 当前问题：`utils` 过宽，什么都能往里放，最终最容易再次变成大杂烩。

### `rules/`
- 当前职责：YAML 规则文件，如关键字映射、单位、参数、文件结构。
- 当前问题：`rules` 太宽，里面实际上混了“源格式映射规则”“单位规则”“参数模板”。

### `models/`
- 当前职责：标准模型 dataclass。
- 当前问题：`models` 太泛，容易和数据库模型、Pydantic 模型、IR 契约混淆。

### `tests/`
- 当前职责：回归测试、结构对齐测试、专项问题测试。
- 当前问题：当前组织方式偏“历史问题归档”，后续还要补“按层测试”。

### `docs/`
- 当前职责：项目上下文、重构清单、工作总结、学习笔记。
- 当前问题：结构已有基础，但还缺一份统一的目录职责说明和命名规范。

### `main.py`
- 当前职责：CLI 入口。
- 当前问题：名字普通但过宽，且文件承担的不是纯 CLI，而是流程编排。

### `run_convert.py`
- 当前职责：历史快捷脚本，跑固定转换流程。
- 当前问题：名字过于临时，像实验脚本，不像正式入口。

---

## 3. 建议命名方案

### 一级目录建议

| 当前名字 | 建议名字 | 原因 |
| --- | --- | --- |
| `parsers/` | `source_readers/` | 更明确表达“读取源格式”而不是泛泛解析。 |
| `transformers/` | `standardizers/` | 真实职责是把原始结构整理成标准 IR，不是泛化 transform。 |
| `domain_rules/` | `domain_logic/` | 表达“领域语义逻辑”，比 `rules` 更不容易和 YAML 规则混淆。 |
| `generators/` | `target_writers/` | 真实职责是写目标文件，不是泛化 generator。 |
| `validators/` | `checks/` | 覆盖 schema、physics、preflight，比 validator 更宽但仍清晰。 |
| `utils/` | `infra/` | 这些内容本质上是基础设施和共享支撑，不是零散工具。 |
| `rules/` | `registries/` | 更像规则注册表和映射清单，而不是运行时业务逻辑。 |
| `models/` | `ir_contracts/` | 明确这些是 IR 契约，不是 ORM/model 那类“模型”。 |

### 入口文件建议

| 当前名字 | 建议名字 | 原因 |
| --- | --- | --- |
| `main.py` | `cli.py` | 入口职责更明确。 |
| `run_convert.py` | `quick_convert.py` 或删除 | 当前更像历史快捷脚本，建议弱化或移除。 |
| `business_rules.py` | 删除 | 当前决定走硬重构，不再保留旧出口。 |

---

## 4. 建议的新目录结构

```text
source_readers/
  eclipse/
    meta_reader.py
    grid_reader.py
    fluid_reader.py
    pvt_reader.py
    rockfluid_reader.py
    well_reader.py
    schedule_reader.py
    assembler.py
  cmg/
    meta_reader.py
    grid_reader.py
    fluid_reader.py
    pvt_reader.py
    rockfluid_reader.py
    well_reader.py
    schedule_reader.py
    assembler.py

standardizers/
  standardize_pipeline.py
  standard_pipeline.py

domain_logic/
  fluid_logic.py
  grid_logic.py
  reference_logic.py
  rockfluid_logic.py
  well_logic.py

target_mappers/
  cmg/
    pvt_adapter.py
    rockfluid_adapter.py
    fluid_adapter.py
  petrel/
    pvt_adapter.py
    rockfluid_adapter.py
    fluid_adapter.py

target_writers/
  cmg/
    grid_writer.py
    fluid_writer.py
    rockfluid_writer.py
    well_writer.py
    case_writer.py
  petrel/
    runspec_writer.py
    props_writer.py
    solution_writer.py
    schedule_writer.py
    case_writer.py

checks/
  schema/
    standard_model_schema.py
  physics/
    fluid_checks.py
    rockfluid_checks.py
    well_checks.py
  preflight/
    cmg_preflight.py
    petrel_preflight.py
    issue_model.py

infra/
  project_paths.py
  reporting.py
  rule_loader.py
  case_materialization.py
  generation_gate.py
  confidence_checks.py
  ir_normalization.py
  value_semantics.py

registries/
  source_formats/
    eclipse_keywords.yaml
    cmg_keywords.yaml
  units.yaml
  value_semantics.yaml
  target_capabilities/
    cmg.yaml
    petrel.yaml

ir_contracts/
  source_ir.py
  standard_ir.py
  target_ir.py
  value_objects.py

application/
  parse_service.py
  standardize_service.py
  generate_service.py
  convert_service.py

cli.py
```

---

## 5. 关键命名解释

### 为什么不用 `transformers`
- 这个词太抽象。
- 外人看不出来这是“标准化层”还是“目标适配层”。
- 项目里后续一定会同时存在 `source -> standard` 和 `standard -> target` 两种变换，继续都叫 transformer 会更乱。

### 为什么建议用 `standardizers`
- 它直接说明这一层的主职责是“整理成标准 IR”。
- 以后如果出现 `target_mappers`，两者边界很清楚。

### 为什么 `domain_rules` 也想改名
- `rules` 容易和 `rules/*.yaml` 混。
- `domain_logic` 更像“领域语义逻辑”，不容易和静态映射表混淆。

### 为什么 `generators` 想改成 `target_writers`
- 当前这层的真正职责不是“生成任何东西”，而是“写目标文件”。
- `writer` 比 `generator` 更具体。

### 为什么 `utils` 想改成 `infra`
- `utils` 会导致任何杂项代码都塞进去。
- 当前这里已经不是简单小工具，而是基础设施层。

### 为什么 `rules` 想改成 `registries`
- 当前这些 YAML 更像注册表、映射表、能力表。
- 它们不是运行时的业务逻辑。

### 为什么 `models` 想改成 `ir_contracts`
- 这里存的是 IR 契约和结构定义。
- `models` 太泛，后面容易和 Pydantic schema、数据库 model 混掉。

---

## 6. 各层输入输出边界

### `source_readers`
- 输入：原始文件文本。
- 输出：`Source IR`。

### `standardizers`
- 输入：`Source IR`。
- 输出：`Standard IR`。

### `domain_logic`
- 输入：标准化过程中的局部数据块。
- 输出：更完整或更一致的语义结果。

### `target_mappers`
- 输入：`Standard IR`。
- 输出：目标软件友好的 `Target IR` 或目标侧数据块。

### `target_writers`
- 输入：`Target IR` 或目标友好块。
- 输出：最终目标文件文本。

### `checks`
- 输入：`Source IR`、`Standard IR` 或 `Target IR`。
- 输出：错误、警告、issue、通过/失败结论。

### `infra`
- 输入输出不固定。
- 只提供公共支撑，不承载领域决策。

### `application`
- 编排整条流程。
- 不持有复杂业务规则。

---

## 7. 对当前仓库的迁移建议

### 第一阶段：先改“概念”
- 保留现有代码位置。
- 先统一文档和术语。
- 先约定 `transformers = standardizers` 的新含义。

### 第二阶段：拆“目标适配”
- 把当前 `domain_rules/pvt_rules.py`、`domain_rules/rockfluid_rules.py` 里明显带目标偏向的逻辑，迁到 `target_mappers/cmg/`。
- 让 `domain_logic` 保持更纯。

### 第三阶段：拆“大文件”
- `parsers/*` 拆 reader 子模块。
- `generators/*` 拆 writer 子模块。
- `checks` 继续拆 `schema/preflight/physics`。

### 第四阶段：再做正式重命名
- 目录和文件名一起改。
- 同时修改 import、测试和文档。
- 最后移除过渡门面。

---

## 8. 当前文件夹内容及作用记录

### 根目录
- `.idea/`：IDE 配置。
- `.pytest_cache/`：测试缓存。
- `.qoder/`：编辑器/工具配置。
- `docs/`：项目文档、上下文、工作记录。
- `domain_rules/`：当前已拆出的领域规则模块。
- `generators/`：当前目标文件写出层，后续建议改名为 `target_writers/`。
- `inputs/`：原始样例输入文件。
- `models/`：当前 IR 结构定义，后续建议改名为 `ir_contracts/`。
- `output/`：生成产物、报告、测试临时文件。
- `parsers/`：当前源格式解析层，后续建议改名为 `source_readers/`。
- `rules/`：当前 YAML 规则与映射文件，后续建议改名为 `registries/`。
- `tests/`：测试。
- `transformers/`：当前标准化层，后续建议改名为 `standardizers/`。
- `utils/`：当前共享工具与基础设施，后续建议改名为 `infra/`。
- `validators/`：当前校验层，后续建议改名为 `checks/`。
- `business_rules.py`：已删除，不再保留旧门面。
- `main.py`：当前 CLI 入口，后续建议改名为 `cli.py`。
- `run_convert.py`：历史快捷脚本，建议弱化或移除。
- `README.md`：项目说明。

---

## 9. 最终建议

先不要一口气重命名整个仓库。
最稳妥的顺序是：
- 先统一文档和术语。
- 再把目标适配规则从领域规则里拆出去。
- 再拆 parser / writer 大文件。
- 最后统一正式改名。

当前最值得先落地的正式命名调整是：
- `transformers/` -> `standardizers/`
- `utils/` -> `infra/`
- `generators/` -> `target_writers/`
- `main.py` -> `cli.py`
