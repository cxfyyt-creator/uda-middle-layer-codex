# Application Structure

## Purpose

`application/` is the orchestration layer.

It coordinates full use cases, but it should not own parsing details, target mapping rules, or file-writing details.

## Current structure

```text
application/
  __init__.py
  parse_service.py
  standardize_service.py
  generate_service.py
  convert_service.py
  quick_convert.py
```

## Responsibility split

### `parse_service.py`

- orchestrates `source_readers`
- converts raw parse result into Standard IR
- writes parsed JSON when needed

### `standardize_service.py`

- loads JSON payloads
- upgrades / normalizes existing IR
- builds Standard IR from raw payload
- runs validation

### `generate_service.py`

- accepts Standard IR or JSON path
- ensures input is valid Standard IR
- delegates to `target_writers`

### `convert_service.py`

- coordinates end-to-end conversion flows
- example: `petrel -> standard json -> cmg`

## Boundary rule

If logic answers "what steps should happen in this use case", keep it in `application/`.

If logic answers "how to parse source format", keep it in `source_readers/`.

If logic answers "how to standardize source semantics", keep it in `standardizers/`.

If logic answers "how to write target format", keep it in `target_writers/`.
