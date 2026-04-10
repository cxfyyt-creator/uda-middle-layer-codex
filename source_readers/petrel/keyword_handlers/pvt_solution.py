from __future__ import annotations

from infra.pvt_metadata import apply_pvt_role
from source_readers.petrel.value_builders import scalar, table, to_float


def parse_pvtw(parser, R):
    vals = parser._read_floats_until_slash()
    if len(vals) >= 4:
        src = "PROPS PVTW"
        R["fluid"]["water_ref_pressure"] = scalar(vals[0], "psia", src)
        R["fluid"]["water_fvf"] = scalar(vals[1], "RB/STB", src)
        R["fluid"]["water_compressibility"] = scalar(vals[2], "1/psi", src)
        R["fluid"]["water_viscosity"] = scalar(vals[3], "cp", src)
        if len(vals) >= 5:
            R["fluid"]["water_viscosity_coeff"] = scalar(vals[4], "1/psi", src)


def parse_rock(parser, R):
    parser._skip_rest_of_kw_line(parser._last_lineno())
    vals = parser._read_floats_until_slash()
    if len(vals) >= 2:
        R["reservoir"]["rock_ref_pressure"] = scalar(vals[0], "psia", "PROPS ROCK")
        R["reservoir"]["rock_compressibility"] = scalar(vals[1], "1/psi", "PROPS ROCK")


def parse_miscible(parser, R):
    R["meta"]["model_type"] = "miscible"
    R["fluid"]["model"] = "MISCIBLE"


def parse_density(parser, R):
    parser._skip_rest_of_kw_line(parser._last_lineno())
    vals = parser._read_floats_until_slash()
    if len(vals) >= 3:
        src = "PROPS DENSITY"
        R["fluid"]["oil_density"] = scalar(vals[0], "lb/ft3", src)
        R["fluid"]["water_density"] = scalar(vals[1], "lb/ft3", src)
        R["fluid"]["gas_density"] = scalar(vals[2], "lb/ft3", src)


def parse_pvto(parser, R):
    parser._skip_rest_of_kw_line(parser._last_lineno())
    rows = []
    current_rs = None
    while parser._peek():
        group = parser._read_until_slash()
        if not group:
            break
        nums = []
        for token in group:
            try:
                nums.append(to_float(token))
            except (ValueError, TypeError):
                pass
        if not nums:
            break
        if len(nums) >= 4:
            current_rs = nums[0]
            rows.append([current_rs, nums[1], nums[2], nums[3]])
            i = 4
            while i + 2 < len(nums):
                rows.append([current_rs, nums[i], nums[i + 1], nums[i + 2]])
                i += 3
        elif len(nums) == 3 and current_rs is not None:
            rows.append([current_rs, nums[0], nums[1], nums[2]])
    if rows:
        R["fluid"]["pvto_table"] = apply_pvt_role(
            table(["rs", "p", "bo", "viso"], rows, "PROPS PVTO"),
            pvt_form="eclipse_pvto",
            representation_role="native_source",
            preferred_backend="petrel",
        )


def parse_pvdg(parser, R):
    parser._skip_rest_of_kw_line(parser._last_lineno())
    nums = parser._read_floats_until_slash()
    rows = []
    i = 0
    while i + 2 < len(nums):
        rows.append([nums[i], nums[i + 1], nums[i + 2]])
        i += 3
    if rows:
        R["fluid"]["pvdg_table"] = apply_pvt_role(
            table(["p", "bg", "visg"], rows, "PROPS PVDG"),
            pvt_form="eclipse_pvdg",
            representation_role="native_source",
            preferred_backend="petrel",
        )


def parse_equil(parser, R):
    vals = parser._read_floats_until_slash()
    if len(vals) >= 2:
        src = "SOLUTION EQUIL"
        R["initial"]["ref_depth"] = scalar(vals[0], "ft", src)
        R["initial"]["ref_pressure"] = scalar(vals[1], "psia", src)
        if len(vals) >= 3:
            R["initial"]["woc_depth"] = scalar(vals[2], "ft", src)
        if len(vals) >= 5:
            R["initial"]["goc_depth"] = scalar(vals[4], "ft", src)


def parse_rsvd(parser, R):
    rows = []
    while parser._peek():
        nums = parser._read_floats_until_slash()
        if not nums:
            break
        if len(nums) >= 2:
            rows.append([nums[0], nums[1]])
    if rows:
        R["initial"]["rsvd_table"] = table(["depth", "rs"], rows, "SOLUTION RSVD")


def parse_pbvd(parser, R):
    rows = []
    while parser._peek():
        nums = parser._read_floats_until_slash()
        if not nums:
            break
        if len(nums) >= 2:
            rows.append([nums[0], nums[1]])
    if rows:
        R["initial"]["pbvd_table"] = table(["pb", "depth"], rows, "SOLUTION PBVD")
