# Target Writers Structure

## Pipeline position

`raw file -> source_readers -> Source IR -> standardizers -> Standard IR -> target_mappers -> Target IR -> target_writers -> output file`

`target_writers` only writes already prepared target data.

## Current structure

```text
target_writers/
  __init__.py
  cmg/
    __init__.py
    generate_service.py
    writer_pipeline.py
  petrel/
    __init__.py
    generate_service.py
    writer_pipeline.py
```

## Responsibility split

### `generate_service.py`

- external entry for `generate_cmg()` or `generate_petrel()`
- load JSON if needed
- normalize and standardize IR
- call `target_mappers` to build target IR
- run preflight / confidence / report logic
- call writer pipeline
- persist output file

### `writer_pipeline.py`

- pure target file writing flow
- section-by-section output layout
- local formatting helpers
- no source parsing logic
- no target mapping logic
- no cross-layer orchestration logic

## Boundary rule

If a rule answers "how should CMG/Petrel target data be written", keep it in `target_writers`.

If a rule answers "how should Standard IR become CMG/Petrel target shape", keep it in `target_mappers`.

If a rule answers "what is physically/business correct", keep it in `domain_logic`.
