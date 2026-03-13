#!/usr/bin/env python3
# =============================================================================
# main.py  —  UDA Middle Layer 统一入口
# =============================================================================

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from parsers.petrel_parser       import parse_petrel
from parsers.cmg_parser          import parse_cmg
from generators.cmg_generator    import generate_cmg
from generators.petrel_generator import generate_petrel


def cmd_parse_petrel(args):
    src = Path(args.input)
    out_dir = Path(args.output) if args.output else Path("outputs/json")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{src.stem}_parsed.json"
    d = parse_petrel(src, str(out))
    g = d["grid"]
    print(f"parse-petrel OK")
    print(f"  Grid: {g.get('ni')} x {g.get('nj')} x {g.get('nk')}  type={g.get('grid_type')}")
    print(f"  PVTO rows: {len(d['fluid'].get('pvto_table',{}).get('rows',[]))}")
    print(f"  PVDG rows: {len(d['fluid'].get('pvdg_table',{}).get('rows',[]))}")
    print(f"  SWFN rows: {len(d['rockfluid'].get('swfn_table',{}).get('rows',[]))}")
    print(f"  Wells: {len(d['wells'])}")
    print(f"  Sim days: {d.get('_total_sim_time', 0):.1f}")
    unk = list(d.get("unknown_keywords", {}).keys())
    if unk:
        print(f"  Unknown keywords: {unk}")
    print(f"  JSON: {out}")


def cmd_parse_cmg(args):
    src = Path(args.input)
    out_dir = Path(args.output) if args.output else Path("outputs/json")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{src.stem}_parsed.json"
    d = parse_cmg(src, str(out))
    g = d["grid"]
    print(f"parse-cmg OK")
    print(f"  Grid: {g.get('ni')} x {g.get('nj')} x {g.get('nk')}  type={g.get('grid_type')}")
    print(f"  PVT rows: {len(d['fluid'].get('pvt_table',{}).get('rows',[]))}")
    print(f"  Wells: {len(d['wells'])}")
    print(f"  JSON: {out}")


def cmd_generate_cmg(args):
    src = Path(args.input)
    out_dir = Path(args.output) if args.output else Path("outputs/cmg")
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = src.stem.replace("_parsed", "")
    out = out_dir / f"{stem}_converted.dat"
    generate_cmg(src, str(out))
    print(f"generate-cmg OK  ->  {out}")


def cmd_generate_petrel(args):
    src = Path(args.input)
    out_dir = Path(args.output) if args.output else Path("outputs/petrel")
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = src.stem.replace("_parsed", "")
    out = out_dir / f"{stem}_converted.DATA"
    generate_petrel(src, str(out))
    print(f"generate-petrel OK  ->  {out}")


def main():
    p = argparse.ArgumentParser(description="UDA Middle Layer — Eclipse <-> CMG")
    sub = p.add_subparsers(dest="command", required=True)
    for cmd in ["parse-petrel","parse-cmg","generate-cmg","generate-petrel"]:
        sp = sub.add_parser(cmd)
        sp.add_argument("input")
        sp.add_argument("-o","--output")
    args = p.parse_args()
    {
        "parse-petrel":    cmd_parse_petrel,
        "parse-cmg":       cmd_parse_cmg,
        "generate-cmg":    cmd_generate_cmg,
        "generate-petrel": cmd_generate_petrel,
    }[args.command](args)

if __name__ == "__main__":
    main()