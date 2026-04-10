from target_writers.cmg import generate_cmg
from target_writers.petrel import generate_petrel

from .standardize_service import ensure_standard_model


def generate_cmg_from_standard(data_or_path, output_file):
    data = ensure_standard_model(data_or_path, strict=True)
    return generate_cmg(data, str(output_file))


def generate_petrel_from_standard(data_or_path, output_file):
    data = ensure_standard_model(data_or_path, strict=True)
    return generate_petrel(data, str(output_file))
