# 2026-03-23 工作总结与对话纪要

本文档用于记录 2026-03-23 这一天围绕 UDA Middle Layer 的讨论、问题定位、代码修改、验证结果和待继续事项，方便后续继续沟通时快速恢复上下文。

## 1. 今天的对话主线

今天的核心主线有两条。第一条是你最早提出的中间层问题：`modifier`、PVT 表达角色、来源软件写法提示与通用物理语义是否混淆。第二条是更实际的转换问题：Petrel/Eclipse 文件转成 CMG dat 后为什么经常报错，如何避免“针对单个 deck 打补丁”，而改成“修一类问题”。

在讨论中，你明确给出了几个重要约束：一，不要把 modifier 问题说得过重，真正的问题是 Petrel 来源的数据也被打上了 CMG 风格写法提示；二，`pvto/pvdg/pvt_table` 三套并列在你的项目里是合理的，不应为了架构整洁而强行合并；三，你希望做的是通用修正，不是 SPE9 个例补丁；四，最后你会用 SPE9 做验证，所以所有修复必须尽量泛化。

后续实际工作中，主线从“讨论架构”转到了“做出可运行 dat 文件”，并逐步扩展到批量处理 `inputs/petrel/SPE*.DATA`、修复 parser/business rules/generator 关键逻辑、实际调用本机 CMG IMEX 验证结果。

## 2. 最开始的问题在哪里

今天定位下来的最初问题主要有四类。第一类是中间层表达不够干净：值的物理意义、分布方式、来源软件写法提示和目标后端偏好混在一起，导致中间层不够中立。第二类是 parser 对 deck 结构理解不够：`LOAD/RESTART`、关键字同行尾部元数据、带空格的 `EQUALS` 字段名、井角色由多个关键字共同决定等情况处理不稳。第三类是业务语义映射错误：最典型的是 Eclipse/Petrel 的 `SGOF` 不能直接当作 CMG 的 `SLT`。第四类是复杂表结构被读坏：多套 `SWFN/SGFN/SOF3` 表以前会被扁平化混成一张表，导致生成的相渗表逻辑错误。

## 3. 今天做过的主要工作

### 3.1 中间层与表达语义整理

为了让中间层更像“通用语义层”，而不是某个目标软件的影子，今天继续沿用并完善了值语义与 PVT 角色相关逻辑。已经在本项目中引入和使用的辅助模块包括：

- `utils/value_semantics.py`
- `utils/pvt_metadata.py`
- `utils/confidence_checks.py`
- `utils/target_preflight.py`

这些逻辑的目的不是推翻现有字段，而是把“这个值是什么”和“这个值在某软件中怎么写”尽量分开。比如 `pvto_table`、`pvdg_table`、`pvt_table` 会保留并列存在，但会尽量标明来源、推导关系和后端偏好。

### 3.2 SPE9：修复 `SGOF -> SLT` 语义错误

这是今天第一个真正落地的大修复。用户实际拿 `SPE9_test_converted.dat` 去跑 CMG IMEX，报出一系列 rockfluid/relperm 错误，包括 `Krog at Irreducible Liquid Saturation is not zero`、`Krg at Connate Gas Saturation is not zero`、`max Krow differs from max Krog` 等。经过检查，根因不是“数值缺了”，而是 `business_rules.py` 里原来把 Eclipse/Petrel 的 `SGOF` 过于直接地用于生成 CMG 的 `SLT`。这一点在物理含义上是错误的。

因此在 `business_rules.py` 中加入了 `_sgof_to_slt(...)`，并重写了 `merge_rockfluid_tables(...)` 的优先级，让 `SGOF` 不再被直接冒充 `SLT`，而是经过明确的语义转换后再用于 CMG rockfluid 输出。这一步不是 SPE9 专属补丁，而是解决“Eclipse/Petrel 相渗表语义到 CMG 相渗表语义映射错误”这一类问题。

### 3.3 批量检查 Petrel SPE 文件，定位共性问题

后续不是停在 SPE9，而是批量检查了 `inputs/petrel/SPE*.DATA`。在这个过程中发现：

- `SPE2_CHAPLOAD.DATA` 是 `LOAD/RESTART` 覆盖型 deck，不是完整模型。
- `SPE2_CHAPRST.DATA` 的井角色曾被错误推断。
- `SPE5_MISCIBLE.DATA` 中有 `WAT` 这类别名，需要归一化到 `WATER`。
- `SPE6_FRAC.DATA` 中存在关键字同行尾部元数据、`EQUALS` 带空格字段名、多套 rockfluid 表等问题。

### 3.4 强化 Petrel parser，解决“文件没读对”的一整类问题

今天对 `parsers/petrel_parser.py` 做了大幅增强，核心修改包括：

1. 支持 `LOAD` / `RESTART`。新增 `_parse_load`、`_parse_restart`，可先解析基础 deck，再叠加当前 deck 的变更。
2. 支持时间继承。新增 `_time_checkpoints` 跟踪，`RESTART` 文件可以从基础模型的时间点接续。
3. 修复井角色误判。`WELSPECS` 不再单独决定生产井/注入井，最终角色由 `WCONPROD` / `WCONINJE` 决定。
4. 增加流体别名归一化。引入 `_normalize_phase_or_fluid`，统一 `WAT -> WATER`、`WTR -> WATER`、`SOLV -> SOLVENT`。
5. 让多个解析函数跳过关键字同行尾部元数据。修复了 `PVTW/ROCK/DENSITY/PVTO/PVDG/COMPDAT/WCONPROD/WCONINJE/WELTARG` 等场景。
6. 修复 `EQUALS` 中字段名带空格的问题，像 `'DX      '` 可以正确识别为 `DX`。
7. 支持表格按“多套表”读取。新增 `_read_table_sets(...)`，通用 `_handle_table(...)` 不再把多套 `SWFN/SGFN/SOF3` 扁平拼接为一套。

### 3.5 SPE2_CHAPLOAD / SPE2_CHAPRST：修复 deck 结构关系理解错误

在修复 `LOAD/RESTART` 支持和井角色误判逻辑之后，`SPE2_CHAPLOAD.DATA` 和 `SPE2_CHAPRST.DATA` 不再被当作“残缺模型”或“井资料错误模型”。它们现在能正确继承基础 deck，并按后续 schedule 关键字得到合理的井角色与时间线，最终成功导出并经 CMG 验证通过。

### 3.6 SPE5_MISCIBLE：修复别名归一化问题

`SPE5_MISCIBLE.DATA` 中的注入流体存在 `WAT` 写法。以前 preflight 会把这种值判为不受支持的 `inj_fluid`。加入流体别名归一化后，`WAT` 能正确转成 `WATER`，该类问题得到解决。后续 `SPE5_MISCIBLE` 也已生成并成功运行。

### 3.7 SPE6_FRAC：修复“多套 rockfluid 表混成一套”的通病

这是今天第二个关键大修复，也是最能体现“不要打个例补丁”的部分。`SPE6_FRAC.DATA` 中有：

- `SGFN 2 TABLES`
- `SWFN 2 TABLES`
- `SOF3` 中也有多段表

旧逻辑会把这些数据扁平拼成一张表，导致生成的 `SWT/SLT` 不单调、端点错误、物理关系错乱，CMG 报输入错误。今天的解决方式分两步：

第一步，在 `parsers/petrel_parser.py` 中保留多套表，不再混表；第二步，在 `business_rules.py` 中新增多套表选择逻辑。具体增加或重构的函数包括：

- `_sanitize_monotonic_prefix(...)`
- `_merge_rockfluid_single(...)`
- `_table_set_count(...)`
- `_table_at_index(...)`
- `_build_rockfluid_variant(...)`
- `_score_monotonic_table(...)`
- `merge_rockfluid_tables(...)`

新的策略不是“再混一次”，而是“先保留多套，再根据当前 CMG backend 的要求选择最适合导出的一套”。这解决的是一整类“多套 rockfluid 表被错误扁平化”的问题，不是 SPE6 专属补丁。

## 4. 今天修改过的主要文件

今天对以下文件有重点修改或在对话中反复依赖：

- `parsers/petrel_parser.py`
- `business_rules.py`
- `rules/keyword_registry.yaml`
- `transformers/uda_transformer.py`
- `parsers/cmg_parser.py`（今天引用并依赖既有改进成果）
- `utils/value_semantics.py`
- `utils/pvt_metadata.py`
- `utils/confidence_checks.py`
- `utils/target_preflight.py`

其中今天后半段直接落地且最关键的代码修改主要集中在前三个文件：`parsers/petrel_parser.py`、`business_rules.py`、`rules/keyword_registry.yaml`。

## 5. 今天实际验证过的结果

今天不仅做了代码修改，还实际调用了本机 CMG IMEX 进行验证。以下文件已经完成过实际运行验证并达到“正常终止”：

- `outputs/cmg/SPE9_converted.dat`
- `outputs/cmg/SPE2_CHAPLOAD_converted.dat`
- `outputs/cmg/SPE2_CHAPRST_converted.dat`
- `outputs/cmg/SPE5_MISCIBLE_converted.dat`
- `outputs/cmg/SPE6_FRAC_converted.dat`

其中 `SPE6_FRAC_converted.dat` 是今天的关键突破，输入阶段已经达到 `0 Error messages`，并 `Normal Termination`。

## 6. 今天生成/交付给用户的重要文件

### 6.1 Petrel -> CMG 批量转换成果

以下文件在今天被重新生成或确认可用：

- `outputs/cmg/SPE1_ODEHIMPES_converted.dat`
- `outputs/cmg/SPE1_ODEHIMPLI_converted.dat`
- `outputs/cmg/SPE2_CHAP_converted.dat`
- `outputs/cmg/SPE2_CHAPLOAD_converted.dat`
- `outputs/cmg/SPE2_CHAPRST_converted.dat`
- `outputs/cmg/SPE5_MISCIBLE_converted.dat`
- `outputs/cmg/SPE6_FRAC_converted.dat`
- `outputs/cmg/SPE9_converted.dat`

### 6.2 今天最后的 roundtrip 测试文件

用户要求“随机挑几个 dat 文件，转成 json 再转回 dat 供后续跑”。实际可稳定完成 roundtrip 的 3 个文件为：

- `outputs/json/roundtrip_pick/SPE2_CHAP_converted_parsed.json`
- `outputs/json/roundtrip_pick/SPE5_MISCIBLE_converted_parsed.json`
- `outputs/json/roundtrip_pick/SPE9_converted_parsed.json`

对应生成的 dat 文件为：

- `outputs/cmg/roundtrip_pick/SPE2_CHAP_converted_converted.dat`
- `outputs/cmg/roundtrip_pick/SPE5_MISCIBLE_converted_converted.dat`
- `outputs/cmg/roundtrip_pick/SPE9_converted_converted.dat`

这 3 个文件的来源链路分别是：

- `outputs/cmg/SPE2_CHAP_converted.dat -> outputs/json/roundtrip_pick/SPE2_CHAP_converted_parsed.json -> outputs/cmg/roundtrip_pick/SPE2_CHAP_converted_converted.dat`
- `outputs/cmg/SPE5_MISCIBLE_converted.dat -> outputs/json/roundtrip_pick/SPE5_MISCIBLE_converted_parsed.json -> outputs/cmg/roundtrip_pick/SPE5_MISCIBLE_converted_converted.dat`
- `outputs/cmg/SPE9_converted.dat -> outputs/json/roundtrip_pick/SPE9_converted_parsed.json -> outputs/cmg/roundtrip_pick/SPE9_converted_converted.dat`

另外，今天还尝试了从 `inputs/cmg/` 中随机抽原始 dat 做 roundtrip，抽中了：

- `mxspe005.dat`
- `mxspe001.dat`
- `mxspe010.dat`

但当前 `parse-cmg -> generate-cmg` 链路对这组文件并不是全部稳定支持，因此改为挑选当前已知可稳定 roundtrip 的 3 个 dat 给用户做测试。这也说明：CMG parser/generator 的 roundtrip 能力仍有继续完善空间。

## 7. 今天解决掉的问题清单

今天已经明确解决或显著推进的问题包括：

1. `SGOF` 被错误当成 `SLT` 的语义映射问题。
2. `LOAD/RESTART` deck 不能继承基础模型的问题。
3. 时间继承与 restart 时间点衔接问题。
4. `WELSPECS` 过早决定井角色导致 producer/injector 误判的问题。
5. `WAT/WTR/SOLV` 这类流体别名不统一的问题。
6. 关键字同行尾部元数据（如 `FIELD 14 JUN 90`）干扰解析的问题。
7. `EQUALS` 中带填充空格的关键字识别失败问题。
8. 多套 `SWFN/SGFN/SOF3` 表被扁平化混成一套的问题。
9. `SPE6_FRAC` 类复杂 rockfluid 结构无法稳定导出并运行的问题。

## 8. 当前还未完全解决/后续可继续推进的方向

虽然今天已经有明显突破，但仍存在后续可继续推进的方向：

1. `inputs/cmg/` 原始 dat 的 parser roundtrip 能力还不完整，部分文件在 `parse-cmg -> generate-cmg` 链路上仍会因未完全支持的关键字或 rockfluid/PVT 表达而被 preflight 阻断。
2. dual-porosity / fracture / 多区域 rockfluid 现在已经能在代表案例上“稳定导出并可跑”，但从更严格的语义忠实性角度看，后续仍可继续完善“多套表 + 区域映射”的完整表达。
3. 用户后续提到的组分模型 PVT 公式问题，今天没有深入展开，仍属于后续重要方向。

## 9. 明天继续沟通时建议优先参考的文件

如果明天继续推进，建议优先参考这些文件：

- `docs/20260323_WORK_SUMMARY.md`（本文档）
- `parsers/petrel_parser.py`
- `business_rules.py`
- `rules/keyword_registry.yaml`
- `outputs/cmg/SPE9_converted.dat`
- `outputs/cmg/SPE6_FRAC_converted.dat`
- `outputs/cmg/roundtrip_pick/` 下的 3 个 roundtrip dat

## 10. 今天对话中形成的共识

今天的共识非常重要，后续工作应继续保持：

1. 不为个例打补丁，优先修一类问题。
2. 中间层不应被某个目标后端绑死，但也不应为了“看起来统一”而强行合并掉有价值的来源表达。
3. 真实验证优先，尤其是以 CMG IMEX 实际运行结果为准。
4. 遇到复杂案例时，先保证结构不被读错，再做物理语义映射，最后再考虑更完整的目标表达。

