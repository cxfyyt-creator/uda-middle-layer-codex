# 归档说明

> 本文件为项目早期全景文档归档版本，保留用于追踪方案演进与历史决策。
>
> 当前不再作为现行项目文档维护，请优先参考 `docs/project/PROJECT_CONTEXT.md`。
>
> 归档时间：2026-03-18

# Universal Data Adapter — Middle Layer (UDA)
# 通用数据适配中间层 · 项目全景文档

> **本文档用途**：供 AI 编程助手（Codex / Claude）阅读，以完整理解项目背景、架构、已完成代码、
> 规则文件含义、开发规范和当前任务，无需重复解释上下文。
>
> **最后更新**：2025 年 3 月（第二周末）

---

## 0. 项目一句话描述

构建一套**中间层转换系统**，实现 **CMG IMEX**（.dat）与 **Petrel Eclipse**（.DATA）
两种油藏模拟软件输入文件的**双向自动转换**，核心是一套与代码解耦的 YAML 规则文件 +
统一 JSON 中间层。

```
CMG .dat  ──→  Parser  ──→  通用 JSON  ──→  Generator  ──→  Petrel .DATA
Petrel .DATA ─→  Parser  ──→  通用 JSON  ──→  Generator  ──→  CMG .dat
```

---

## 1. 项目目录结构（最新版）

```
uda_middle_layer/
│
├── inputs/                        # ★ 原始输入文件（不可修改）
│   ├── cmg/                       #   CMG .dat 原始文件
│   │   ├── mxspe001.dat           #   SPE1  10×10×3  气驱基础案例
│   │   ├── mxspe002.dat           #   SPE2  10×1×15  径向坐标锥进
│   │   ├── mxspe005.dat           #   SPE5  7×7×3    WAG混相注入
│   │   ├── mxspe009.dat           #   SPE9  24×25×15 3D非均质
│   │   └── mxspe010.dat           #   SPE10 100×1×20 细网格非均质
│   └── petrel/                    #   Petrel .DATA 原始文件（待获取）
│
├── outputs/                       # ★ 转换生成的文件（程序输出，可重新生成）
│   ├── json/                      #   Parser 输出的中间层 JSON
│   │   ├── mxspe001_parsed.json
│   │   ├── mxspe002_parsed.json
│   │   └── ...
│   ├── cmg/                       #   Generator 输出的 CMG .dat 文件
│   │   ├── mxspe001_roundtrip.dat #   往返测试：JSON → CMG
│   │   └── ...
│   └── petrel/                    #   Generator 输出的 Petrel .DATA 文件
│       ├── mxspe001_converted.DATA
│       └── ...
│
├── rules/                         # ★ YAML 规则文件（核心"法典"，人工维护）
│   ├── parameters.yaml            #   参数映射规则（CMG关键字 ↔ Petrel关键字）
│   ├── units.yaml                 #   单位换算规则（FIELD ↔ METRIC）
│   └── file_structure.yaml        #   文件结构描述（注释符、关键字前缀、区块顺序）
│
├── docs/                          # ★ 解析文档（供 Codex/开发者阅读）
│   ├── PROJECT_CONTEXT.md         #   ← 本文件，项目全景
│   ├── CMG_FORMAT_GUIDE.md        #   CMG .dat 格式详解（基于SPE1-10）
│   ├── PETREL_FORMAT_GUIDE.md     #   Petrel .DATA 格式详解（待写）
│   ├── JSON_SCHEMA.md             #   通用 JSON 中间层格式说明
│   └── UNIT_CONVERSION.md         #   单位换算速查表
│
├── parsers/
│   ├── cmg_parser.py              #   ✅ 已完成 v2，CMG .dat → JSON dict
│   └── petrel_parser.py           #   🔲 待开发，Petrel .DATA → JSON dict
│
├── generators/
│   ├── cmg_generator.py           #   ✅ 已完成 v2，JSON dict → CMG .dat
│   └── petrel_generator.py        #   🔲 待开发，JSON dict → Petrel .DATA
│
├── validators/
│   └── schema.py                  #   🔲 待开发，Pydantic 数据校验
│
├── utils/
│   └── unit_converter.py          #   🔲 待开发，从 units.yaml 读取换算规则
│
├── tests/
│   ├── test_cmg_roundtrip.py      #   往返测试：CMG→JSON→CMG
│   ├── test_cmg_to_petrel.py      #   正向测试：CMG→JSON→Petrel
│   └── test_petrel_to_cmg.py      #   反向测试：Petrel→JSON→CMG
│
└── main.py                        #   命令行入口
```

### 1.1 目录设计原则

| 目录 | 性质 | 说明 |
|------|------|------|
| `inputs/` | 只读 | 原始文件，永远不被程序修改 |
| `outputs/` | 可重新生成 | 所有程序输出，可随时删除重跑 |
| `rules/` | 人工维护 | 不含代码逻辑，新增软件只加文件 |
| `docs/` | 供人/AI 阅读 | 不含可执行代码，纯文档 |
| `parsers/` | 代码 | 读取 → JSON |
| `generators/` | 代码 | JSON → 写出 |

---

## 2. 核心设计原则

1. **规则与代码分离**：所有参数映射、单位换算、文件结构规则存储在 `rules/` YAML 文件中，
   代码只读取规则并执行，新增软件支持只需新增 YAML，不修改 Python 代码。

2. **中间层保留原始单位**：Parser 输出的 JSON 保留原始文件的单位（如 CMG FIELD 单位 psia/ft），
   Generator 在生成目标文件时才做单位换算。

3. **modifier 保留**：Parser 解析 CMG 数组时，记录原始写法修饰词（CON/KVAR/ALL 等）到
   `modifier` 字段，Generator 还原时使用，保证往返一致性。

4. **可追溯性**：每个 JSON 字段记录 `source`（来源行号）和 `confidence`（置信度），
   便于排查解析错误。

5. **确定性优先**：中间层 JSON 经过 Pydantic 验证（待实现），不合法数据在转换前被拦截。

---

## 3. 通用 JSON 中间层格式（完整规范）

Parser 的输出 / Generator 的输入，遵循以下结构：

### 3.1 顶层结构

```json
{
  "meta":      { ... },   // 文件元信息
  "grid":      { ... },   // 网格几何
  "reservoir": { ... },   // 储层岩石属性
  "fluid":     { ... },   // 流体 PVT
  "rockfluid": { ... },   // 相对渗透率
  "initial":   { ... },   // 初始条件
  "numerical": { ... },   // 数值控制
  "wells":     [ ... ]    // 井列表（数组）
}
```

### 3.2 meta 字段

```json
{
  "meta": {
    "source_software": "cmg_imex",        // 来源软件标识
    "source_file": "mxspe001.dat",        // 原始文件名
    "unit_system": "field",               // 单位制：field | metric | si | lab
    "conversion_timestamp": "2025-03-09T10:00:00",
    "start_date": "1986-04-22",           // 模拟起始日期（来自 *DATE）
    "dtwell": 1.0                         // 初始时间步长（天，来自 *DTWELL）
  }
}
```

### 3.3 值的三种标准结构

所有数值字段必须是以下三种结构之一：

**scalar（单值）**
```json
{
  "type": "scalar",
  "value": 4800.0,
  "unit": "psia",
  "confidence": 0.99,
  "source": "initial *REFPRES 第42行",
  "modifier": "CON"          // 可选，记录原始写法（CON/KVAR等）
}
```

**array（数组）**
```json
{
  "type": "array",
  "values": [200.0, 50.0, 500.0],
  "unit": "md",
  "grid_order": "IJK",
  "confidence": 0.99,
  "source": "reservoir *PERMI 第28行",
  "modifier": "KVAR"         // 记录原始修饰词
}
```

**table（表格）**
```json
{
  "type": "table",
  "columns": ["sw", "krw", "krow"],
  "rows": [[0.12, 0.0, 1.0], [0.82, 0.0, 0.0]],
  "confidence": 0.99,
  "source": "rockfluid *SWT 第65行"
}
```

### 3.4 完整字段清单

#### grid（网格几何）
| 字段 | 类型 | 单位（FIELD） | 说明 |
|------|------|------|------|
| `grid_type` | str | — | CART / RADIAL |
| `ni`, `nj`, `nk` | int | — | 三方向网格数 |
| `di` | scalar/array | ft | I方向尺寸 |
| `dj` | scalar/array | ft | J方向尺寸 |
| `dk` | scalar/array | ft | K方向层厚 |
| `depth_ref_block` | scalar + i/j/k | ft | 参考块埋深 |

#### reservoir（储层属性）
| 字段 | 类型 | 单位 | 说明 |
|------|------|------|------|
| `porosity` | scalar/array | fraction | 孔隙度 |
| `perm_i` | scalar/array | md | I方向渗透率 |
| `perm_j` | scalar/array | md | J方向渗透率 |
| `perm_k` | scalar/array | md | K方向渗透率（垂向）|
| `rock_compressibility` | scalar | 1/psi | 岩石压缩系数 |
| `rock_ref_pressure` | scalar | psia | 压缩系数参考压力 |

#### fluid（流体PVT）
| 字段 | 类型 | 单位 | 说明 |
|------|------|------|------|
| `pvt_table` | table | 见列说明 | 黑油PVT表（6列：p/rs/bo/eg/viso/visg）|
| `oil_density` | scalar | lb/ft³ | 原油地面密度 |
| `gas_density` | scalar | lb/ft³ | 天然气地面密度 |
| `water_density` | scalar | lb/ft³ | 地层水地面密度 |
| `water_fvf` | scalar | RB/STB | 水相体积系数 BWI |
| `water_compressibility` | scalar | 1/psi | 水相压缩系数 CW |
| `water_ref_pressure` | scalar | psia | 水相参考压力 REFPW |
| `water_viscosity` | scalar | cp | 水相粘度 VWI |
| `water_viscosity_coeff` | scalar | 1/psi | 水粘度压力系数 CVW |
| `oil_compressibility` | scalar | 1/psi | 欠饱和油压缩系数 CO |
| `oil_viscosity_coeff` | scalar | 1/psi | 油粘度压力系数 CVO |

#### rockfluid（相对渗透率）
| 字段 | 类型 | 列名 | 说明 |
|------|------|------|------|
| `swt_table` | table | sw/krw/krow[/pcow] | 水油相渗，3或4列 |
| `slt_table` | table | sl/krg/krog[/pcog] | 液气相渗，3或4列 |

#### initial（初始条件）
| 字段 | 类型 | 单位 | 说明 |
|------|------|------|------|
| `ref_depth` | scalar | ft | 参考深度 REFDEPTH |
| `ref_pressure` | scalar | psia | 参考点压力 REFPRES |
| `woc_depth` | scalar | ft | 水油接触面深度 DWOC |
| `goc_depth` | scalar | ft | 气油接触面深度 DGOC |
| `bubble_point_pressure` | scalar/array | psia | 泡点压力 PB |
| `pressure` | scalar/array | psia | 初始地层压力 PRES |
| `water_saturation` | scalar/array | fraction | 初始含水饱和度 SW |
| `oil_saturation` | scalar/array | fraction | 初始含油饱和度 SO |
| `gas_saturation` | scalar/array | fraction | 初始含气饱和度 SG |

#### numerical（数值控制）
| 字段 | 类型 | 单位 | 说明 |
|------|------|------|------|
| `max_timestep` | scalar | day | 最大时间步 DTMAX |
| `max_steps` | scalar | — | 最大步数 MAXSTEPS |

#### wells（井列表，每个元素结构）
```json
{
  "well_name": "Injector",
  "well_type": "INJECTOR",       // INJECTOR | PRODUCER
  "well_index": 1,               // CMG 井编号
  "bhp_max": 20000.0,            // psia，*OPERATE *MAX *BHP
  "bhp_min": 1000.0,             // psia，*OPERATE *MIN *BHP
  "rate_max": 100000000.0,       // STB/d 或 Mscf/d，*OPERATE *MAX *STO/*STG
  "rate_min": null,
  "well_radius": 0.25,           // ft，*GEOMETRY
  "geofac": 0.34,                // 几何系数
  "wfrac": 1.0,                  // 流动效率
  "skin": 0.0,                   // 表皮系数
  "perforations": [
    {"i": 1, "j": 1, "k": 3, "wi": 100000.0, "perf_type": "PERF"},
    {"i": 1, "j": 1, "k": 8, "wi": 1.0, "perf_type": "PERFV"}
  ],
  "alter_schedule": [
    {"time": 10.0, "rate": 100.0},
    {"time": 50.0, "rate": 1000.0}
  ],
  "source": "WELL 第xxx行"
}
```

---

## 4. 已完成代码详解

### 4.1 `parsers/cmg_parser.py`（v2，约 450 行）

**功能**：将 CMG IMEX .dat 文件解析为上述通用 JSON 字典。

**工作原理**：词元流（Token Stream）解析，而非逐行解析。
1. 读取文件，去注释（`**` 后内容），拆分为带行号的词元列表。
2. 游标（`pos`）从头扫描，遇到 `*` 关键字调用对应解析方法。
3. 每个方法向前读取所需词元，遇下一个 `*` 关键字停止。

**关键工具函数**：
```python
_strip_comments(line)   # 去除 ** 及其后内容
_is_kw(tok)             # 判断是否为 *关键字（非 **）
_to_float(s)            # 转浮点，支持 Fortran 科学计数法（d/D）
_expand_repeat(tok)     # 展开 N*value，如 "2*8.0" → [8.0, 8.0]
_scalar(v, unit, src)   # 构造 scalar 结构
_array(vs, unit, src)   # 构造 array 结构
_table(cols, rows, src) # 构造 table 结构
```

**CMGParser 类核心方法**：
```python
_load_tokens()          # 读文件→词元列表（带行号）
_peek(off=0)            # 查看但不移动游标
_next()                 # 取词元并移动游标
_read_floats()          # 连续读浮点数，支持N*value，遇*关键字停止

_scalar_prop(block, key, unit, R)  # 解析单值属性（支持同行/下行两种写法）
_array_prop(block, key, unit, R)   # 解析数组，识别并保留 *CON/*KVAR/*IVAR/*ALL

_parse_grid(R)          # *GRID → 网格类型 + ni/nj/nk
_parse_dim(key, unit, R)# *DI/*DJ/*DK → 带modifier的网格尺寸
_parse_depth(R)         # *DEPTH i j k value → 参考块坐标+深度
_parse_pvt(R)           # *PVT → 6列黑油表
_parse_density(R)       # *DENSITY *OIL/GAS/WATER value
_parse_rpt_table(kw, R) # *SWT/*SLT → 自动检测3或4列相渗表
_parse_well(R)          # *WELL → 初始化井字典
_parse_operate(R)       # *OPERATE → 更新井约束
_parse_perf(R, kw)      # *PERF（i,j,k,wi）和 *PERFV（k,wi，支持k1:k2范围）
_parse_geometry(R)      # *GEOMETRY → 井半径/几何系数/表皮
_parse_alter(R)         # *ALTER → 记录时间-速率变化
```

**主循环关键字映射**（`parse()` 方法中的 if/elif 链）：
```
*INUNIT     → meta.unit_system
*GRID       → _parse_grid()
*DI/DJ/DK   → _parse_dim()
*DEPTH      → _parse_depth()
*POR        → _array_prop("reservoir","porosity","fraction")
*PERMI/J/K  → _array_prop("reservoir","perm_i/j/k","md")
*CPOR       → _scalar_prop("reservoir","rock_compressibility","1/psi")
*PRPOR      → _scalar_prop("reservoir","rock_ref_pressure","psia")
*PVT        → _parse_pvt()
*DENSITY    → _parse_density()
*BWI/CW/REFPW/VWI/CO/CVO/CVW → _scalar_prop("fluid",...)
*SWT/*SLT   → _parse_rpt_table()
*REFDEPTH/REFPRES/DWOC/DGOC → _scalar_prop("initial",...)
*PB/PRES/SW/SO/SG → _array_prop("initial",...)
*DTMAX      → _scalar_prop("numerical","max_timestep","day")
*MAXSTEPS   → _scalar_prop("numerical","max_steps","–")
*DATE       → meta.start_date
*DTWELL     → meta.dtwell
*TIME       → 更新内部 _current_time 状态
*ALTER      → _parse_alter()
*WELL       → _parse_well()
*INJECTOR   → wells[-1].well_type = "INJECTOR"
*PRODUCER   → wells[-1].well_type = "PRODUCER"
*OPERATE    → _parse_operate()
*PERF       → _parse_perf(R, "*PERF")
*PERFV      → _parse_perf(R, "*PERFV")
*GEOMETRY   → _parse_geometry()
其余        → 静默跳过
```

**调用方式**：
```python
from parsers.cmg_parser import parse_cmg

data = parse_cmg("inputs/cmg/mxspe001.dat")
# 或同时写出 JSON
data = parse_cmg("inputs/cmg/mxspe001.dat", "outputs/json/mxspe001_parsed.json")
```

**已知局限**：
- `*KDIR *DOWN` 被静默跳过（不影响数值提取，但 K 层顺序信息丢失）
- `*PERMJ *EQUALSI` 被静默跳过（perm_j 会缺失）
- `*IJK` 范围格式（`*POR *IJK 1:5 1:10 1:3 0.25`）尚未支持
- `*GROUP` / `*ATTACHTO` 被静默跳过

---

### 4.2 `generators/cmg_generator.py`（v2，约 230 行）

**功能**：将通用 JSON 字典还原为 CMG IMEX .dat 文件。

**格式化工具**：
```python
_fmt(v)    # 数值格式化：整数→str，普通小数→g格式，大/小值→.6E
_vals(obj) # 从 JSON 对象提取值：scalar→[value]，array→values
```

**CMGGenerator 类方法**：
```python
_write_array(kw, obj)   # 核心：根据 modifier 还原 *CON/*KVAR/*ALL 等写法
_gen_io()               # 生成文件头 + *INUNIT
_gen_grid()             # 生成 *GRID *DI *DJ *DK *DEPTH
_gen_reservoir()        # 生成 *POR *PERMI *PERMJ *PERMK *CPOR *PRPOR
_gen_fluid()            # 生成 *MODEL *PVT *DENSITY *BWI 等
_gen_rockfluid()        # 生成 *ROCKFLUID *RPT *SWT *SLT（4列对齐）
_gen_initial()          # 生成 *INITIAL *VERTICAL *PB *REFPRES 等
_gen_numerical()        # 生成 *NUMERICAL *DTMAX *MAXSTEPS
_gen_wells()            # 生成 *RUN *DATE *WELL *OPERATE *PERF *ALTER *STOP
generate()              # 按序调用所有 _gen_*，返回完整文件字符串
```

**`_write_array` modifier 逻辑**：
```
modifier == "CON" 或 scalar → "*KEYWORD *CON value"
modifier == "KVAR"          → "*KEYWORD *KVAR\n   v1  v2  v3"
modifier == "IVAR"          → "*KEYWORD *IVAR\n   ..."
modifier == "JVAR"          → "*KEYWORD *JVAR\n   ..."
modifier == "ALL"           → "*KEYWORD *ALL\n   （每行最多8值）"
无 modifier，单值            → "*KEYWORD *CON value"
无 modifier，多值            → "*KEYWORD *KVAR\n   ..."
```

**调用方式**：
```python
from generators.cmg_generator import generate_cmg
import json

with open("outputs/json/mxspe001_parsed.json") as f:
    data = json.load(f)
generate_cmg(data, "outputs/cmg/mxspe001_roundtrip.dat")
```

---

## 5. 规则文件详解

### 5.1 `rules/parameters.yaml`

每个参数条目的完整结构：
```yaml
porosity:
  standard_name: porosity
  chinese_name: 孔隙度
  data_type: float           # float | integer | float_array | string
  physical_range: [0.01, 0.40]   # 物理合法范围，供 Pydantic 验证层使用
  required: true
  cmg:
    keyword: "*POR"
    block: RESERVOIR
    unit: fraction
    format: CON_or_array     # 写法类型
    example: "*POR *CON 0.3"
  petrel:
    keyword: PORO
    section: GRID
    unit: fraction
    format: array_slash
    example: "PORO\n  300*0.25 /"
  unit_conversion: null      # 引用 units.yaml 中的规则名，null=不需换算
```

**已定义参数类别**：
网格（grid_type/ni/nj/nk/di/dj/dk/depth_ref_block）、
储层（porosity/perm_i/perm_j/perm_k/rock_compressibility/rock_ref_pressure）、
流体（pvt_table/oil_density/gas_density/water_density/water_fvf/water_compressibility/water_ref_pressure/water_viscosity）、
相渗（swt_table/slt_table）、
初始（ref_pressure/ref_depth/woc_depth/goc_depth/bubble_point_pressure）、
数值（max_timestep/max_steps）

---

### 5.2 `rules/units.yaml`

每条换算规则的结构：
```yaml
ft_to_m:
  physical_quantity: length
  from_unit: ft
  to_unit: m
  factor: 0.3048
  formula: "value_m = value_ft * 0.3048"
  inverse: m_to_ft

fahrenheit_to_celsius:
  physical_quantity: temperature
  from_unit: degF
  to_unit: degC
  factor: null              # 非线性，无法用单一系数
  formula: "value_C = (value_F - 32.0) / 1.8"
  inverse: celsius_to_fahrenheit
```

**换算方向**：CMG FIELD → Petrel METRIC（生成 Petrel 文件时）。
反向（Petrel→CMG）取 factor 倒数，温度除外（非线性，用 inverse 公式）。

**关键换算系数速查**：
```
压力:      psia × 0.0689476 = bara
           psia × 0.00689476 = MPa
压缩系数:  1/psi × 14.5038  = 1/bara  （注意：与压力换算方向相反）
长度:      ft × 0.3048 = m
密度:      lb/ft³ × 16.0185 = kg/m³
气体体积:  Mscf × 28.3168 = m³
液体体积:  STB × 0.158987 = m³
溶解GOR:   scf/STB × 0.178107 = m³/m³
产液速率:  STB/d × 0.158987 = m³/d
产气速率:  Mscf/d × 28.3168 = m³/d
渗透率:    md = md（相同，无需换算）
粘度:      cp = cp（相同）
体积系数:  RB/STB = m³/m³（数值相同）
温度:      °C = (°F - 32) / 1.8
```

---

### 5.3 `rules/file_structure.yaml`

描述两种软件的文件格式约定：

| 规则项 | CMG IMEX (.dat) | Petrel Eclipse (.DATA) |
|--------|----------------|------------------------|
| 注释符 | `**` | `--` |
| 关键字前缀 | `*`（必须） | 无 |
| 大小写 | 不敏感 | 不敏感 |
| 数组结束符 | 无（遇下一个 `*` 关键字结束） | `/`（斜杠） |
| 重复语法 | 无内置（用修饰词） | `N*value` |
| 文件区块 | 无显式段名，靠关键字归类 | 有显式段名，严格顺序 |

**CMG 文件区块顺序**：
IO_CONTROL → GRID → RESERVOIR → FLUID → ROCKFLUID → INITIAL → NUMERICAL → WELL

**Petrel 文件段名顺序**：
RUNSPEC → GRID → EDIT → PROPS → REGIONS → SOLUTION → SUMMARY → SCHEDULE

---

## 6. CMG IMEX 格式速查（关键知识）

### 6.1 数组修饰词

```
*POR *CON 0.3          → 全场常数
*DK *KVAR              → 按K层给值（最常用），下行依次列出各层值
   50.0 30.0 20.0
*DI *IVAR              → 按I方向逐列给值
*PERMJ *EQUALSI        → J方向 = I方向（无需重列值）
*PERMI *ALL            → 逐块给值，按 I 快 J 中 K 慢 的顺序
   49.29 162.25 ...
```

### 6.2 N*value 重复语法

```
2*8.0   → 8.0  8.0
5*0.3   → 0.3  0.3  0.3  0.3  0.3
注意：N*value 中间不能有空格！
```

### 6.3 *KDIR 对 K 层方向的影响

```
不写 *KDIR：K=1 是最底层（SPE1/SPE2 使用）
*KDIR *DOWN：K=1 是最顶层（SPE9/SPE10 使用）
```

### 6.4 射孔格式

```
*PERF 1              → 标准射孔，需指定 i j k wi
** if jf kf wi
   1  1  3  1.0E+5

*PERFV *GEO 1        → 垂直井简化射孔，只需 k 和 ff
** kf ff
   8:9  1.0          → k1:k2 范围语法，射 k=8 和 k=9 两层

*PERF GEOA 'Name'    → 用井名字符串代替编号（SPE10写法）
```

### 6.5 井约束

```
*INJECTOR *UNWEIGHT 1
*INCOMP *GAS / *WATER / *SOLVENT
*OPERATE *MAX *STG  value    → 最大气注入（Mscf/d）
*OPERATE *MAX *STW  value    → 最大水注入（STB/d）
*OPERATE *MAX *BHP  value    → 最大井底压力（psia）

*PRODUCER 2
*OPERATE *MAX *STO  value    → 最大产油（STB/d）
*OPERATE *MIN *BHP  value    → 最小井底压力（psia）
*OPERATE *MIN *STO  value  *CONT *REPEAT  → 持续监控
```

---

## 7. Petrel Eclipse 格式速查（待 Petrel Parser 开发时参考）

### 7.1 文件整体格式特点

- **注释**：`--` 后内容为注释
- **关键字**：无前缀，直接写（如 `PORO`，不是 `*PORO`）
- **数组结束**：必须以 `/` 结尾
- **重复语法**：`N*value`（如 `300*0.3`）
- **段名**：RUNSPEC、GRID、PROPS、SOLUTION、SCHEDULE 等，必须显式写出

### 7.2 典型格式示例

```
-- Petrel/Eclipse 注释

RUNSPEC
DIMENS
  10 10 3 /          -- 网格维度 NI NJ NK，以 / 结尾
FIELD               -- 单位制声明（关键字即单位名）

GRID
PORO
  300*0.3 /          -- 300 个网格全部孔隙度 0.3，/ 结尾

PERMX
  100*200 100*50 100*500 /  -- 按 K=1,2,3 层给值

PROPS
PVTO
-- Rs(m3/m3)  Pres(bara) Bo(m3/m3) Viso(cp)
   0.0        1.0        1.05      1.0  /   -- 每组以 / 结尾（饱和点）
   ...
/                                            -- 整个表以额外 / 结尾

SWOF
-- Sw    krw   krow  Pcow(bara)
  0.12   0.0   1.0   0.0
  0.82   0.0   0.0   0.0  /

SOLUTION
EQUIL
-- Datum  Pi      WOC    Pcwoc  GOC   Pcgoc
  2560.3  330.0   2700.0  0.0   2000.0  0.0 /

SCHEDULE
WELSPECS
-- WellName  Group  I  J  RefDepth  Phase
  'INJ'  'FIELD'  1  1  1*  WATER /
/

COMPDAT
-- WellName  I  J  K1  K2  Status  ...
  'INJ'  1  1  3  3  OPEN  2*  0.25 /
/

DATES
  22 APR 1986 /
/
```

### 7.3 CMG → Petrel 关键字对照

| 物理量 | CMG 关键字 | Petrel 关键字 | 所在段 |
|--------|-----------|--------------|--------|
| 网格维度 | `*GRID *CART NI NJ NK` | `DIMENS NI NJ NK /` | RUNSPEC |
| 单位制 | `*INUNIT *FIELD` | `FIELD`（单独一行）| RUNSPEC |
| I方向尺寸 | `*DI` | `DX` | GRID |
| J方向尺寸 | `*DJ` | `DY` | GRID |
| K方向尺寸 | `*DK` | `DZ` | GRID |
| 顶深 | `*DEPTH i j k value` | `TOPS` | GRID |
| 孔隙度 | `*POR` | `PORO` | GRID |
| I渗透率 | `*PERMI` | `PERMX` | GRID |
| J渗透率 | `*PERMJ` | `PERMY` | GRID |
| K渗透率 | `*PERMK` | `PERMZ` | GRID |
| 黑油PVT | `*PVT` | `PVTO` / `PVDG` | PROPS |
| 密度 | `*DENSITY *OIL/GAS/WATER` | `DENSITY` (单行3值) | PROPS |
| 水压缩 | `*CW` + `*BWI` + `*VWI` | `PVTW` (单行5值) | PROPS |
| 岩石压缩 | `*CPOR` + `*PRPOR` | `ROCK` (单行2值) | PROPS |
| 水油相渗 | `*SWT` | `SWOF` | PROPS |
| 气液相渗 | `*SLT` | `SGOF` | PROPS |
| 初始压力 | `*REFPRES` + `*REFDEPTH` | `EQUIL` | SOLUTION |
| 流体接触 | `*DWOC` + `*DGOC` | `EQUIL`（同行）| SOLUTION |
| 泡点压力 | `*PB` | `PBUB` | SOLUTION |
| 井定义 | `*WELL + *INJECTOR/PRODUCER` | `WELSPECS` | SCHEDULE |
| 射孔 | `*PERF i j k wi` | `COMPDAT` | SCHEDULE |
| 时间推进 | `*TIME` / `*DATE` | `DATES` / `TSTEP` | SCHEDULE |
| 生产约束 | `*OPERATE *MAX *STO` | `WCONPROD` | SCHEDULE |
| 注入约束 | `*OPERATE *MAX *STG/*STW` | `WCONINJE` | SCHEDULE |

---

## 8. 开发规范

### 8.1 代码风格

- Python 3.8+，不使用第三方库（仅标准库 + PyYAML + Pydantic）
- 函数命名：`parse_xxx()`、`generate_xxx()`、`_private_helper()`
- 所有解析方法挂载在类上，工具函数为模块级函数
- 不使用 try/except 静默吞掉所有异常，解析失败优先返回 None 而非抛出

### 8.2 测试规范

往返测试标准：
```
CMG .dat → JSON → CMG .dat（往返）
数值误差 < 0.01%（浮点精度损失可接受）
文件可被 CMG 模拟器成功读取
```

### 8.3 路径约定

```python
PROJECT_ROOT = Path(__file__).parent.parent  # uda_middle_layer/
INPUTS_CMG   = PROJECT_ROOT / "inputs" / "cmg"
INPUTS_PETREL= PROJECT_ROOT / "inputs" / "petrel"
OUTPUTS_JSON = PROJECT_ROOT / "outputs" / "json"
OUTPUTS_CMG  = PROJECT_ROOT / "outputs" / "cmg"
OUTPUTS_PETREL=PROJECT_ROOT / "outputs" / "petrel"
RULES_DIR    = PROJECT_ROOT / "rules"
```

---

## 9. 项目进度

### 第一周（已完成）

- [x] CMG IMEX 软件下载与环境配置
- [x] 阅读 CMG IMEX 用户手册，整理关键字清单
- [x] 确定项目整体架构（三层：Parser → JSON → Generator）
- [x] 编写 `rules/parameters.yaml`（覆盖约 25 个核心参数）
- [x] 编写 `rules/units.yaml`（覆盖所有主要单位换算）
- [x] 编写 `rules/file_structure.yaml`（CMG 和 Petrel 结构描述）
- [x] 实现 `parsers/cmg_parser.py` v2（词元流解析，支持所有 SPE 示例）
- [x] 实现 `generators/cmg_generator.py` v2（modifier 保留，往返一致）
- [x] 对 mxspe001.dat 完成往返测试（JSON 输出正确，CMG 文件可读取）

### 第二周（进行中）

- [x] 深入学习 CMG IMEX 格式（SPE1-10 五个示例全面分析）
- [x] 调整项目目录架构（inputs/outputs/docs 分离）
- [x] 编写项目全景文档（本文件）
- [ ] 获取 Petrel Eclipse .DATA 示例文件（主线阻塞点）
  - 备选：https://github.com/OPM/opm-tests（公开 Eclipse .DATA 文件）
  - 备选：SPE Comparative Solution Project 官网
- [ ] 对照真实 Petrel 文件，验证并补全 `parameters.yaml` 的 petrel 部分
- [ ] 实现 `parsers/petrel_parser.py` 框架（优先 5 个关键参数）
- [ ] 编写 `validators/schema.py` 基础框架（Pydantic 模型）

### 第三周（计划）

- [ ] 完成 `parsers/petrel_parser.py`（全部核心参数）
- [ ] 实现 `utils/unit_converter.py`（从 units.yaml 读取换算规则）
- [ ] 实现 `generators/petrel_generator.py`
- [ ] 编写单元测试（每个参数独立验证）

### 第四周（计划）

- [ ] CMG → Petrel 正向转换端到端测试
- [ ] Petrel → CMG 反向转换端到端测试
- [ ] 实现识别报告输出（成功/低置信度/未识别/缺失字段）

### 第五周（计划）

- [ ] 往返测试：CMG → Petrel → CMG，数值误差分析
- [ ] 用导师提供的真实文件测试全流程
- [ ] 完善 `main.py` 命令行接口
- [ ] 准备项目演示

---

## 10. 当前已知问题和 TODO

| 问题 | 优先级 | 说明 |
|------|--------|------|
| `*KDIR *DOWN` 未被记录 | 中 | 不影响数值，但 K 层顺序信息丢失 |
| `*PERMJ *EQUALSI` 未处理 | 中 | Parser 跳过后 perm_j 缺失，Generator 不会输出 |
| `*IJK` 范围格式未支持 | 低 | `*POR *IJK 1:5 1:10 1:3 0.25` 会被跳过 |
| `*GROUP` / `*ATTACHTO` 未解析 | 低 | SPE9 的井组功能 |
| `*MONITOR` 条件未解析 | 低 | 停止条件不会进入 JSON |
| `*SHUTIN` / `*OPEN` 未解析 | 中 | SPE5 的 WAG 循环无法正确往返 |
| Petrel Parser 待实现 | 高 | 主线任务，阻塞于示例文件获取 |
| schema.py Pydantic 验证 | 中 | 物理范围校验尚未实现 |
| unit_converter.py 未独立 | 低 | 目前换算逻辑内嵌在 Generator |

---

## 11. 快速上手：如何运行现有代码

```python
# 1. 解析 CMG 文件
from parsers.cmg_parser import parse_cmg

data = parse_cmg(
    "inputs/cmg/mxspe001.dat",
    "outputs/json/mxspe001_parsed.json"   # 可选，同时写出JSON文件
)

print(f"网格: {data['grid']['ni']}×{data['grid']['nj']}×{data['grid']['nk']}")
print(f"孔隙度: {data['reservoir']['porosity']}")
print(f"井数量: {len(data['wells'])}")

# 2. 从 JSON 生成 CMG 文件（往返测试）
from generators.cmg_generator import generate_cmg
import json

with open("outputs/json/mxspe001_parsed.json") as f:
    data = json.load(f)

generate_cmg(data, "outputs/cmg/mxspe001_roundtrip.dat")

# 3. 命令行运行
python parsers/cmg_parser.py inputs/cmg/mxspe001.dat
python generators/cmg_generator.py outputs/json/mxspe001_parsed.json
```

---

*文档结束 · 如需更新请同步修改本文件*
