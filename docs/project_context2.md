# UDA Middle Layer — Project Context 2

> 更新时间：2026-03-17  
> 目标读者：项目成员 / 维护者 / 代码代理

---

## 1. 项目当前定位

本项目是一个**油藏模拟输入文件中间层转换器**，支持：

- Petrel Eclipse `.DATA` → 中间 JSON → CMG `.dat`
- CMG `.dat` → 中间 JSON → Petrel `.DATA`

核心链路：

`parse -> transform_raw_to_standard -> validate_standard_model -> generate`

---

## 2. 当前代码结构（关键模块）

- `main.py`：统一 CLI 入口（parse/generate）
- `parsers/`
  - `petrel_parser.py`
  - `cmg_parser.py`
- `transformers/`
  - `uda_transformer.py`（`transform_raw_to_standard`）
- `validators/`
  - `schema.py`
  - `__init__.py`
- `generators/`
  - `cmg_generator.py`
  - `petrel_generator.py`

---

## 3. 已确认生效的能力

### 3.1 Transformer / Validator

- `transform_raw_to_standard()` 已生效，包含：
  - `timeline_events` 生成
  - `uda_version`（通过 `StandardModel` 输出）
  - `unparsed_blocks` 透传
- `validate_standard_model()` 已接入 `main.py` 主流程。

### 3.2 Schema 兼容性修复（已做）

为修复 `numerical.max_steps.unit = None` 校验失败，已放宽类型：

- `ScalarValue.unit: Optional[str] = ""`
- `ArrayValue.unit: Optional[str] = ""`
- `TableValue.unit: Optional[str] = "fraction"`

### 3.3 CMG 生成器修复（已做）

`generators/cmg_generator.py` 已包含：

1. 输出段新增：
   - `*OUTSRF *GRID *ALL`
2. 无动态事件时，`_write_schedule()` 会补默认总时长：
   - `*TIME  3650.00`（或使用 `meta._total_sim_time`）
3. 支持：
   - `timeline_events` 驱动的 `*TIME/*ALTER`
   - `unparsed_blocks` 输出到结果注释区

---

## 4. 最新验证结果（关键）

### 4.1 Petrel → CMG（可用）

- `SPE1_ODEHIMPLI.DATA`：可成功 parse + generate-cmg
- 生成结果中已确认包含：
  - `*OUTSRF *GRID *ALL`
  - `*TIME ...` 行

- `SPE2_CHAP.DATA`：可成功生成
  - 输出：`outputs/cmg/SPE2_CHAP_converted.dat`

- `SPE5_MISCIBLE.DATA`：可成功生成（有 unknown keyword 警告）
  - 输出：`outputs/cmg/SPE5_MISCIBLE_converted.dat`

### 4.2 CMG → Petrel（基本可跑，但解析完整性不足）

- `mxspe001.dat`、`mxspe002.dat` 已可 parse + generate-petrel / generate-cmg
- 但 `parse-cmg` 存在大量 `unknown keyword` 警告
- 并且在示例中出现 `Wells: 0`（井解析不完整）

> 结论：反向链路可执行，但语义保真度仍需提升。

---

## 5. 当前已知问题

1. **CMG 关键字覆盖不足**
   - 多个关键字被记录为 unknown（含 RUN 控制、井控制相关项）
2. **井与调度保真不足（CMG 解析侧）**
   - 在某些 CMG 样例中井信息未正确进入标准模型
3. **严格校验与“历史输入脏数据”间的平衡**
   - 当前已放宽 unit，可跑通，但后续建议引入“规范化层”统一处理 `None -> ""`

---

## 6. 推荐下一步（按优先级）

1. **修复 `cmg_parser` 井相关关键字解析**（最高优先）
   - 目标：`mxspe001/mxspe002` parse 后 wells > 0
2. **完善 unknown keyword 处理策略**
   - 分类：可忽略 / 需要结构化支持 / 需要阻断
3. **建立最小回归集**
   - SPE1、SPE2、SPE5 各跑双向链路并校验关键字段
4. **输出质量校验规则**
   - 除“命令成功”外增加内容断言（井数、事件数、关键段存在）

---

## 7. 常用命令（当前可用）

```bash
python main.py parse-petrel inputs/petrel/SPE1_ODEHIMPLI.DATA -o outputs/json/
python main.py generate-cmg outputs/json/SPE1_ODEHIMPLI_parsed.json -o outputs/cmg/

python main.py parse-petrel inputs/petrel/SPE2_CHAP.DATA -o outputs/json/
python main.py generate-cmg outputs/json/SPE2_CHAP_parsed.json -o outputs/cmg/

python main.py parse-cmg inputs/cmg/mxspe002.dat -o outputs/json/
python main.py generate-cmg outputs/json/mxspe002_parsed.json -o outputs/cmg/
python main.py generate-petrel outputs/json/mxspe002_parsed.json -o outputs/petrel/
```

---

## 8. 产物路径示例

- `outputs/json/SPE1_ODEHIMPLI_parsed.json`
- `outputs/cmg/SPE1_ODEHIMPLI_converted.dat`
- `outputs/cmg/SPE2_CHAP_converted.dat`
- `outputs/cmg/SPE5_MISCIBLE_converted.dat`
- `outputs/json/mxspe002_parsed.json`
- `outputs/cmg/mxspe002_converted.dat`

---

如需继续开发，建议从 **CMG parser 的井/调度解析恢复** 开始。