# =============================================================================
# standard_model_schema.py — Standard IR Pydantic schema
# 职责：格式校验 + 基础物理范围校验
# =============================================================================

from __future__ import annotations

import warnings
from enum import Enum
from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from checks.physics import collect_porosity_physics_issues


class SourceSoftware(str, Enum):
    CMG_IMEX = "cmg_imex"
    PETREL = "petrel_eclipse"


class UnitSystem(str, Enum):
    FIELD = "field"
    METRIC = "metric"
    LAB = "lab"
    SI = "si"


class WellType(str, Enum):
    INJECTOR = "INJECTOR"
    PRODUCER = "PRODUCER"


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
                raise ValueError(f"第 {i + 1} 行有 {len(row)} 个值，但 columns 定义了 {len(columns)} 列")
        return rows


class RefValue(BaseModel):
    type: Literal["ref"]
    source_file: str = ""
    dataset: Optional[str] = None
    format: Optional[str] = None
    relation: Optional[str] = None
    unit: Optional[str] = ""
    confidence: float = 1.0
    source: str = ""
    required: bool = True
    scale: Optional[float] = None
    source_section: Optional[str] = None
    source_key: Optional[str] = None
    source_format_hint: Optional[dict[str, Any]] = None

    @model_validator(mode="after")
    def validate_ref_shape(self):
        relation = str(self.relation or "").upper()
        if relation == "EQUALSI":
            if not self.source_key:
                raise ValueError("internal EQUALSI ref requires source_key")
            return self

        if not self.source_file:
            raise ValueError("external ref requires source_file")
        return self


ValueObject = Union[ScalarValue, ArrayValue, RefValue]


class CaseDependencyItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    kind: str
    path: str
    source_path: Optional[str] = None
    exists: Optional[bool] = None
    required: bool = True
    line: Optional[int] = None


class CaseManifestBlock(BaseModel):
    root_file: str = ""
    source_dir: str = ""
    static_inputs: List[CaseDependencyItem] = Field(default_factory=list)
    runtime_inputs: List[CaseDependencyItem] = Field(default_factory=list)
    runtime_outputs: List[CaseDependencyItem] = Field(default_factory=list)


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    well_name: str
    absolute_days: float
    event_type: str
    target: Optional[str] = None
    value: Optional[float] = None


class UnparsedBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    line: Optional[int] = None
    text: str = ""
    reason: str = ""
    source: Optional[str] = None


class MetaBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    source_software: SourceSoftware
    source_file: str = ""
    unit_system: UnitSystem
    conversion_timestamp: str = ""


class GridBlock(BaseModel):
    grid_type: Optional[str] = None
    ni: Optional[int] = None
    nj: Optional[int] = None
    nk: Optional[int] = None
    di: Optional[ValueObject] = None
    dj: Optional[ValueObject] = None
    dk: Optional[ValueObject] = None
    active_cell_mask: Optional[ValueObject] = None
    pinchout_array: Optional[ValueObject] = None
    cell_activity_mode: Optional[str] = None
    depth_ref_block: Optional[ScalarValue] = None

    @field_validator("ni", "nj", "nk")
    @classmethod
    def dims_positive(cls, v):
        if v is not None and v <= 0:
            raise ValueError(f"网格维度必须大于 0，当前值: {v}")
        return v


class ReservoirBlock(BaseModel):
    porosity: Optional[ValueObject] = None
    perm_i: Optional[ValueObject] = None
    perm_j: Optional[ValueObject] = None
    perm_k: Optional[ValueObject] = None
    rock_compressibility: Optional[ScalarValue] = None
    rock_ref_pressure: Optional[ScalarValue] = None

    @staticmethod
    def _extract_numeric_values(v):
        if v is None:
            return []
        if v.type == "scalar":
            return [v.value]
        if v.type == "array":
            return v.values
        return []

    @field_validator("perm_i", "perm_j", "perm_k")
    @classmethod
    def check_perm(cls, v):
        if v is None:
            return v
        vals = cls._extract_numeric_values(v)
        if not vals:
            return v
        bad = [x for x in vals if x < 0]
        if bad:
            raise ValueError(f"渗透率不能为负，问题值: {bad[:5]}")
        return v

    @field_validator("rock_compressibility")
    @classmethod
    def check_cpor(cls, v):
        if v is None:
            return v
        if not (1e-9 < v.value < 1e-2):
            raise ValueError(f"岩石压缩系数 {v.value} 超出合理范围 (1e-9, 1e-2)")
        return v


class FluidBlock(BaseModel):
    pvt_table: Optional[TableValue] = None
    pvts_table: Optional[TableValue] = None
    reservoir_temperature: Optional[ScalarValue] = None
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
        if v is None:
            return v
        if not (0.90 <= v.value <= 1.15):
            raise ValueError(f"水体积系数 {v.value} 超出范围 [0.90, 1.15]")
        return v

    @field_validator("water_viscosity")
    @classmethod
    def check_vw(cls, v):
        if v is None:
            return v
        if not (0.05 <= v.value <= 5.0):
            raise ValueError(f"水黏度 {v.value} 超出范围 [0.05, 5.0] cp")
        return v


class RockFluidBlock(BaseModel):
    swt_table: Optional[TableValue] = None
    slt_table: Optional[TableValue] = None

    @field_validator("swt_table")
    @classmethod
    def check_swt(cls, v):
        if v is None:
            return v
        for row in v.rows:
            if not (0.0 <= row[0] <= 1.0):
                raise ValueError(f"Sw={row[0]} 超出 [0,1]")
        return v

    @field_validator("slt_table")
    @classmethod
    def check_slt(cls, v):
        if v is None:
            return v
        for row in v.rows:
            if not (0.0 <= row[0] <= 1.0):
                raise ValueError(f"Sl={row[0]} 超出 [0,1]")
        return v


class InitialBlock(BaseModel):
    ref_depth: Optional[ScalarValue] = None
    ref_pressure: Optional[ScalarValue] = None
    bubble_point_pressure: Optional[ValueObject] = None
    solvent_bubble_point_pressure: Optional[ValueObject] = None
    woc_depth: Optional[ScalarValue] = None
    goc_depth: Optional[ScalarValue] = None

    @field_validator("ref_pressure")
    @classmethod
    def check_pres(cls, v):
        if v is None:
            return v
        if v.value <= 0:
            raise ValueError(f"参考压力必须 > 0，当前值: {v.value}")
        return v

    @model_validator(mode="after")
    def check_depth_order(self):
        goc, woc = self.goc_depth, self.woc_depth
        if goc and woc and goc.value >= woc.value:
            raise ValueError(f"GOC({goc.value}) 应比 WOC({woc.value}) 更浅")
        return self


class NumericalBlock(BaseModel):
    max_timestep: Optional[ScalarValue] = None
    max_steps: Optional[ScalarValue] = None

    @field_validator("max_timestep")
    @classmethod
    def check_dt(cls, v):
        if v is None:
            return v
        if v.value <= 0:
            raise ValueError(f"最大时间步长必须 > 0，当前值: {v.value}")
        return v


class PerfLocation(BaseModel):
    i: int
    j: int
    k: int
    wi: float = 1.0


class WellBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    well_name: str
    well_type: Optional[WellType] = None
    bhp_max: Optional[float] = None
    bhp_min: Optional[float] = None
    rate_max: Optional[float] = None
    rate_min: Optional[float] = None
    perforations: List[PerfLocation] = Field(default_factory=list)
    well_radius: Optional[float] = None

    @field_validator("well_radius")
    @classmethod
    def check_radius(cls, v):
        if v is None:
            return v
        if not (0.001 <= v <= 5.0):
            raise ValueError(f"井筒半径 {v} 超出范围 [0.001, 5.0]")
        return v


class UniversalModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    meta: MetaBlock
    case_manifest: CaseManifestBlock = Field(default_factory=CaseManifestBlock)
    uda_version: str = "1.0.0"
    grid: Optional[GridBlock] = None
    reservoir: Optional[ReservoirBlock] = None
    fluid: Optional[FluidBlock] = None
    rockfluid: Optional[RockFluidBlock] = None
    initial: Optional[InitialBlock] = None
    numerical: Optional[NumericalBlock] = None
    wells: List[WellBlock] = Field(default_factory=list)
    timeline_events: List[TimelineEvent] = Field(default_factory=list)
    unparsed_blocks: List[UnparsedBlock] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_active_cell_physics(self):
        issues = collect_porosity_physics_issues(self.grid, self.reservoir)
        if issues:
            raise ValueError("; ".join(issues))
        return self

    @model_validator(mode="after")
    def warn_missing_blocks(self):
        missing = [b for b in ["grid", "reservoir", "fluid"] if getattr(self, b) is None]
        if missing:
            warnings.warn(f"以下必要区块缺失: {missing}，模型可能不完整")
        return self


def validate_standard_model(data: dict, *, strict: bool = True) -> Optional[UniversalModel]:
    """验证标准模型数据。

    strict=True 时抛出 ValidationError，避免静默失败。
    strict=False 时返回 None，表示验证失败。
    """
    try:
        return UniversalModel.model_validate(data)
    except ValidationError:
        if strict:
            raise
        return None
