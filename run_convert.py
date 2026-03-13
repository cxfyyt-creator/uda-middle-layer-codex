"""
一键运行脚本：Petrel .DATA -> JSON -> CMG .dat
用法：python run_convert.py SPE1_ODEHIMPES.DATA
"""
import sys
import json
from pathlib import Path

# 把 parsers/ 和 generators/ 加入模块搜索路径
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "parsers"))
sys.path.insert(0, str(ROOT / "generators"))

from petrel_parser import parse_petrel
from cmg_generator import generate_cmg

def main():
    if len(sys.argv) < 2:
        print("用法: python run_convert.py <输入的.DATA文件>")
        print("例如: python run_convert.py SPE1_ODEHIMPES.DATA")
        sys.exit(1)

    input_file = Path(sys.argv[1])
    if not input_file.exists():
        print(f"错误：找不到文件 {input_file}")
        sys.exit(1)

    # 创建输出目录
    json_dir = ROOT / "outputs" / "json"
    cmg_dir  = ROOT / "outputs" / "cmg"
    json_dir.mkdir(parents=True, exist_ok=True)
    cmg_dir.mkdir(parents=True, exist_ok=True)

    json_out = json_dir / f"{input_file.stem}_parsed.json"
    cmg_out  = cmg_dir  / f"{input_file.stem}_converted.dat"

    # 第一步：解析 Petrel .DATA -> JSON
    print(f"\n[1/2] 解析 {input_file.name} ...")
    data = parse_petrel(str(input_file), str(json_out))

    g = data["grid"]
    print(f"  网格:     {g.get('ni')} x {g.get('nj')} x {g.get('nk')}")
    print(f"  孔隙度:   {data['reservoir'].get('porosity',{}).get('value','?')}")
    print(f"  PVTO行数: {len(data['fluid'].get('pvto_table',{}).get('rows',[]))}")
    print(f"  PVDG行数: {len(data['fluid'].get('pvdg_table',{}).get('rows',[]))}")
    print(f"  井数量:   {len(data['wells'])}")
    print(f"  开始日期: {data['meta'].get('start_date')}")
    print(f"  -> JSON 已保存: {json_out}")

    # 第二步：生成 CMG .dat
    print(f"\n[2/2] 生成 CMG .dat ...")
    generate_cmg(data, str(cmg_out))
    print(f"  -> CMG  已保存: {cmg_out}")

    print("\n完成！")

if __name__ == "__main__":
    main()