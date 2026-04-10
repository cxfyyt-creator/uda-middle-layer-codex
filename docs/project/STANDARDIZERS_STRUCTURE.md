# Standardizers Structure

## Purpose

`standardizers/` is the pipeline that turns Source IR into Standard IR.

It should own semantic normalization, not source parsing and not target formatting.

## Current structure

```text
standardizers/
  __init__.py
  standardize_pipeline.py
  section_normalizers.py
  timeline_builder.py
  model_assembly.py
```

## Responsibility split

### `standardize_pipeline.py`

- orchestrates the standardization flow
- exposes `build_standard_ir()`
- exposes `normalize_standard_ir()`

### `section_normalizers.py`

- normalizes section-level semantics
- applies domain logic
- upgrades partially aligned payloads into Standard IR shape

### `timeline_builder.py`

- builds `timeline_events`
- keeps schedule-event extraction out of the main pipeline file

### `model_assembly.py`

- assembles the final `StandardModel`
- keeps structural packaging separate from semantic normalization

## Boundary rule

If logic answers "how should this source meaning be normalized into Standard IR", keep it in `standardizers/`.

If logic answers "how should Standard IR be packaged as a complete contract object", keep it in `model_assembly.py`.

If logic answers "how should a target format rebuild its own keywords", keep it out of `standardizers/` and put it in `target_mappers/` or `target_writers/`.
