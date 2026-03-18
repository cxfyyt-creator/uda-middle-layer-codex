# =============================================================================
# schema.py  —  通用JSON中间层 Pydantic 验证模型
# 职责：格式校验 + 物理范围校验
# =============================================================================

from __future__ import annotations
from typing import List, Optional, Literal, Union
from pydantic import BaseModel, field_validator, model_validator, ValidationError
from enum import Enum
import warnings


# ── 枚举 ─────────────────────────────────────────────────────────────────────

class SourceSoftware(str, Enum):
    CMG_IMEX = "cmg_imex"
    PETREL   = "petrel_eclipse"

class UnitSystem(str, Enum):
    FIELD  = "field"
    METRIC = "metric"
    LAB    = "lab"
    SI     = "si"

class WellType(str, Enum):
    INJECTOR = "INJECTOR"
    PRODUCER = "PRODUCER"


# ── 通用值容器 ────────────────────────────────────────────────────────────────

class ScalarValue(BaseModel):
    type: Literal["scalar"]
    value: float
    unit: Optional[str] = ""
    confidence: float = 1.0
    source: str = ""

class ArrayValue(BaseModel):
    type: Literal["array"]
    values: List[float]
    unit: Optional[str] = ""
    grid_order: str = "IJK"
    shape: Optional[List[int]] = None
    confidence: float = 1.0
    source: str = ""

class TableValue(BaseModel):
    type: Literal["table"]
    columns: List[str]
    rows: List[List[float]]
    unit: Optional[str] = "fraction"
    confidence: float = 1.0
    source: str = ""

    @field_validator("rows")
    @classmethod
    def rows_match_columns(cls, rows, info):
        columns = info.data.get("columns", [])
        for i, row in enumerate(rows):
            if len(row) != len(columns):
                raise ValueError(f"第{i+1}行有{len(row)}个值，但columns定义了{len(columns)}列")
        return rows


# ── Meta ─────────────────────────────────────────────────────────────────────

class MetaBlock(BaseModel):
    source_software: SourceSoftware
    source_file: str = ""
    unit_system: UnitSystem
    conversion_timestamp: str = ""


# ── Grid ─────────────────────────────────────────────────────────────────────

class GridBlock(BaseModel):
    grid_type: Optional[str] = None
    ni: Optional[int] = None
    nj: Optional[int] = None
    nk: Optional[int] = None
    di: Optional[Union[ScalarValue, ArrayValue]] = None
    dj: Optional[Union[ScalarValue, ArrayValue]] = None
    dk: Optional[Union[ScalarValue, ArrayValue]] = None
    depth_ref_block: Optional[ScalarValue] = None

    @field_validator("ni", "nj", "nk")
    @classmethod
    def dims_positive(cls, v):
        if v is not None and v <= 0:
            raise ValueError(f"网格维度必须大于0，当前: {v}")
        return v


# ── Reservoir ────────────────────────────────────────────────────────────────

class ReservoirBlock(BaseModel):
    porosity: Optional[Union[ScalarValue, ArrayValue]] = None
    perm_i: Optional[Union[ScalarValue, ArrayValue]] = None
    perm_j: Optional[Union[ScalarValue, ArrayValue]] = None
    perm_k: Optional[Union[ScalarValue, ArrayValue]] = None
    rock_compressibility: Optional[ScalarValue] = None
    rock_ref_pressure: Optional[ScalarValue] = None

    @field_validator("porosity")
    @classmethod
    def check_porosity(cls, v):
        if v is None: return v
        vals = [v.value] if v.type == "scalar" else v.values
        bad = [x for x in vals if not (0.0 < x <= 0.60)]
        if bad:
            raise ValueError(f"孔隙度超出范围(0, 0.60]，问题值: {bad[:5]}")
        return v

    @field_validator("perm_i", "perm_j", "perm_k")
    @classmethod
    def check_perm(cls, v):
        if v is None: return v
        vals = [v.value] if v.type == "scalar" else v.values
        bad = [x for x in vals if x < 0]
        if bad:
            raise ValueError(f"渗透率不能为负，问题值: {bad[:5]}")
        return v

    @field_validator("rock_compressibility")
    @classmethod
    def check_cpor(cls, v):
        if v is None: return v
        if not (1e-9 < v.value < 1e-2):
            raise ValueError(f"岩石压缩系数 {v.value} 超出合理范围(1e-9, 1e-2)")
        return v


# ── Fluid ─────────────────────────────────────────────────────────────────────

class FluidBlock(BaseModel):
    pvt_table: Optional[TableValue] = None
    pvts_table: Optional[TableValue] = None
    oil_density: Optional[ScalarValue] = None
    gas_density: Optional[ScalarValue] = None
    water_density: Optional[ScalarValue] = None
    solvent_density: Optional[ScalarValue] = None
    water_fvf: Optional[ScalarValue] = None
    water_compressibility: Optional[ScalarValue] = None
    water_ref_pressure: Optional[ScalarValue] = None
    water_viscosity: Optional[ScalarValue] = None
    tlmixpar: Optional[ScalarValue] = None
    omegasg: Optional[ScalarValue] = None
    minss: Optional[ScalarValue] = None
    oil_compressibility: Optional[ScalarValue] = None
    oil_viscosity_coeff: Optional[ScalarValue] = None

    @field_validator("water_fvf")
    @classmethod
    def check_bw(cls, v):
        if v is None: return v
        if not (0.90 <= v.value <= 1.15):
            raise ValueError(f"水体积系数 {v.value} 超出范围[0.90, 1.15]")
        return v

    @field_validator("water_viscosity")
    @classmethod
    def check_vw(cls, v):
        if v is None: return v
        if not (0.05 <= v.value <= 5.0):
            raise ValueError(f"水粘度 {v.value} 超出范围[0.05, 5.0] cp")
        return v


# ── RockFluid ─────────────────────────────────────────────────────────────────

class RockFluidBlock(BaseModel):
    swt_table: Optional[TableValue] = None
    slt_table: Optional[TableValue] = None

    @field_validator("swt_table")
    @classmethod
    def check_swt(cls, v):
        if v is None: return v
        for row in v.rows:
            if not (0.0 <= row[0] <= 1.0):
                raise ValueError(f"Sw={row[0]} 超出[0,1]")
        return v

    @field_validator("slt_table")
    @classmethod
    def check_slt(cls, v):
        if v is None: return v
        for row in v.rows:
            if not (0.0 <= row[0] <= 1.0):
                raise ValueError(f"Sl={row[0]} 超出[0,1]")
        return v


# ── Initial ───────────────────────────────────────────────────────────────────

class InitialBlock(BaseModel):
    ref_depth: Optional[ScalarValue] = None
    ref_pressure: Optional[ScalarValue] = None
    bubble_point_pressure: Optional[Union[ScalarValue, ArrayValue]] = None
    solvent_bubble_point_pressure: Optional[Union[ScalarValue, ArrayValue]] = None
    woc_depth: Optional[ScalarValue] = None
    goc_depth: Optional[ScalarValue] = None

    @field_validator("ref_pressure")
    @classmethod
    def check_pres(cls, v):
        if v is None: return v
        if v.value <= 0:
            raise ValueError(f"参考压力必须>0，当前: {v.value}")
        return v

    @model_validator(mode="after")
    def check_depth_order(self):
        goc, woc = self.goc_depth, self.woc_depth
        if goc and woc and goc.value >= woc.value:
            raise ValueError(f"GOC({goc.value})应比WOC({woc.value})浅(数值更小)")
        return self


# ── Numerical ─────────────────────────────────────────────────────────────────

class NumericalBlock(BaseModel):
    max_timestep: Optional[ScalarValue] = None
    max_steps: Optional[ScalarValue] = None

    @field_validator("max_timestep")
    @classmethod
    def check_dt(cls, v):
        if v is None: return v
        if v.value <= 0:
            raise ValueError(f"最大时间步长必须>0，当前: {v.value}")
        return v


# ── Well ──────────────────────────────────────────────────────────────────────

class PerfLocation(BaseModel):
    i: int
    j: int
    k: int
    wi: float = 1.0

class WellBlock(BaseModel):
    well_name: str
    well_type: Optional[WellType] = None
    bhp_max: Optional[float] = None
    bhp_min: Optional[float] = None
    rate_max: Optional[float] = None
    rate_min: Optional[float] = None
    perforations: List[PerfLocation] = []
    well_radius: Optional[float] = None

    @field_validator("well_radius")
    @classmethod
    def check_radius(cls, v):
        if v is None: return v
        if not (0.001 <= v <= 5.0):
            raise ValueError(f"井筒半径 {v} 超出范围[0.001, 5.0]")
        return v


# ── 顶层模型 ──────────────────────────────────────────────────────────────────

class UniversalModel(BaseModel):
    meta: MetaBlock
    uda_version: str = "1.0.0"
    grid: Optional[GridBlock] = None
    reservoir: Optional[ReservoirBlock] = None
    fluid: Optional[FluidBlock] = None
    rockfluid: Optional[RockFluidBlock] = None
    initial: Optional[InitialBlock] = None
    numerical: Optional[NumericalBlock] = None
    wells: List[WellBlock] = []

    @model_validator(mode="after")
    def warn_missing_blocks(self):
        missing = [b for b in ["grid","reservoir","fluid"]
                   if getattr(self, b) is None]
        if missing:
            warnings.warn(f"以下必要区块缺失: {missing}，模型可能不完整")
        return self


def validate_standard_model(data: dict, *, strict: bool = True) -> UniversalModel:
    """验证标准模型数据。

    strict=True 时抛出 ValidationError，防止静默失败。
    strict=False 时返回 None 代表验证失败。
    """
    try:
        return UniversalModel.model_validate(data)
    except ValidationError:
        if strict:
            raise
        return None
