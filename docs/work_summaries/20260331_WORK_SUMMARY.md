# 2026-03-31 工作总结（按 2026-03-31 当前方向重写）

说明：这份文档不再把 2026-03-31 理解成“CMG source-faithful roundtrip 阶段总结”，而是按当前仓库方向，重新定位为 **IR v1.0 + 工程依赖表达 + 分层 preflight** 的阶段总结。

## 1. 核心结论

2026-03-31 这一阶段真正建立起来的，不是“dat 到 dat 的保真回写能力”，而是三件更重要的事：
1. `ref` 进入标准模型，外部文件引用终于有正式位置；
2. `case_manifest` 进入正式结构，案例级静态输入、运行时输入、运行时输出终于有正式位置；
3. `preflight` 开始能按层归因，失败不再只是“生成失败”，而能更清楚地区分解析器、IR、生成器和校验层。

所以，这一天的价值应当定义为：**项目开始从案例修补转向工程型 IR 建设。**

## 2. 当前仓库已对应的落点

### 2.1 IR v1.0 已落到代码
- `validators/schema.py`：已有 `RefValue`、`CaseDependencyItem`、`CaseManifestBlock`。
- `models/standard_model.py`：已有 `case_manifest`、`timeline_events`、`unparsed_blocks`。
- `parsers/cmg_parser.py`：已能识别 `SIP_DATA`、`BINARY_DATA`、`*EQUALSI`，并构建 `case_manifest`。
- `transformers/uda_transformer.py`：统一组装标准模型。
- `generators/cmg_generator.py`：结构化生成路径已接入 `ref`、运行时依赖装配与报告。

### 2.2 `case_manifest` 已不只是输入清单
当前 `case_manifest` 已正式包含：
- `root_file`
- `source_dir`
- `static_inputs`
- `runtime_inputs`
- `runtime_outputs`

并且 `runtime_outputs` 已用于：
- 上下游案例装配分析
- preflight 依赖提示
- 生成阶段运行时文件补齐

### 2.3 preflight 已形成分层输出
当前 `utils/target_preflight.py` 已能输出：
- `format_coverage`
- `ir_expression`
- `generator_capability`
- `validation_rule`

并补充：
- `headline`
- `plain_message`
- `next_action`

这意味着系统开始具备“失败可解释”的雏形。

### 2.4 active/null 与 FLXB 两条工程链已经接上
- `active_cell_mask / pinchout_array / cell_activity_mode` 已落到解析、转换、校验链。
- `FLXB-IN / FLXB-OUT` 已进入依赖扫描、case 装配分析、preflight 报错和生成期补齐链路。

## 3. 这次方向校正后，哪些东西已经变化

现在已经明确：**CMG→CMG 不再以 source-faithful 为主线。** 当前代码已同步做了这件事：
- 删除了 `tests/test_cmg_source_faithful_roundtrip.py`；
- `parsers/cmg_parser.py` 不再把原始 deck 文本、source dir、roundtrip mode 写进 `meta`；
- `generators/cmg_generator.py` 不再走 preserved deck 回写，而是统一走结构化生成；
- `utils/target_preflight.py` 不再给 source-faithful 特判放行；
- 相关测试已改成围绕结构化生成、`ref`、`case_manifest`、`FLXB` 依赖链和 preflight 分层来验证。

换句话说，`CMG -> JSON -> CMG` 现在只作为 **解析器 / IR / 生成器局部能力测试**，不再作为项目最终目标。

## 4. 这一天最该保留的项目理解

如果用最简单的话说，这一天最重要的收获不是“我们能不能把 dat 原样写回去”，而是：
- 我们开始知道哪些信息应该进 IR；
- 我们开始知道哪些失败属于解析器，哪些属于生成器；
- 我们开始知道一个案例不只是模型字段，还包括依赖文件和运行时产物。

这三点，才是后面做跨软件工程级转换的基础。

## 5. 当前最直接的下一步

按现在的方向，下一步最具体的事应该是：
1. 继续补 `ref` 的结构化写回，让 `mxdrm005` 真正从“能表达”推进到“能生成”；
2. 继续补 `FLXB-IN` 的工程装配，让 `mxgeo008/010/012` 从“装配能跑”推进到“结构化稳定”；
3. 继续把外部数组、引用型 payload、corner-point 等内容正式放进 IR，而不是再回到原文保留思路；
4. 把当前文档口径统一成“IR / 工程依赖 / 分层失败归因”，不再混用“保真回写主线”的旧说法。

## 6. 本次核对涉及的关键文件

- `parsers/cmg_parser.py`
- `transformers/uda_transformer.py`
- `validators/schema.py`
- `generators/cmg_generator.py`
- `utils/cmg_case_dependencies.py`
- `utils/target_preflight.py`
- `tests/test_ir_upgrade_v1.py`
- `tests/test_flxb_dependency_chain.py`
- `tests/test_target_preflight_layers.py`
- `tests/test_active_cell_validation.py`
