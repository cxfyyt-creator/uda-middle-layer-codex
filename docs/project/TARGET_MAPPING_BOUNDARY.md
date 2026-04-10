# Target Mapping Boundary

## Goal

This note fixes one boundary in the current architecture:

`raw file -> source_readers -> Source IR -> standardizers -> Standard IR -> target_mappers -> Target IR -> target_writers -> output file`

The key point is:

- `standardizers/` should only normalize and enrich the Standard IR.
- `target_mappers/` should build target-specific shapes that only one backend needs.
- `target_writers/` should only write already-prepared target data.

## Current CMG rule split

These rules are now treated as CMG target mapping, not domain logic:

- `fluid.pvto_table + fluid.pvdg_table -> fluid.pvt_table`
- `rockfluid.swfn_table + rockfluid.sof3_table -> rockfluid.swt_table`
- `rockfluid.swfn_table + rockfluid.sof2_table -> rockfluid.swt_table / rockfluid.slt_table`
- `rockfluid.sgof_table -> rockfluid.slt_table`
- `rockfluid.sgt_table -> rockfluid.slt_table`

## Current Petrel rule split

These rules are now treated as Petrel target mapping, not writer-side fallback:

- `fluid.pvt_table -> fluid.pvto_table + fluid.pvdg_table`
- `reservoir.rock_ref_pressure -> fluid.rock_ref_pressure`
- `reservoir.rock_compressibility -> fluid.rock_compressibility`

## Landed structure

- `target_mappers/cmg/pvt_mapping.py`
  - builds CMG `pvt_table`
- `target_mappers/cmg/rockfluid_mapping.py`
  - builds CMG `swt_table` and `slt_table`
- `target_mappers/cmg/target_ir_builder.py`
  - prepares the full CMG Target IR before writing
- `target_mappers/petrel/pvt_mapping.py`
  - builds Petrel `pvto_table` and `pvdg_table`
- `target_mappers/petrel/target_ir_builder.py`
  - prepares the full Petrel Target IR before writing

## What standardizers still do

These remain in `standardizers/` because they are standard-model semantics, not CMG formatting:

- resolve internal references like `EQUALSI`
- infer missing `perm_j` for radial cases
- derive `oil_compressibility` and `oil_viscosity_coeff`
- derive `bubble_point_pressure`
- enrich miscible model fields

## Practical rule

If a rule answers "what does this data mean?", it belongs in `domain_logic/` or `standardizers/`.

If a rule answers "how should this data be prepared for CMG/Petrel output?", it belongs in `target_mappers/`.
