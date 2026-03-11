# 通用数据适配中间层 (UDA Middle Layer)
## CMG IMEX <-> Petrel Eclipse 双向格式转换

```
uda_middle_layer/
├── inputs/                 ← 原始输入（只读）
│   ├── cmg/                ← CMG .dat 输入文件
│   └── petrel/             ← Petrel .DATA 输入文件
│
├── outputs/                ← 程序输出（可重建）
│   ├── json/               ← Parser 产出的中间层 JSON
│   ├── cmg/                ← Generator 产出的 CMG .dat
│   └── petrel/             ← Generator 产出的 Petrel .DATA
│
├── rules/                  ← 规则文件（参数映射/单位/结构）
│   ├── parameters.yaml
│   ├── units.yaml
│   ├── file_structure.yaml
│   └── PROJECT_CONTEXT.md
│
├── docs/                   ← 项目文档（架构与格式说明）
│   └── PROJECT_CONTEXT.md
│
├── parsers/
│   ├── cmg_parser.py       ← 读取 .dat → 通用 JSON
│   └── petrel_parser.py    ← 读取 .DATA → 通用 JSON（待完善）
│
├── generators/
│   ├── cmg_generator.py    ← 通用 JSON → .dat
│   └── petrel_generator.py ← 通用 JSON → .DATA（待完善）
│
├── validators/
│   └── schema.py
├── utils/
│   └── unit_converter.py
├── tests/
│   └── sample_files/
└── main.py
```

## 快速开始
```bash
# 1) CMG .dat -> JSON
python parsers/cmg_parser.py inputs/cmg/mxspe001.dat

# 2) JSON -> CMG .dat
python generators/cmg_generator.py outputs/json/mxspe001_parsed.json
```

## 说明
- `inputs/` 只放原始文件，程序不改写。
- `outputs/` 放可再生结果，可随时清空后重跑。
- `rules/` 保持“规则与代码分离”，新增映射优先改 YAML。
