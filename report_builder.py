
"""
report_builder.py
Exports a benchmark pack to Excel (and optional PDF later).
"""
from __future__ import annotations
from io import BytesIO
from typing import Optional

import pandas as pd


def build_excel_pack(role_df: pd.DataFrame, emp_df: pd.DataFrame) -> bytes:
    """
    Returns an .xlsx file as bytes with:
      - Summary
      - Role_Benchmark
      - Employee_Gaps
      - Dept_Summary
    """
    out = BytesIO()

    # Summary metrics
    total_hc = int(role_df["Live_HC"].sum()) if "Live_HC" in role_df.columns else len(emp_df)
    avg_gap = float(role_df["Variance %"].mean()) if "Variance %" in role_df.columns and len(role_df) else 0.0
    crit_roles = int((role_df["Variance %"] <= -20).sum()) if "Variance %" in role_df.columns else 0

    summary = pd.DataFrame(
        {
            "Metric": ["Total Headcount", "Designations", "Avg Market Gap %", "Critical Roles (<= -20%)"],
            "Value": [total_hc, len(role_df), round(avg_gap, 0), crit_roles],
        }
    )

    role_cols = [
        "Designation", "Department", "Employee Type", "Live_HC",
        "Your Salary (AED)", "Benchmark_Low", "Benchmark_Mid", "Benchmark_High", "Market_Avg", "Variance %"
    ]
    role_export = role_df[[c for c in role_cols if c in role_df.columns]].copy()
    role_export = role_export.sort_values(["Variance %", "Department", "Designation"], ascending=[True, True, True])

    emp_cols = [
        "Employee ID", "Employee Name", "Designation", "Department", "Date of Joining",
        "Tenure_Text", "Employee Type",
        "Salary", "Benchmark_Low", "Benchmark_Mid", "Benchmark_High", "Market_Avg", "Gap %", "Gap (AED)"
    ]
    emp_export = emp_df[[c for c in emp_cols if c in emp_df.columns]].copy()
    if "Gap %" in emp_export.columns:
        emp_export = emp_export.sort_values("Gap %")

    dept_summary = (
        role_df.groupby("Department")
        .agg(
            Headcount=("Live_HC", "sum"),
            Avg_GapPct=("Variance %", "mean"),
            Critical_Roles=("Variance %", lambda s: (s <= -20).sum()),
        )
        .reset_index()
        .sort_values("Avg_GapPct")
    )
    dept_summary["Avg_GapPct"] = dept_summary["Avg_GapPct"].round(0)

    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        role_export.to_excel(writer, sheet_name="Role_Benchmark", index=False)
        emp_export.to_excel(writer, sheet_name="Employee_Gaps", index=False)
        dept_summary.to_excel(writer, sheet_name="Dept_Summary", index=False)

        # basic formatting
        wb = writer.book
        fmt_header = wb.add_format({"bold": True, "bg_color": "#DCE6F1", "border": 1})
        fmt_int = wb.add_format({"num_format": "#,##0", "border": 1})
        fmt_pct = wb.add_format({"num_format": "0", "border": 1})
        fmt_text = wb.add_format({"border": 1})

        def format_sheet(name: str):
            ws = writer.sheets[name]
            df = {"Summary": summary, "Role_Benchmark": role_export, "Employee_Gaps": emp_export, "Dept_Summary": dept_summary}[name]
            # header
            for col, val in enumerate(df.columns):
                ws.write(0, col, val, fmt_header)
                # width
                width = max(12, min(42, int(df[val].astype(str).map(len).quantile(0.9)) + 2))
                ws.set_column(col, col, width)
            # formats
            for i, colname in enumerate(df.columns):
                if any(k in colname for k in ["Salary", "Benchmark", "Market", "Gap (AED)", "Headcount", "Live_HC"]):
                    ws.set_column(i, i, None, fmt_int)
                elif "%" in colname or "Pct" in colname or colname in {"Variance %", "Gap %"}:
                    ws.set_column(i, i, None, fmt_pct)
                else:
                    ws.set_column(i, i, None, fmt_text)
            ws.freeze_panes(1, 0)

        for sheet in ["Summary", "Role_Benchmark", "Employee_Gaps", "Dept_Summary"]:
            format_sheet(sheet)

    return out.getvalue()
