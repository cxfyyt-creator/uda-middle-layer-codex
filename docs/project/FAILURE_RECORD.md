# 转换失败与架构问题记录

> 更新时间：2026-03-31
>
> 目的：集中记录当前 Petrel/Eclipse → CMG、CMG 往返过程中出现的失败现象、直接原因、归类原因和对应的架构层问题，避免后续重复分析同一类问题。

---

## 1. 失败类型总分类

当前失败大致可分为 6 类：

### A. 属性解析/展开错误

表现：
- 孔隙度、渗透率等数组被读坏；
- 合法模型被校验成不合法；
- 常见报错是 `porosity out of range`。

典型诱因：
- `EQUALS / COPY / MULTIPLY / BOX` 一类局部赋值语义没被正确展开；
- 外部引用或区域赋值在中间层里被错误扁平化。

---

### B. 合法零值/空块被过严校验拦截

表现：
- deck 本身可能可跑，但中间层校验先失败；
- 常见于 `porosity=0.0` 的 null block / inactive block / zero porosity 示例。

典型诱因：
- 当前 schema 对 `porosity` 采用 `(0, 0.60]` 的严格约束；
- 没有区分“物理异常值”和“建模上有意义的零值块”。

---

### C. 网格类型不支持或转换不完整

表现：
- 报 `grid.di/dj/dk missing`；
- 文件里实际是 `COORD / ZCORN` 角点网格，但目标生成链按规则网格路径处理。

典型诱因：
- 当前后端更偏向 `CART + DI/DJ/DK`；
- 对 corner-point grid 的统一表达和导出能力不完整。

---

### D. 物理模型类型超出当前支持范围

表现：
- 报 `blackoil fluid requires ...`；
- 或虽然解析了文件，但生成路径按普通 blackoil 理解，导致缺关键物性。

典型诱因：
- 文件属于化学驱、tracer、API tracking、盐水等专项模型；
- 当前中间层虽能承接一部分字段，但还没形成该类模型的完整目标映射。

---

### E. 目标后端预检假设过强

表现：
- 生成前就被 preflight 拦截；
- 但原始 deck 未必真的不可运行。

典型诱因：
- 预检默认按某一类“标准黑油 + 规则网格 + 完整显式密度/PVT”的理想模型判断；
- 对示例 deck、历史 deck、派生 deck 的兼容性不足。

---

### F. 工程级信息未进入中间层

表现：
- `.dat` 能生成，但运行时仍失败；
- 典型例子是外部文件、运行时依赖、链式案例无法自动衔接。

典型诱因：
- 当前中间层更擅长描述“模型内容”，不擅长描述“文件关系”；
- 静态依赖、运行时依赖、产物依赖没有统一建模。

---

## 2. 已确认样例记录

### 2.1 CMG GEO 相关

| 样例 | 现象 | 直接原因 | 归类 |
|---|---|---|---|
| `mxgeo004.dat` | 转换链被挡 | `porosity` 中存在大量 `0.0` | B / E |
| `mxgeo006.dat` | 转换链被挡 | `porosity` 中存在大量 `0.0` | B / E |
| `mxgeo008.dat` | 下游运行依赖不稳 | deck 里引用 `mxgeo007.flxb`，实际产物是 `mxgeo007_converted.flxb` | F |
| `mxgeo010.dat` | 同类问题 | `mxgeo009.flxb` 与 `mxgeo009_converted.flxb` 不一致 | F |
| `mxgeo012.dat` | 同类问题 | `mxgeo011.flxb` 与 `mxgeo011_converted.flxb` 不一致 | F |

说明：
- `mxgeo004 / 006` 暴露的是“严格校验不等于真实可运行性”；
- `mxgeo008 / 010 / 012` 暴露的是“运行时依赖文件名与产物名不一致”。

---

### 2.2 Petrel/Eclipse 中 `a*` 开头样例

| 样例 | 现象 | 直接原因 | 归类 |
|---|---|---|---|
| `ALKALINE_ASP.DATA` | 生成失败 | 预检按 blackoil 路径判断，缺可接受的 PVT 结构；文件本身属于 `ALKALINE + SURFACT + POLYMER` 模型 | D / E |
| `API_INJ.DATA` | 生成失败 | `COORD/ZCORN` 角点网格未转好；密度未被当前链路稳定提取；含 `API/APIVD/WAPI` 语义 | C / D / E |
| `API_TRACK.DATA` | 生成失败 | `API tracking` 相关物性/语义未稳定进入目标链路；密度提取不足 | D / E |

说明：
- `ALKALINE_ASP` 不是普通黑油例子；
- `API_INJ / API_TRACK` 不是普通黑油 deck，而是带 API tracking 的专项样例。

---

### 2.3 Petrel/Eclipse 中 `b*` 开头样例

| 样例 | 现象 | 直接原因 | 归类 |
|---|---|---|---|
| `BIG3D3P.DATA` | 成功 | 当前链路可承接该类常规 blackoil/规则网格样例 | 参考成功样例 |
| `BASE_WATER.DATA` | 校验失败 | `PORO` 被错误读成异常值，出现 `1.0`、`13.0` 等不合理值；疑似 `EQUALS/COPY/MULTIPLY` 展开错误 | A / E |
| `BRILLIG.DATA` | 校验失败 | `porosity` 大量 `0.0`；同时带 `COORD/ZCORN/TRACERS/ACTNUM/COPY/MULTIPLY` | B / C / E |
| `BRILLIG_ACTIONG.DATA` | 校验失败 | 与 `BRILLIG` 同类 | B / C / E |
| `BRILLIG_HYSTER.DATA` | 校验失败 | 与 `BRILLIG` 同类，且带额外 hysteresis 相关语义 | B / C / D / E |
| `BRILLRST.DATA` | 校验失败 | 与 `BRILLIG` 同类，且有 restart/派生场景 | B / C / E / F |
| `BRINETRACER.DATA` | 生成失败 | `TRACERS + PVTWSALT + COORD/ZCORN`，当前既非规则网格也非普通 blackoil | C / D / E |

说明：
- `BIG3D3P` 当前可作为“常规路径成功基线”；
- `BASE_WATER` 暴露的是属性编辑语义展开问题；
- `BRILL*` 这一串说明角点网格、tracer、局部赋值和零值块问题是会叠加出现的。

---

## 3. 架构层问题记录

以下不是单个转换失败，而是当前架构层面已经暴露出的共性问题。

### 3.1 当前中间层更像“案例型 IR”，不是“工程型 IR”

现状：
- 擅长表达 `grid / fluid / wells / schedule`；
- 不擅长表达主文件、外部文件、运行时依赖和产物链。

影响：
- 一旦案例不是单文件，稳定性就明显下降；
- 典型就是 `dat + sip`、`FLXB-IN`、restart 链。

---

### 3.2 当前链路默认“所有关键数据应被完整内联”

现状：
- 校验和生成更偏向“所有东西都已变成结构化字段”；
- 对外部 payload、大数组、引用型数据支持不足。

影响：
- 真实工程一旦依赖外部文件，就会出现“可解析但不可迁移”；
- 大模型场景会越来越难以维护。

---

### 3.3 校验层与真实可运行性之间存在偏差

现状：
- 当前 schema/preflight 很适合挡明显错误；
- 但会误伤一部分真实可运行 deck，例如零孔隙度块、特殊派生案例。

影响：
- 容易把“架构表达不足”误判成“原始文件有问题”；
- 也会让成功率低于真实软件可接受范围。

---

### 3.4 目标生成器目前仍以“常规 blackoil + 常规网格”路径为主

现状：
- 常规样例已有一定成功率；
- 特殊物理模型、角点网格、tracer/API/salt/chemical 等仍明显薄弱。

影响：
- 当前成功样例更像“基本面验证”；
- 还不能说明工程级跨模拟器互转已进入稳定阶段。

---

## 4. 当前建议的使用方式

现阶段建议把样例分成三类使用：

1. **成功基线样例**：如 `BIG3D3P`，用于确认主链未退化；
2. **局部失败诊断样例**：如 `BASE_WATER`，用于专门定位属性展开问题；
3. **能力边界样例**：如 `ALKALINE_ASP`、`API_TRACK`、`BRINETRACER`、`BRILLIG*`，用于说明当前还不应把这些场景视为已支持。

---

## 5. 后续记录原则

以后遇到新的失败，建议按以下四列追加：

- **现象**：报错或运行行为；
- **直接原因**：当前具体卡点；
- **归类**：A~F 中哪一类；
- **是否属于架构问题**：是 parser/generator 小问题，还是工程型 IR 问题。

这样可以避免后面重复把同一类问题当成新问题分析。
