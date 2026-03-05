
"""
build_reports.py
Automation entrypoint: generate Excel benchmark pack from CSVs.

Usage:
  python build_reports.py --core salary_data.csv --payroll actuals_payroll.csv --market Market_salary.csv --out PCI_Salary_Benchmark_Pack.xlsx

Optional:
  --include "JK Cement" --include "Union Cement Company"  (repeatable)
"""
from __future__ import annotations
import argparse
from pathlib import Path

import pandas as pd

from salary_engine import load_csvs, build_engine
from report_builder import build_excel_pack


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", required=True, help="Path to salary_data.csv")
    ap.add_argument("--payroll", required=True, help="Path to actuals_payroll.csv")
    ap.add_argument("--market", required=True, help="Path to Market_salary.csv")
    ap.add_argument("--out", required=True, help="Output .xlsx path")
    ap.add_argument("--include", action="append", default=None, help="Competitor company column to include (repeatable)")
    args = ap.parse_args()

    core_df, payroll_df, market_df = load_csvs(args.core, args.payroll, args.market)
    res = build_engine(core_df, payroll_df, market_df, competitor_include=args.include)
    xlsx = build_excel_pack(res.role_df, res.emp_df)

    out_path = Path(args.out)
    out_path.write_bytes(xlsx)
    print(f"Saved: {out_path.resolve()}")


if __name__ == "__main__":
    main()
