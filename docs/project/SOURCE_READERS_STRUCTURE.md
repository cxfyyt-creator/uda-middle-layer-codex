# Source Readers Structure

## Current structure

`source_readers/` is now split by source format first:

```text
source_readers/
  __init__.py
  cmg/
    __init__.py
    reader_pipeline.py
    parse_service.py
    token_stream.py
    value_builders.py
    keyword_handlers/
      fluid_props.py
      wells_schedule.py
  petrel/
    __init__.py
    reader_pipeline.py
    parse_service.py
    token_stream.py
    value_builders.py
    keyword_handlers/
      pvt_solution.py
      edit_keywords.py
      run_control.py
      wells_schedule.py
```

## Responsibility split

`reader_pipeline.py`
- owns parser state
- owns token walking
- owns keyword dispatch
- owns source-format parsing behavior

`parse_service.py`
- owns external entrypoint `parse_*()`
- owns JSON write-out
- owns parse report generation

`token_stream.py`
- owns source-format tokenization helpers
- owns comment stripping and token-level constants

`value_builders.py`
- owns scalar/array/table construction helpers
- owns repeat-expansion and numeric parsing helpers

`keyword_handlers/`
- owns keyword-family parsing logic
- groups related parsing behavior by business area instead of keeping everything inside one parser class

`__init__.py`
- exports stable package-level entrypoints

## Why this split matters

Before this change, one file mixed three roles:

- parser core
- parse orchestration
- parse report output

That makes later decomposition harder, because every small change touches the same oversized file.

Now the next decomposition can happen inside each format package without moving the external entrypoint again.

## Next decomposition target

The next safe split inside each source reader is:

- `token_stream.py`
- `value_builders.py`
- `keyword_handlers/`
- `reader_pipeline.py`

The first three are now landed in the current structure.

The rule is:

- if code is generic token/state handling, move it out of the parser class
- if code is specific to one keyword family, move it into a handler module
- keep `reader_pipeline.py` as the thin coordinator, not the final storage place for every handler
