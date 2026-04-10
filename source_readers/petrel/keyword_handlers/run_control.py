from __future__ import annotations

from source_readers.petrel.token_stream import MONTH_MAP


def parse_start(parser, R):
    row = parser._read_until_slash()
    values = [str(token).strip("'") for token in row]
    if len(values) >= 3:
        try:
            day = int(values[0])
            month = MONTH_MAP.get(values[1].upper()[:3], 1)
            year = int(values[2])
            R["meta"]["start_date"] = f"{year:04d}-{month:02d}-{day:02d}"
        except (ValueError, IndexError):
            pass


def parse_load(parser, R):
    row = parser._read_until_slash()
    values = [str(token).strip("'").strip() for token in row]
    if not values:
        return
    base_path = parser._resolve_related_datafile(values[0])
    if not base_path:
        parser._record_unparsed(parser._last_lineno(), f"LOAD {values[0]}", reason="load target not found")
        return
    try:
        resolved_key = str(base_path.resolve()).lower()
    except Exception:
        resolved_key = str(base_path).lower()
    if resolved_key in parser._load_stack:
        parser._record_unparsed(parser._last_lineno(), f"LOAD {base_path.name}", reason="recursive load detected")
        return

    base_raw = parser.__class__(base_path, _load_stack=parser._load_stack | {resolved_key}).parse()
    parser._loaded_base_raw = base_raw
    parser._merge_loaded_base(R, base_raw)
    R["meta"]["load_source_file"] = base_path.name


def parse_restart(parser, R):
    row = parser._read_until_slash()
    values = [str(token).strip("'").strip() for token in row]
    if not values:
        return

    restart_name = values[0]
    restart_step = None
    if len(values) >= 2:
        try:
            restart_step = int(float(values[1]))
        except (ValueError, TypeError):
            restart_step = None

    if parser._loaded_base_raw is None:
        base_path = parser._resolve_related_datafile(restart_name)
        if base_path:
            try:
                resolved_key = str(base_path.resolve()).lower()
            except Exception:
                resolved_key = str(base_path).lower()
            if resolved_key not in parser._load_stack:
                parser._loaded_base_raw = parser.__class__(
                    base_path,
                    _load_stack=parser._load_stack | {resolved_key},
                ).parse()
                parser._merge_loaded_base(R, parser._loaded_base_raw)

    if parser._loaded_base_raw:
        checkpoints = parser._loaded_base_raw.get("_time_checkpoints") or [0.0]
        if restart_step is not None and checkpoints:
            idx = max(0, min(restart_step, len(checkpoints) - 1))
            parser._current_time = float(checkpoints[idx])
            parser._time_checkpoints = [parser._current_time]

    R["meta"]["restart_source_file"] = restart_name
    if restart_step is not None:
        R["meta"]["restart_step"] = restart_step
