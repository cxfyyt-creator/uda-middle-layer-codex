# 2026-03-27 工作总结与对话纪要

本文档记录 2026-03-27 围绕 UDA Middle Layer 中 CMG `dat -> json -> dat` roundtrip 所做的分析、修改、测试、交付与方法论反思。今天最重要的收获不是“又支持了几个关键字”，而是明确了一个更基础的事实：**CMG dat / deck 不是普通字段集合，而是带有执行语义、上下文依赖、外部文件依赖和顺序约束的输入包。**

因此，今天的工作目标逐步从“能解析、能生成”转向“生成结果是否仍然保留原始 CMG deck 的求解器语义，并能被 IMEX 真正接受”。

---

## 1. 今日任务主线

今天围绕用户需求，主线可以分成 5 段。

### 1.1 从 roundtrip 测试切入，目标是验证 CMG 解析器能力

用户首先要求：

- 从 `inputs/cmg` 中取原始 `.dat`
- 执行 `dat -> json -> dat`
- 产出 roundtrip 文件给用户在 CMG IMEX 中实际测试
- 重点不是单个样例能转，而是借此评估 `cmg_parser` 的能力边界

同时，用户明确提出：

- 回答要紧凑
- 不要针对某一个地方打补丁
- 要解决“一类问题”
- 不分先后地推进：整体代码理解、roundtrip 测试、其他示例测试、导入格式理解

### 1.2 用户实际跑 IMEX，暴露出内部测试未覆盖的真实问题

在初版 roundtrip 文件交付后，用户拿生成结果在本地 CMG IMEX 2021.10 上运行，先后暴露出多类错误，例如：

- `PERMJ` 缺失或未正确默认
- `*TRES` 未在 `*PVT *ZG` 之前定义
- `PVT TABLE` 中 `Eg` 检查失败
- `*USER_INPUT` 初始化被错误改写为 `*VERTICAL *BLOCK_CENTER *WATER_OIL_GAS`
- `mxdrm005_roundtrip.dat` 运行时找不到 `mxdrm005.sip`

这些问题说明：

- parser / transformer / generator 的内部链路“能跑通”并不等于 CMG 能跑通
- 内部 schema 验证不是最终验收标准
- 求解器级验证必须成为 roundtrip 的核心环节

### 1.3 逐步从“修单点错误”转向“识别语义类问题”

随着用户不断反馈真实报错，今天的工作重心逐步从：

- 追一个报错补一个 patch

转向：

- 识别哪些信息属于 deck 语义
- 找出哪些语义在当前中间层中会丢失
- 建立更稳妥的 roundtrip 策略

### 1.4 工作方式被用户直接质疑后，开始系统反思

用户明确提出：

- “你有没有思考为什么会出现这样的情况呢”
- “我认为你的工作方式有点问题”
- “哪些是有用的，哪些是无用的”

这些反馈直接推动本轮工作从“继续堆功能”转向“重新定义 roundtrip 的正确目标”。

### 1.5 最终收口：把 CMG roundtrip 的主策略改为 source-faithful

在充分暴露问题后，今天最终形成的核心策略是：

> 对于来源本身就是 CMG 的 case，`CMG -> JSON -> CMG` 不再优先做“重建式生成”，而是优先做 **source-faithful roundtrip**：保留原始 deck 文本与外部运行依赖，在输出时原样或近原样回写。

这是今天最关键的方法论升级。

---

## 2. 今天的核心结论

今天最重要的结论有 4 个。

### 2.1 CMG roundtrip 的本质不是字段重组，而是 deck 语义保真

以下几件事并不等价：

- parser 能把 dat 读成 JSON
- transformer 能把 raw 数据变成 standard model
- generator 能写出新的 dat
- IMEX 真正接受并运行这个 dat

今天反复出现的问题，都属于前 3 步看似成立，但第 4 步失败。

### 2.2 一个 CMG case 不只是 `.dat` 文件，而是一个 deck / case package

今天后半段明确认识到：

- `dat` 只是主输入文件
- `INCLUDE` / `SIPDATA-IN` / 其他外部文件也是 case 的一部分
- deck 的正确性不仅取决于 dat 内容，还取决于外部依赖文件是否完整可用

因此，**roundtrip 的交付对象不能只是一份 dat 文本，而应是可执行 case 所需的输入包。**

### 2.3 保真优先于重建，特别是对复杂 CMG deck

复杂 deck 中最容易被“重建式生成”破坏的内容包括：

- `*VARI` / `*DTOP` / `*MOD` / `*NULL`
- `SIP_DATA` 外部属性引用
- `*EQUALSI` 引用语义
- `*USER_INPUT` 初始化模式
- 井控 / 调度 / 顺序依赖

因此，今天明确放弃了“尽量把所有 CMG deck 重新建模后再生成”的默认方向，转而优先采用原始 source-faithful 回写。

### 2.4 “有用”和“无用”必须从是否影响运行来划分，而不是从是否看起来重要来划分

今天对“有用 / 无用”的区分已经明确。

**有用的：**

- 会直接影响 CMG 是否能读入、初始化、运行的内容
- 原始 deck 文本本身
- `SIPDATA-IN`、`*INCLUDE`、`INCLUDE` 等运行依赖
- deck 中表达初始化机制、PVT 上下文、引用关系的语义信息

**无用或当前不应优先处理的：**

- 只影响输出控制、不影响输入求解器运行的元信息
- 如 `*OUTPUT`、`*INDEX-OUT`、`*MAIN-RESULTS-OUT`、`*CASEID`、`*WRST` 等
- 为了“格式更统一”而主动改写原 deck 建模方式
- 针对单一样例追加 if/else 式补丁

---

## 3. 为什么前面会反复报错

今天的错误并不是偶然，而是现有工作方式在几个层面上的必然结果。

### 3.1 验收标准偏向内部一致性，而不是求解器可执行性

此前更重视：

- `unknown_keywords` 是否为空
- `unparsed_blocks` 是否为空
- `validate_standard_model(strict=True)` 是否通过
- `generate_cmg()` 是否成功写出文本

这些检查有价值，但它们主要验证的是 **内部结构自洽**，并不能保证 **CMG deck 语义保真**。

### 3.2 过早把 deck 当成“通用字段集合”

CMG deck 中很多信息不是普通数值字段，而是求解器语言的一部分。

例如：

- `*PERMJ *EQUALSI`：不是一个数值，而是“引用关系”
- `*PERMK *EQUALSI * 0.01`：不是一个单值，而是“引用关系 + 缩放”
- `*TRES`：不仅是温度值，还带有上下文顺序要求
- `*USER_INPUT`：不是标记文字，而是初始化机制切换
- `SIP_DATA`：不是属性值，而是外部文件引用机制

如果把这些都先压扁成普通字段，再重新拼装，语义很容易丢。

### 3.3 生成器做了不该做的“规范化改写”

今天较大的问题之一，是生成器在没有足够依据时，把原始建模方式重写成另一套它认为“更统一”的表达。

最典型的是：

- 原始文件用 `*USER_INPUT`
- 生成器却写成 `*VERTICAL *BLOCK_CENTER *WATER_OIL_GAS`

这不是格式变化，而是建模语义变化。

### 3.4 之前只做了“文本 roundtrip”，没做“案例 roundtrip”

`mxdrm005` 的问题尤其典型。

当时的问题不是：

- dat 写错了

而是：

- 只交付了主 dat
- 没有把 `mxdrm005.sip` 这个运行依赖一起交付

这说明当时对 roundtrip 的理解还停留在“文本层”，没有上升到“案例层”。

---

## 4. 今日代码修改总览

今天最终有效、值得保留的修改主要集中在 5 个方向。

### 4.1 继续完善传统重建链路中的关键语义

今天前半段对原有 parser / transformer / generator 链路做了多项修复，主要包括：

#### 4.1.1 `*EQUALSI` 语义保留

相关文件：

- `parsers/cmg_parser.py`
- `business_rules.py`
- `transformers/uda_transformer.py`
- `generators/cmg_generator.py`

完成内容：

- parser 识别 `*EQUALSI`
- transformer / business_rules 解析引用关系与缩放
- generator 能回写 `*EQUALSI` / `*EQUALSI * scale`

目的：

- 修复 `PERMJ` / `PERMK` 这种“引用型属性”在 roundtrip 中丢失的问题

#### 4.1.2 `*TRES` 与 `*PVT *ZG` 的顺序与上下文修复

相关文件：

- `rules/keyword_registry.yaml`
- `validators/schema.py`
- `generators/cmg_generator.py`

完成内容：

- 把 `*TRES` 正式纳入 fluid 语义
- 在 generator 中保证 `*TRES` 出现在 `*PVT` 之前

目的：

- 修复 `ZG` 类型 PVT 数据对 reservoir temperature 的上下文依赖

#### 4.1.3 `INITIAL` 段不再一刀切重写

相关文件：

- `rules/keyword_registry.yaml`
- `generators/cmg_generator.py`

完成内容：

- 区分 `*USER_INPUT` 初始化和 `*VERTICAL ...` 初始化
- 支持 `*PRES`、`*SW`、`*SO`、`*SG`、`*PB`、`*PBS` 等用户输入型初值写回

目的：

- 修复 `mxspe005` 这类案例中初始化机制被错误替换的问题

### 4.2 引入 source-faithful CMG roundtrip 模式

这是今天后半段最重要的新修改。

相关文件：

- `parsers/cmg_parser.py`
- `generators/cmg_generator.py`

完成内容：

#### parser 侧

在 `CMGParser` 中新增：

- `self.raw_lines`
- 加载 token 时保留原始行文本

在 `parse()` 返回前写入：

- `R["meta"]["_cmg_roundtrip_mode"] = "source_faithful"`
- `R["meta"]["_cmg_raw_deck_lines"] = list(self.raw_lines)`
- `R["meta"]["_cmg_source_dir"] = str(self.filepath.parent)`

#### generator 侧

在 `CMGGenerator` 中新增：

- `_preserved_cmg_deck(self, data)`

行为：

- 如果来源是 CMG
- 且 roundtrip 模式为 `source_faithful`
- 且带有原始 deck 行文本
- 则直接回写原始 deck 内容，而不是走重建式生成

意义：

- 避免复杂 CMG deck 在中间层重建过程中丢失 `VARI / SIP_DATA / 顺序 / 井控` 等语义

### 4.3 新增 CMG case dependency 扫描器

相关文件：

- `utils/cmg_case_dependencies.py`（新增）
- `parsers/cmg_parser.py`
- `generators/cmg_generator.py`

新增能力：

- `scan_cmg_case_dependencies(raw_lines, source_dir=None)`

当前已识别为 **运行依赖** 的内容：

- `SIPDATA-IN`
- `*INCLUDE`
- `INCLUDE`

扫描结果会写入：

- `meta._cmg_case_dependencies.runtime_inputs`
- `meta._cmg_case_dependencies.missing_runtime_inputs`
- `meta._cmg_case_dependencies.ignored_lines`

其中：

- `runtime_inputs`：真正影响运行的外部输入文件
- `missing_runtime_inputs`：源目录中缺失的运行依赖
- `ignored_lines`：当前识别为非运行依赖控制信息的行

### 4.4 自动复制外部运行依赖文件

相关文件：

- `generators/cmg_generator.py`

新增内容：

- `_copy_external_file_refs(self, data, output_file)`

行为：

- 生成 dat 后
- 自动根据 `runtime_inputs` 复制对应外部文件到输出目录
- 避免仅交付 dat 导致 case 不完整

本轮直接解决的问题：

- `mxdrm005_roundtrip.dat` 会自动配套复制 `mxdrm005.sip`

同时还加了一个小的稳健性修复：

- 若目标文件已存在，则跳过复制，避免 Windows 下重复覆盖时触发权限问题

### 4.5 在 preflight 中加入“缺失运行依赖即阻断”

相关文件：

- `utils/target_preflight.py`
- `tests/test_cmg_source_faithful_roundtrip.py`

新增逻辑：

- 对 CMG 目标，在 preflight 中检查 `missing_runtime_inputs`
- 如果存在缺失依赖，则直接加入 blocker
- 错误信息形如：
  - `missing required CMG runtime input: mxdrm005.sip`

意义：

- 不再生成“看起来有 dat、实际上必然跑不起来”的交付物
- 把案例级错误尽早前移到生成阶段暴露

---

## 5. 今日测试与验证工作

### 5.1 回归测试补充与运行

今天使用并扩展了以下测试文件：

- `tests/test_cmg_inputs_regression.py`
- `tests/test_cmg_combinative_templates.py`
- `tests/test_cmg_source_faithful_roundtrip.py`

其中 `test_cmg_source_faithful_roundtrip.py` 主要验证：

1. `mxdrm001`：
   - source-faithful roundtrip 后内容与原始 dat 一致
   - 没有 runtime inputs
   - 存在 ignored lines

2. `mxdrm005`：
   - runtime input 正确识别为 `mxdrm005.sip`
   - 缺失列表为空
   - 生成时会复制 `mxdrm005.sip`
   - 回写结果保留 `FILENAMES SIPDATA-IN 'mxdrm005.sip'`
   - 保留 `POR SIP_DATA`、`PERMI SIP_DATA`、`*GRID *VARI 13 14 11`

3. 缺失依赖时阻断：
   - 如果只复制 `mxdrm005.dat`，不提供 `mxdrm005.sip`
   - 生成阶段会被 preflight blocker 拦截

今天最终执行的测试命令：

```bash
python -m unittest tests.test_cmg_source_faithful_roundtrip tests.test_cmg_inputs_regression tests.test_cmg_combinative_templates
```

结果：

- `OK`

### 5.2 用户本地 IMEX 验证

今天最关键的外部验证不是 unittest，而是用户在本地 CMG IMEX 2021.10 的真实运行。

最终确认：

- `deliverables/cmg_roundtrip_20260327_mxdrm5/mxdrm005_roundtrip.dat`
- 配套 `deliverables/cmg_roundtrip_20260327_mxdrm5/mxdrm005.sip`

对应输出文件 `mxdrm005_roundtrip.out` 中已出现：

- `Stopping time reached.`
- `0 Error messages.`
- `End of Simulation: Normal Termination`

这意味着：

- `mxdrm005` 这一轮已经不再停留在“内部自洽”
- 而是实现了案例级可运行

---

## 6. 今日交付结果

今天主要形成并保留了以下交付目录：

```text
D:\01_projects\uda_middle_layer_codex\deliverables\cmg_roundtrip_20260327_mxdrm5
```

其中对当前任务最关键的文件包括：

- `mxdrm001_roundtrip.dat`
- `mxdrm002_roundtrip.dat`
- `mxdrm003_roundtrip.dat`
- `mxdrm004_roundtrip.dat`
- `mxdrm005_roundtrip.dat`
- `mxdrm005.sip`

此外，目录中还有用户本地运行生成的：

- `.out`
- `.sr3`
- `.rstr.sr3`
- `cmgjournal.log`

这些文件不是本轮代码生成逻辑的重点，但它们为今天的求解器级验证提供了依据。

---

## 7. 今天关于“有用 / 无用”的明确结论

这是用户今天特别强调的一点，下面给出今天最终形成的判断。

### 7.1 有用的内容

以下内容是今天确认“真正有用、值得保留和继续加强”的：

1. **source-faithful roundtrip 策略**
   - 对 CMG 来源 case，优先保留原始 deck
   - 避免无谓重建导致语义破坏

2. **case dependency 扫描与复制**
   - 把 dat 视为 case package 的一部分
   - 识别并带上 `SIPDATA-IN` / `INCLUDE`

3. **preflight 前移阻断**
   - 缺依赖不再继续生成
   - 尽早暴露必然失败的案例

4. **求解器级验证**
   - 以 IMEX 是否接受输入作为重要验收标准
   - 而不是只看内部 JSON / schema / report

5. **区分运行依赖与输出控制信息**
   - 用“是否影响运行”来划分优先级

6. **清理用户可见输出目录**
   - 临时测试不要堆到用户 output 目录
   - 交付目录和临时目录要分离

### 7.2 无用或当前阶段价值很低的内容

以下内容今天已经证明，要么无用，要么在当前阶段优先级过低：

1. **把复杂 CMG deck 一律重新建模后再生成**
   - 对工程 roundtrip 来说风险过高

2. **为了统一格式主动改写建模机制**
   - 比如把 `*USER_INPUT` 改写成 `*VERTICAL ...`
   - 这会破坏原始语义

3. **只靠内部单元测试自证正确**
   - 如果不结合 IMEX 结果，就容易形成假通过

4. **对单一样例做孤立补丁**
   - 只能暂时压住一个错误，不能解决类问题

5. **把输出控制信息误判为运行必需项**
   - `*OUTPUT`、`*CASEID`、`*WRST` 等当前不应当作为运行依赖强处理

6. **在 `outputs/` 下堆积大量临时目录**
   - 对用户无帮助，只会增加干扰

---

## 8. 今天的文档、代码与测试文件变化

### 8.1 主要修改文件

今天涉及并确认有效的主要文件包括：

- `parsers/cmg_parser.py`
- `generators/cmg_generator.py`
- `utils/cmg_case_dependencies.py`（新增）
- `utils/target_preflight.py`
- `tests/test_cmg_source_faithful_roundtrip.py`
- `tests/test_cmg_inputs_regression.py`
- `tests/test_cmg_combinative_templates.py`
- `rules/keyword_registry.yaml`
- `validators/schema.py`
- `transformers/uda_transformer.py`
- `business_rules.py`

### 8.2 今天新增或强化的测试意图

今天的测试重点不再只是：

- parse 成功
- generate 成功

而是逐步转向：

- 关键语义是否保留
- 运行依赖是否识别完整
- 缺失依赖是否提前阻断
- 交付目录是否包含完整 case 所需文件
- 用户拿到后是否能在 IMEX 中正常运行

---

## 9. 今天对 Petrel 与 CMG 解析器关系的认识

今天虽然主要在修 CMG，但对架构也形成了一个更清晰的认识：

- Petrel 与 CMG 解析器在大框架上都属于“外部 deck / data -> 中间层 -> 再输出”的思路
- 但两者并不能简单认为“方法完全一样、保真要求完全一样”

原因是：

1. **CMG deck 的语言性更强**
   - 顺序、机制、外部引用、上下文依赖非常重要

2. **Petrel / Eclipse 风格数据块更偏结构化表述**
   - 虽然也有语义问题，但很多块相对更适合字段化建模

3. **因此不能假设：两份语义相同的 data/dat 经过两个解析器后，一定得到完全一致的中间文件，再生成完全一致的输出文本**

更现实的目标应该是：

- 在中间层表达上尽量对齐同类物理语义
- 在输出时遵守各自目标求解器的语言与语义要求
- 对 CMG 来源 case，优先做 CMG 自身语义保真

---

## 10. 今天对“deck”这一概念的理解收敛

用户今天问到“什么是 deck”。今天的工作也让这个概念更明确了。

在当前项目语境下，**deck** 可以理解为：

> 求解器可执行输入包，而不是单独某一个文本文件。

对 CMG 来说，它通常包括：

- 主 `.dat` 文件
- `INCLUDE` 引用文件
- `SIPDATA-IN` 等外部属性文件
- 这些文件之间的路径关系
- 关键字顺序、上下文、机制切换等求解器语义

因此，今天之后对“roundtrip 正确”的理解应分 3 层：

1. **文本层**：主 dat 是否保真
2. **语义层**：关键机制、顺序、引用是否保真
3. **案例层**：外部依赖是否一起交付，是否能独立运行

---

## 11. 今天清理输出目录的情况

按照用户要求，今天已做以下处理：

- 停止继续在 `outputs/` 下堆积新一轮临时目录
- 统一把正式交付内容放到 `deliverables/`
- 使用 `.tmp_tests`、`.tmp_build_mxdrm5` 作为临时目录
- 在任务结束后已将这些临时目录删除

当前项目根目录已不再保留这轮产生的 `.tmp_tests`、`.tmp_build_mxdrm5`。

这一点虽然不是算法改进，但对工程使用体验很重要：

- 用户可见目录更干净
- 临时产物与正式交付物分离
- 后续定位问题更清晰

---

## 12. 当前仍然存在的限制

尽管今天已经完成了重要收口，但仍有以下限制需要明确。

### 12.1 仍有相当一部分 CMG 块没有被完整结构化解析

今天测试输出中仍能看到不少 `unparsed_blocks` / 未解析内容，例如：

- `*AQUIFER`
- `*AQPROP`
- `*AQFUNC`
- `*SECTOR`
- `*RTYPE`
- `*KROIL *STONE2 *SWSG`
- 一些 `*REGION` / `*NULL` / `*DTOP` / `*MOD` 组合表达

这说明：

- 当前 source-faithful roundtrip 对“原样回写”是安全的
- 但若未来要做更强的跨软件转换或更深的中间层建模，这些块仍需要逐步结构化

### 12.2 目前的 solver 级验证仍主要依赖用户本地环境

今天的最终求解器验证主要来自用户本地 IMEX 2021.10 的实际运行结果。理想状态下，后续还需要：

- 更系统的自动化或半自动化外部求解器回归流程
- 更明确的运行日志收集与对比机制

### 12.3 source-faithful 解决了 roundtrip 可跑问题，但不等于中间层已经足够完善

source-faithful 是当前工程上最稳妥的策略，但它更多解决的是：

- CMG 来源 case 的保真回写
- 用户拿去跑时的可靠性

它并不自动意味着：

- 中间层已经完整理解 CMG deck 的全部语义
- 所有复杂块都可以自由编辑、跨软件映射或重组

这两件事不能混为一谈。

---

## 13. 建议的后续工作

基于今天的结果，后续建议按下面的优先级推进。

### 13.1 先整理“哪些块必须进入中间层，哪些块可以先保真挂载”

这是今天之后最值得做的事情之一。

建议把 CMG 内容分成两类：

1. **必须结构化进入中间层的内容**
   - 会参与跨软件转换或工程编辑的核心语义
   - 如网格、属性、PVT、初始条件、井、调度、关键引用关系

2. **当前可先 source-faithful 保留的内容**
   - 复杂但暂时不需要在中间层中自由编辑的块
   - 如部分 aquifer / sector / 特定模板控制块

### 13.2 建立“CMG roundtrip 必须保真的语义清单”

至少应包括：

- 初始化机制
- 引用型关键字
- 外部依赖文件
- PVT 上下文依赖
- 调度与井控机制
- 关键段落顺序

### 13.3 继续扩大 `inputs/cmg` 样例覆盖，但以“类问题”方式推进

后续不宜再按“来一个新文件，补一个 if”推进，而应：

- 每新增样例，先归类它暴露的是哪一类 deck 语义问题
- 优先修复这类语义的通用处理方式

### 13.4 对未解析块做分类，而不是急于全部解析

今天已经证明：

- 并不是所有未解析块都要立刻深入结构化
- 更重要的是先判断它们是否影响当前目标

换句话说，后续不应盲目追求“unparsed 全清零”，而应优先判断：

- 这块是否影响 roundtrip 可跑
- 这块是否影响后续中间层编辑
- 这块是否影响跨软件转换

---

## 14. 今日一句话总结

如果只用一句话概括今天：

> 今天真正完成的，不只是修了几个 CMG 关键字，而是把 `CMG -> JSON -> CMG` 的理解从“文本转换”提升到了“deck / case 语义保真”，并据此引入了 source-faithful roundtrip、外部依赖扫描复制、缺失依赖前移阻断和求解器级验证这一整套更可靠的工作方式。

---

## 15. 今日后续新增进展（晚间补充）

在完成前半段的 source-faithful roundtrip 改造后，今天后半段继续做了更大范围的样例批量验证，重点不再是只看 `mxspe` / `mxdrm005`，而是继续验证：

- 统一的 CMG 框架是否可以继续承接更多 IMEX 样例
- source-faithful 方案是否可以支撑 GEM 组分模型
- 当前“一个 CMG 框架 + 模型分层扩展”的方向是否成立

### 15.1 新增批量 roundtrip 交付：`mxdrm006` ~ `mxdrm009`

今天新增将以下 4 个文件做了 roundtrip 交付：

- `mxdrm006.dat`
- `mxdrm007.dat`
- `mxdrm008.dat`
- `mxdrm009.dat`

交付目录：

```text
deliverables/cmg_roundtrip_20260327_mxdrm6_9/
```

用户随后反馈：

- 这 4 个文件 **均无报错，能够正常运行**

这件事非常关键，因为它说明：

1. `mxdrm005` 的成功不是孤例；
2. source-faithful 并不是只对单一案例有效；
3. 即使存在较多未结构化解析块，只要原始 deck 保真且外部依赖完整，case 级 roundtrip 仍然可以稳定工作。

### 15.2 新增批量 roundtrip 交付：`flu` 目录全部文件

今天继续处理了：

```text
inputs/cmg/flu/
```

实际存在的文件为：

- `mxflu002.dat`
- `mxflu003.dat`
- `mxflu004.dat`
- `mxflu005.dat`
- `mxflu006.dat`

交付目录：

```text
deliverables/cmg_roundtrip_20260327_mxflu/
```

说明：

- 原本用户口头说的是 `fiu`，实际目录名为 `flu`
- 已按真实目录完成批量转换
- 交付目录中仅保留 roundtrip dat，不保留多余 report 目录

这一步的意义在于：

- roundtrip 验证已经从单个样例推进到目录级批处理
- 可以更真实地测试当前框架面对同类案例集时的稳定性

### 15.3 新增批量 roundtrip 交付：`frr` 目录全部文件

今天继续批量处理了：

```text
inputs/cmg/frr/
```

总计处理：

- `mxfrr001.dat` ~ `mxfrr031.dat`

交付目录：

```text
deliverables/cmg_roundtrip_20260327_mxfrr/
```

在这个目录中，今天有一个很有价值的新发现：

- `mxfrr018.dat` 中存在：

```text
FILENAMES *BINDATA-IN 'mxfrr018.cmgbin'
```

因此，今天进一步增强了运行依赖扫描能力：

- 在 `utils/cmg_case_dependencies.py` 中新增对 `BINDATA-IN` 的识别

于是：

- `mxfrr018_roundtrip.dat` 在交付时会自动配套复制
- `mxfrr018.cmgbin`

这说明今天对“有用 / 无用”的区分又向前走了一步：

- `SIPDATA-IN` 是运行依赖
- `BINDATA-IN` 也是运行依赖
- 未来凡是这类外部输入引用，都应纳入 case package 识别，而不是只盯着 dat 本体

### 15.4 新增组分模型验证：`gmflu001.dat`

今天还专门拿了一个 GEM 组分模型样例：

- `inputs/cmg/gmflu001.dat`

并生成：

```text
deliverables/cmg_roundtrip_20260327_gmflu/gmflu001_roundtrip.dat
```

随后用户使用：

- `GEM 2021.10`

对该文件进行实际运行验证，最终结果是：

- **正常读入**
- **正常进入模拟**
- **正常结束计算**
- 没有输入级错误

这件事的重要性非常高。

它说明：

1. 今天建立的 source-faithful 路线不仅对 IMEX blackoil 类案例有效；
2. 对至少一个 **GEM compositional** 案例，也已经可以实现稳定的 `CMG -> JSON -> CMG` 保真回写；
3. 当前统一 CMG 框架并不需要因为出现组分模型就立刻拆成一套完全独立解析器。

当然，也必须客观指出：

- 这并不表示当前中间层已经完整理解了 GEM 组分语义；
- 这表示的是：**当前框架已经具备组分 case 的基础保真转换能力。**

### 15.5 新增 GEM DRM 样例批量交付：`gmdrm001` ~ `gmdrm003`

在 `gmflu001` 成功后，今天继续处理了：

```text
inputs/cmg/gem_drm/
```

其中 3 个 dat 文件：

- `gmdrm001.dat`
- `gmdrm002.dat`
- `gmdrm003.dat`

已生成交付至：

```text
deliverables/cmg_roundtrip_20260327_gem_drm/
```

这一步虽然用户还未在今天回传运行结果，但它代表着：

- 今天对 GEM 方向的验证，不再只停留在单一样例 `gmflu001`
- 已开始推进到一个更小型的 GEM 样例集合

---

## 16. 今天对“解析器 / 生成器架构”形成的进一步认识

今天在 `gmflu001` 成功后，用户进一步提出了一个非常关键的架构问题：

- CMG 不同模型（如 blackoil / miscible / compositional）
- 是继续用一个解析器 / 生成器，还是每种模型单独开一套？

今天基于实际验证结果，形成了更明确的答案。

### 16.1 解析器不应当按模型彻底拆成多套独立实现

今天的结论是：

> **一个统一的 CMG 解析器框架 + 按模型分层扩展**

比“每个模型各写一套完整解析器”更合理。

原因包括：

1. 很多能力是所有 CMG 模型共用的：
   - token / 注释 / section / 外部依赖识别
   - 原始行保留
   - source-faithful roundtrip
   - 通用 grid / wells / schedule 的一部分

2. 如果每个模型都独立写一套：
   - 代码重复高
   - bug 修复会分裂
   - 同类语法行为容易不一致
   - 后期维护成本会越来越大

3. 但也不能把所有模型逻辑糊在一个超大解析器里：
   - 那样会变成巨大的 if/else 泥球

因此更合理的方向是：

- **语法层统一**
- **语义层按模型模块化**

### 16.2 生成器同理：统一框架，模型 writer 分开

今天同时也确认：

- 生成器也不应当每个模型各写一整套独立系统
- 更合理的是：

> **一个统一输出框架 + 各模型专属 writer 模块**

这样可以保证：

- source-faithful 回写能力统一
- 依赖复制、preflight、报告机制统一
- 模型专属 fluid / EOS / component 写法又能按模块扩展

### 16.3 这一天的实际结果，已经给这个架构判断提供了证据

今天这个架构判断不是纯理论，而是有实际证据支持的：

- IMEX 的 `mxdrm006~009` 批量成功
- `flu` / `frr` 目录批量完成交付
- `gmflu001` 作为 GEM 组分样例成功运行
- `gem_drm` 样例也已进入批量交付阶段

也就是说：

- 现有统一 CMG 框架不是只能服务 blackoil
- 它已经开始证明可以承接 compositional / GEM 方向
- 后续更合理的是在统一框架下继续分层增强，而不是从零另起一套

---

## 17. 今天对“source-faithful”的理解进一步收敛

经过今天后半段的更多样例验证，对 source-faithful 的理解进一步清晰了。

### 17.1 source-faithful 不是权宜之计，而是当前最稳妥的工程主线

今天之前，source-faithful 还可以被理解为一种“应急措施”或“过渡方案”；

但经过：

- `mxdrm006~009` 批量成功
- `gmflu001` GEM 成功
- `mxfrr018` 外部二进制依赖正确随交付复制

现在更合理的认识是：

> 对 `CMG -> JSON -> CMG`，尤其是面向用户真实求解器运行验证时，source-faithful 不是退而求其次，而是当前阶段最稳妥、最符合工程目标的主线方案。

### 17.2 source-faithful 解决的是“可跑”与“保真”，不是“语义全理解”

同时今天也再次提醒了一个边界：

- source-faithful 很强，但它解决的核心是：
  - 原始 deck 保真
  - 外部依赖完整
  - 用户拿去跑不容易炸

它并不自动意味着：

- 当前中间层已经具备对所有 CMG / GEM 复杂语义的自由编辑能力
- 所有 keyword 都已经被结构化理解
- 所有模型都已经可做高质量跨软件转换

因此，后续必须继续坚持一个清晰边界：

- **roundtrip 可跑能力**
- **中间层语义完备能力**

这两者要分开建设、分开验收。

---

## 18. 今日文档在晚间应补充的最终结论

如果把今天从早到晚的工作连起来看，可以得到一个比白天更完整的结论：

1. 前半段解决的是：
   - 为什么旧方法会不断在 IMEX 中出错
   - 为什么只看内部 schema 不够
   - 为什么要转向 deck / case 语义保真

2. 后半段验证的是：
   - 这套新方法不是只对一两个样例有效
   - 它已经可以支撑更多 IMEX 样例目录级批量交付
   - 它已经开始支撑 GEM 组分模型

3. 因而今天最终真正确定下来的，不只是几个 patch，而是一条架构路线：

> **统一 CMG 解析 / 生成框架 + source-faithful roundtrip 主线 + 外部依赖自动识别复制 + 模型语义分层扩展**

这会直接影响后续如何建设：

- blackoil 支持
- miscible 支持
- compositional / GEM 支持
- 以及未来真正的工程化中间层能力

---

## 19. 今日最终一句话总结（晚间修正版）

如果在今天全部工作完成后，再用一句话总结，那么更准确的表述应该是：

> 2026-03-27 这一天，项目从“尝试把 CMG dat 解析并重建成另一份 dat”正式转向了“以 deck / case 语义保真为核心的统一 CMG 框架”，并且这一路线已经在 IMEX 多个目录样例与至少一个 GEM 组分样例上证明了可行性。
