# 能力边界矩阵

> 文档文件名已简化：`MATRIX.md`

## 1. 更新记录

| 更新时间 | 更新内容 | 结论变化 |
|---|---|---|
| 2026-03-30 | 建立首版能力边界矩阵，统一状态口径、原因类型、下一步任务 | 矩阵从零散讨论变成正式文档 |
| 2026-03-31（批量转换更新） | 补充 CMG `spe/cmb/drm/flu/frr/geo` 与 Petrel 全量 `DATA` 批量结果 | 明确了当前成功面与失败面 |
| 2026-03-31 14:20:18 | 纳入 IR 升级 v1.0 结果：`ref`、`case_manifest`、preflight/generator 兼容 | `mxdrm005` 的主要缺口由“IR 表达缺失”转为“结构化生成器能力”；`mxgeo008/010/012` 的问题由“依赖无正式落点”转为“运行时装配/生成器能力” |

## 2. 口径

### 2.1 状态
- **完整成功**：结构化链路稳定走通。
- **保真成功**：能转、能回写、部分还能跑，但成功明显依赖 source-faithful。
- **部分成功**：某个关键问题已解决，但整条链路还没稳定。
- **失败**：当前不能稳定生成或稳定运行。

### 2.2 原因类型
- **格式覆盖**：解析器没真正读进去。
- **IR表达**：读到了，但 IR 没地方正式存。
- **生成器能力**：IR 里有了，但目标端还不会写、不会装配。
- **校验规则**：数据未必错，但被 schema/preflight 挡住。

## 3. 案例矩阵

| 案例 | 方向 | 当前状态 | 当前主要缺口 | 原因类型 | 最新备注 |
|---|---|---|---|---|---|
| `mxspe001/002/005/009/010` | CMG→CMG | 完整成功 | - | - | 基础黑油往返稳定 |
| `mxcmb001-004` | CMG→CMG | 保真成功 | 仍主要依赖保真回写 | - | 2026-03-31 批量 4/4 成功 |
| `mxdrm001-004,006-009` | CMG→CMG | 保真成功 | 仍主要依赖保真回写 | - | 2026-03-31 批量 8/8 成功 |
| `mxdrm005` | CMG→CMG | 保真成功 | `ref` 已进 IR，但 structured writer 还不会展开/写回 | 生成器能力 | `SIP_DATA` 已能解析成 `ref`，`case_manifest` 已能正式记录 `mxdrm005.sip` |
| `mxflu002-006` | CMG→CMG | 保真成功 | 仍主要依赖保真回写 | - | 2026-03-31 批量 5/5 成功 |
| `mxfrr001-031` | CMG→CMG | 保真成功 | 仍主要依赖保真回写 | - | 2026-03-31 批量 31/31 成功 |
| `mxnwp001-007` | CMG→CMG | 保真成功 | 仍主要依赖保真回写 | - | 用户已反馈运行成功 |
| `mxhrw001-008` | CMG→CMG | 保真成功 | 仍主要依赖保真回写 | - | 用户已反馈运行成功 |
| `mxgeo001-007,009,011` | CMG→CMG | 保真成功 | 仍主要依赖保真回写 | - | 2026-03-31 批量成功 |
| `mxgeo004/006` | CMG→CMG | 保真成功但结构化不稳 | null block / 零孔隙度块校验仍偏硬 | 校验规则 | active/null 语义仍未正式打通 |
| `mxgeo008/010/012` | CMG→CMG | 失败 | `FLXB-IN` 依赖虽已进入 `case_manifest`，但运行时装配仍未彻底工程化 | 生成器能力 | 问题已从“IR 无法表达依赖”推进到“生成器/装配层未完全解决” |
| `SPE1_ODEHIMPES/SPE1_ODEHIMPLI/SPE2_CHAP/SPE2_CHAPLOAD/SPE2_CHAPRST/SPE5_MISCIBLE/SPE6_FRAC/SPE9` | Petrel/Eclipse→CMG | 完整成功 | - | - | 当前基础成功面 |
| `BIG3D3P` | Petrel/Eclipse→CMG | 保真成功 | `ACTNUM` 等语义尚未完全结构化 | 格式覆盖 | 能跑，但还不是完全工程化支持 |
| `BASE_WATER` | Petrel/Eclipse→CMG | 部分成功 | `DXV/DYV`、`GRAVITY`、`PVDO+PVDG` 链路未补齐 | 格式覆盖 | `EQUALS/COPY/MULTIPLY` 已修，问题已缩小 |
| `ALKALINE_ASP` | Petrel/Eclipse→CMG | 失败 | 化学模型目标链路未建立 | 生成器能力 | 非简单补字段问题 |
| `API_INJ` | Petrel/Eclipse→CMG | 失败 | `COORD/ZCORN` corner-point 路径未建立 | 格式覆盖 | 同时伴随 API 相关语义缺口 |
| `API_TRACK` | Petrel/Eclipse→CMG | 失败 | API tracking 目标语义未建立 | 生成器能力 | 不是短期小修可解 |
| `BRILLIG/BRILLIG_ACTIONG/BRILLIG_HYSTER/BRILLRST` | Petrel/Eclipse→CMG | 失败 | `COORD/ZCORN` + active/null 语义均未稳定 | 格式覆盖 | 其中还夹杂校验层误杀问题 |
| `BRINETRACER` | Petrel/Eclipse→CMG | 失败 | corner-point + tracer/salt 复合语义未建立 | 生成器能力 | 属于后阶段任务 |

## 4. 当前最重要的能力边界判断

1. **链路可以走通**这件事已经被证明，尤其是 CMG 往返与一批 Petrel/Eclipse→CMG 基础案例。
2. **当前系统仍主要是案例型能力，不是工程型能力**。原因不是不能转，而是工程依赖、外部数据引用、运行时装配还没完全工程化。
3. **IR 升级 v1.0 已经迈出关键一步**：
   - `ref` 已存在，说明“值来自外部文件”终于有正式位置；
   - `case_manifest` 已存在，说明“这个案例依赖哪些文件”终于有正式位置；
   - 但这一步主要解决的是**能表达**，还没完全解决**能结构化生成**。
4. 因此，当前最真实的表述应当是：**系统已从“IR 表达缺失”推进到“生成器能力缺口更突出”的阶段。**

## 5. 下一步任务—影响案例—预期收益

| 任务 | 直接影响案例 | 预期收益 |
|---|---|---|
| 完成 `ref` 的结构化写回/展开 | `mxdrm005` | 从“保真成功”推进到“完整成功” |
| 完成 `FLXB-IN` 运行时装配工程化 | `mxgeo008/010/012` | 从“失败”推进到“可稳定运行” |
| 校验器拆层 + active/null cell 语义 | `mxgeo004/006`、`BIG3D3P`、`BRILLIG*` | 失败原因会更清晰，null block 不再被误杀 |
| 补齐 `DXV/DYV`、`GRAVITY`、`PVDO+PVDG` | `BASE_WATER` | 从“部分成功”继续推向“完整成功” |
| 建立 `COORD/ZCORN` 正式路径 | `API_INJ`、`BRILLIG*`、`BRINETRACER` | 打开当前最硬的一条能力边界 |
| 在 corner-point 基础上补 tracer/API/salt/chemical | `API_TRACK`、`BRINETRACER`、`ALKALINE_ASP` | 进入后续高级物理支持阶段 |

## 6. 当前优先级判断

建议顺序不变，但现在更清楚了：
1. **先做 `ref` 的结构化生成**：因为 IR 端已经到位，最短路径就是把 `mxdrm005` 真正推过线。
2. **再做 `FLXB-IN` 装配工程化**：因为 `case_manifest` 已经到位，剩下是生成器/工程组装问题。
3. **然后做校验器拆层 + active/null**：这样后面每个新失败都更容易定位。
4. **之后再打 `BASE_WATER` 和 `COORD/ZCORN`**：一个是近收益，一个是硬边界。
