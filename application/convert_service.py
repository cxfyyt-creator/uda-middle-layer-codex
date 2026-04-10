from pathlib import Path

from infra.project_paths import CMG_OUTPUT_DIR, JSON_OUTPUT_DIR

from .generate_service import generate_cmg_from_standard
from .parse_service import parse_petrel_to_standard


def convert_petrel_to_cmg(input_file, json_output=None, cmg_output=None):
    input_path = Path(input_file)
    json_out = Path(json_output) if json_output else JSON_OUTPUT_DIR / f"{input_path.stem}_parsed.json"
    cmg_out = Path(cmg_output) if cmg_output else CMG_OUTPUT_DIR / f"{input_path.stem}_converted.dat"
    data = parse_petrel_to_standard(input_path, output_json=json_out)
    generate_cmg_from_standard(data, cmg_out)
    return {
        "data": data,
        "json_output": json_out,
        "target_output": cmg_out,
    }
