#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from application import (
    ensure_standard_model,
    generate_cmg_from_standard,
    generate_petrel_from_standard,
    parse_cmg_to_standard,
    parse_petrel_to_standard,
)
from infra.project_paths import CMG_OUTPUT_DIR, JSON_OUTPUT_DIR, PETREL_OUTPUT_DIR


def cmd_parse_petrel(args):
    src = Path(args.input)
    out_dir = Path(args.output) if args.output else JSON_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{src.stem}_parsed.json"
    data = parse_petrel_to_standard(src, output_json=out)
    grid = data["grid"]
    print("parse-petrel OK")
    print(f"  Grid: {grid.get('ni')} x {grid.get('nj')} x {grid.get('nk')}  type={grid.get('grid_type')}")
    print(f"  PVTO rows: {len(data['fluid'].get('pvto_table', {}).get('rows', []))}")
    print(f"  PVDG rows: {len(data['fluid'].get('pvdg_table', {}).get('rows', []))}")
    print(f"  SWFN rows: {len(data['rockfluid'].get('swfn_table', {}).get('rows', []))}")
    print(f"  Wells: {len(data['wells'])}")
    print(f"  Timeline events: {len(data.get('timeline_events', []))}")
    print(f"  JSON: {out}")


def cmd_parse_cmg(args):
    src = Path(args.input)
    out_dir = Path(args.output) if args.output else JSON_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{src.stem}_parsed.json"
    data = parse_cmg_to_standard(src, output_json=out)
    grid = data["grid"]
    print("parse-cmg OK")
    print(f"  Grid: {grid.get('ni')} x {grid.get('nj')} x {grid.get('nk')}  type={grid.get('grid_type')}")
    print(f"  PVT rows: {len(data['fluid'].get('pvt_table', {}).get('rows', []))}")
    print(f"  Wells: {len(data['wells'])}")
    print(f"  Timeline events: {len(data.get('timeline_events', []))}")
    print(f"  JSON: {out}")


def cmd_generate_cmg(args):
    src = Path(args.input)
    out_dir = Path(args.output) if args.output else CMG_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{src.stem.replace('_parsed', '')}_converted.dat"
    data = ensure_standard_model(src, strict=True)
    generate_cmg_from_standard(data, out)
    print(f"generate-cmg OK  ->  {out}")


def cmd_generate_petrel(args):
    src = Path(args.input)
    out_dir = Path(args.output) if args.output else PETREL_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{src.stem.replace('_parsed', '')}_converted.DATA"
    data = ensure_standard_model(src, strict=True)
    generate_petrel_from_standard(data, out)
    print(f"generate-petrel OK  ->  {out}")


def main():
    parser = argparse.ArgumentParser(description="UDA Middle Layer CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ["parse-petrel", "parse-cmg", "generate-cmg", "generate-petrel"]:
        sub_parser = sub.add_parser(command)
        sub_parser.add_argument("input")
        sub_parser.add_argument("-o", "--output")
    args = parser.parse_args()
    {
        "parse-petrel": cmd_parse_petrel,
        "parse-cmg": cmd_parse_cmg,
        "generate-cmg": cmd_generate_cmg,
        "generate-petrel": cmd_generate_petrel,
    }[args.command](args)


if __name__ == "__main__":
    main()
