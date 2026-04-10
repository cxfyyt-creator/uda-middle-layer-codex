import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from application.convert_service import convert_petrel_to_cmg


def main():
    if len(sys.argv) < 2:
        print("Usage: python application/quick_convert.py <input DATA file>")
        sys.exit(1)
    input_file = Path(sys.argv[1])
    if not input_file.exists():
        print(f"Input file not found: {input_file}")
        sys.exit(1)
    print(f"\n[1/2] Parsing {input_file.name} ...")
    result = convert_petrel_to_cmg(input_file)
    data = result["data"]
    json_out = result["json_output"]
    cmg_out = result["target_output"]
    grid = data["grid"]
    print(f"  Grid:      {grid.get('ni')} x {grid.get('nj')} x {grid.get('nk')}")
    print(f"  PVTO rows: {len(data['fluid'].get('pvto_table', {}).get('rows', []))}")
    print(f"  PVDG rows: {len(data['fluid'].get('pvdg_table', {}).get('rows', []))}")
    print(f"  Wells:     {len(data['wells'])}")
    print(f"  Start:     {data['meta'].get('start_date')}")
    print(f"  JSON:      {json_out}")
    print(f"\n[2/2] Generating CMG .dat ...")
    print(f"  CMG:       {cmg_out}")


if __name__ == "__main__":
    main()
