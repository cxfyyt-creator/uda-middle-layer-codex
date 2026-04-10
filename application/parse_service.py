from source_readers.cmg import parse_cmg
from source_readers.petrel import parse_petrel

from .standardize_service import build_and_validate_standard_ir, write_json_file


def parse_petrel_to_standard(input_file, output_json=None):
    raw = parse_petrel(input_file)
    data = build_and_validate_standard_ir(raw)
    if output_json:
        write_json_file(output_json, data)
    return data


def parse_cmg_to_standard(input_file, output_json=None):
    raw = parse_cmg(input_file)
    data = build_and_validate_standard_ir(raw)
    if output_json:
        write_json_file(output_json, data)
    return data
