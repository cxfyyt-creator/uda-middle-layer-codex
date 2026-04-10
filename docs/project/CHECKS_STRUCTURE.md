# Checks Structure

## Purpose

`checks/` is the verification layer.

It should separate schema validation, physics validation, and target readiness checks.

## Current structure

```text
checks/
  __init__.py
  schema/
    __init__.py
    standard_model_schema.py
  physics/
    __init__.py
    reservoir_physics.py
    fluid_physics.py
    rockfluid_physics.py
    well_physics.py
  readiness/
    __init__.py
    target_readiness.py
    format_coverage_checks.py
    capability_checks.py
    completeness_checks.py
    confidence_checks.py
    generation_gate.py
    issue_reporting.py
```

## Responsibility split

### `schema/`

- validates Standard IR structure
- owns Pydantic schemas
- should remain the single entry for contract-shape validation

### `physics/`

- will hold cross-field physical consistency checks
- example: active cell vs porosity, saturation ordering, pressure-depth consistency
- current files:
- `reservoir_physics.py`
- `fluid_physics.py`
- `rockfluid_physics.py`
- `well_physics.py`

### `readiness/`

- will hold target generation preflight checks
- will hold confidence and completeness checks before writing output
- current files:
- `target_readiness.py`
- `format_coverage_checks.py`
- `capability_checks.py`
- `completeness_checks.py`
- `confidence_checks.py`
- `generation_gate.py`
- `issue_reporting.py`

## Boundary rule

If logic answers "is this payload structurally a valid Standard IR", keep it in `schema/`.

If logic answers "is this payload physically self-consistent", keep it in `physics/`.

If logic answers "is this payload ready for a specific writer/backend", keep it in `readiness/`.
