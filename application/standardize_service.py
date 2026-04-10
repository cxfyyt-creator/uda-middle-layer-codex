import json
from pathlib import Path

from checks import validate_standard_model
from standardizers import build_standard_ir, normalize_standard_ir


def load_json_file(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json_file(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def build_and_validate_standard_ir(raw, strict=True):
    standard = build_standard_ir(raw)
    validate_standard_model(standard, strict=strict)
    return standard


def ensure_standard_model(data_or_path, strict=True):
    if isinstance(data_or_path, (str, Path)):
        payload = load_json_file(Path(data_or_path))
    else:
        payload = data_or_path
    data = normalize_standard_ir(payload) if payload.get("uda_version") else build_and_validate_standard_ir(payload, strict=strict)
    validate_standard_model(data, strict=strict)
    return data
