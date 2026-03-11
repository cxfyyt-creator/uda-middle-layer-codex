from __future__ import annotations

import argparse
import json
from pathlib import Path

from generators.cmg_generator import generate_cmg
from parsers.cmg_parser import parse_cmg


def _default_output_for_parse(input_path: Path) -> Path:
    out_dir = Path("outputs/json")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{input_path.stem}_parsed.json"


def _default_output_for_generate(input_path: Path) -> Path:
    out_dir = Path("outputs/cmg")
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem.replace("_parsed", "")
    return out_dir / f"{stem}_roundtrip.dat"


def cmd_parse_cmg(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else _default_output_for_parse(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    parse_cmg(str(input_path), str(output_path))
    print(f"OK: parsed CMG -> JSON: {output_path}")


def cmd_generate_cmg(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else _default_output_for_generate(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)
    generate_cmg(data, output_path)
    print(f"OK: generated JSON -> CMG: {output_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="UDA middle layer CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_parse = sub.add_parser("parse-cmg", help="Parse CMG .dat to universal JSON")
    p_parse.add_argument("input", help="Path to input CMG .dat file")
    p_parse.add_argument("-o", "--output", help="Output JSON path")
    p_parse.set_defaults(func=cmd_parse_cmg)

    p_gen = sub.add_parser("generate-cmg", help="Generate CMG .dat from universal JSON")
    p_gen.add_argument("input", help="Path to input universal JSON file")
    p_gen.add_argument("-o", "--output", help="Output CMG .dat path")
    p_gen.set_defaults(func=cmd_generate_cmg)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
