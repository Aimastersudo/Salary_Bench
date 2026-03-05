
"""
salary_engine.py
Reusable data cleaning + benchmark calculation engine for PCI Salary Benchmark project.
- Reads 3 CSVs: salary_data.csv (core role table), actuals_payroll.csv (employee list), Market_salary.csv (competitor ranges)
- Normalizes designations, departments
- Computes competitor midpoints per role
- Computes Benchmark Low/Mid/High (based on competitor midpoints)
- Computes Market Avg (mean of competitor midpoints)
- Computes variance/gap vs market
- Produces:
    role_df: one row per (role, department, employee type) with headcount
    emp_df : one row per employee with market benchmarks
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def _master_clean(text: object) -> str:
    t = str(text).strip()
    if t.lower() in {"nan", "none"}:
        return ""
    t = t.title()
    t = " ".join(t.split())
    t = t.replace("Co-Ordinator", "Coordinator").replace("–", "-").replace(" / ", "/")
    return t


_RANGE_RE = re.compile(r"^\s*(?P<a>[\d,\.]+)\s*(?:-|–|to)\s*(?P<b>[\d,\.]+)\s*$", re.IGNORECASE)


def parse_salary_range(v: object) -> Tuple[float, float, float]:
    """
    Parse a salary cell like:
        "15,000 - 20,000" -> (15000, 20000, 17500)
        "9000" -> (9000, 9000, 9000)
        "-" or blank -> (nan, nan, nan)
    Returns (low, high, mid) as floats.
    """
    s = str(v).replace("AED", "").strip()
    if s in {"-", "", "nan", "None"}:
        return (np.nan, np.nan, np.nan)

    s = s.replace(",", "")
    m = _RANGE_RE.match(s)
    if m:
        a = float(m.group("a"))
        b = float(m.group("b"))
        low, high = (a, b) if a <= b else (b, a)
        return (low, high, (low + high) / 2.0)

    # try single number
    try:
        x = float(s)
        return (x, x, x)
    except Exception:
        return (np.nan, np.nan, np.nan)


@dataclass
class EngineResult:
    role_df: pd.DataFrame
    emp_df: pd.DataFrame
    competitor_columns: List[str]


def build_engine(
    core_df: pd.DataFrame,
    payroll_df: pd.DataFrame,
    market_df: pd.DataFrame,
    competitor_include: Optional[List[str]] = None,
) -> EngineResult:
    """
    Build cleaned + merged datasets.
    competitor_include: which competitor columns to include in benchmark calculations.
    """
    # strip columns
    for d in (core_df, payroll_df, market_df):
        d.columns = d.columns.str.strip()

    # standardize keys
    core_df["Match_Key"] = core_df["Designation"].apply(_master_clean)
    payroll_df["Match_Key"] = payroll_df["Designation"].apply(_master_clean)
    market_df["Match_Key"] = market_df["Designation"].apply(_master_clean)

    # known bridge for payroll truncations
    bridge = {
        "Asst.Public Relation Offi": "Asst. Public Relation Officer",
        "Asst.External Relationship Manager": "Asst. External Relationship Manager",
        "Junior Engineer ( Instrum": "Junior Engineer (Instrumentation)",
        "Truck Cum Shovel Operato": "Truck Cum Shovel Operator",
        "Junior It Help Desk Suppo": "Junior It Help Desk Support",
        "Dy.Chief Engineer(Electri": "Dy. Chief Engineer (Electrical)",
        "Assistant Engineer (Pro": "Assistant Engineer (Production)",
        "Chief Engineer (Mech)": "Chief Engineer (Mechanical)",
        "Assistant Engineer (Mech)": "Assistant Engineer (Mechanical)",
        "Senior Engineer(Technical)": "Senior Engineer (Technical)",
        "Finance Co-Ordinator": "Finance Coordinator",
        "Marketing Co-Ordinator": "Marketing Coordinator",
        "Plant Co-Ordinator": "Plant Coordinator",
        "Sales Co-Ordinator": "Sales Coordinator",
        "Senior Sales And Logistic": "Senior Sales & Logistics",
        "Asst.Security Manager": "Asst. Security Manager",
        "Asst.Purchase Officer": "Asst. Purchase Officer",
        "Truck Driver - Bulker": "Truck Driver - Bulker",
        "Dy.Chief Engineer(Mech)": "Dy. Chief Engineer (Mechanical)",
    }
    payroll_df["Match_Key"] = payroll_df["Match_Key"].replace(bridge)

    # department fixes
    dept_fix = {
        "HR Administration": "HR",
        "Information technology": "IT",
        "Quality Control": "QC",
        "Sales and Logistics": "Sales & Logistics",
        "Stores Section": "Stores",
        "Procurment": "Procurement",
    }
    if "Department" in payroll_df.columns:
        payroll_df["Department"] = payroll_df["Department"].replace(dept_fix)
    if "Department" in core_df.columns:
        core_df["Department"] = core_df["Department"].replace(dept_fix)

    # split core_df rows where Department has "A/B"
    rows = []
    for _, row in core_df.iterrows():
        dv = str(row.get("Department", "") or "")
        if "/" in dv:
            for sd in [s.strip() for s in dv.split("/") if s.strip()]:
                nr = row.copy()
                nr["Department"] = sd
                rows.append(nr)
        else:
            rows.append(row)
    core_df = pd.DataFrame(rows)

    # competitors columns
    competitor_cols = [c for c in market_df.columns if c not in {"#", "Designation", "Match_Key"}]
    if competitor_include:
        competitor_cols = [c for c in competitor_cols if c in set(competitor_include)]

    # compute competitor midpoints per role
    m = market_df[["Match_Key"] + competitor_cols].copy()
    for c in competitor_cols:
        lows, highs, mids = zip(*m[c].apply(parse_salary_range))
        m[f"{c}__low"] = lows
        m[f"{c}__high"] = highs
        m[f"{c}__mid"] = mids

    mid_cols = [f"{c}__mid" for c in competitor_cols]
    m["Benchmark_Low"] = m[mid_cols].min(axis=1, skipna=True)
    m["Benchmark_Mid"] = m[mid_cols].median(axis=1, skipna=True)
    m["Benchmark_High"] = m[mid_cols].max(axis=1, skipna=True)
    m["Market_Avg"] = m[mid_cols].mean(axis=1, skipna=True)

    bench_cols = ["Match_Key", "Benchmark_Low", "Benchmark_Mid", "Benchmark_High", "Market_Avg"] + competitor_cols
    # keep original competitor columns for display (strings) but benchmarks numeric
    m_clean = pd.merge(
        market_df[["Match_Key"] + competitor_cols],
        m[["Match_Key", "Benchmark_Low", "Benchmark_Mid", "Benchmark_High", "Market_Avg"]],
        on="Match_Key",
        how="left",
    ).drop_duplicates(subset=["Match_Key"])

    # salary columns numeric
    core_df["Your Salary (AED)"] = (
        core_df["Your Salary (AED)"].astype(str).str.replace(",", "", regex=False)
    )
    core_df["Your Salary (AED)"] = pd.to_numeric(core_df["Your Salary (AED)"], errors="coerce").fillna(0).round(0).astype(int)

    # merge role table with benchmarks
    role_df = pd.merge(core_df, m_clean, on="Match_Key", how="left")
    # fallbacks: if no market data, set market numbers equal to current salary
    for c in ["Benchmark_Low", "Benchmark_Mid", "Benchmark_High", "Market_Avg"]:
        role_df[c] = pd.to_numeric(role_df[c], errors="coerce")
        role_df[c] = role_df[c].fillna(role_df["Your Salary (AED)"])

    role_df["Variance %"] = (
        (role_df["Your Salary (AED)"] - role_df["Market_Avg"]) / role_df["Market_Avg"].replace(0, np.nan) * 100
    ).replace([np.inf, -np.inf], np.nan).fillna(0).round(0).astype(int)

    # payroll employees
    if "Salary" not in payroll_df.columns and " Salary " in payroll_df.columns:
        payroll_df["Salary"] = payroll_df[" Salary "]
    payroll_df["Salary"] = payroll_df["Salary"].astype(str).str.replace(",", "", regex=False)
    payroll_df["Salary"] = pd.to_numeric(payroll_df["Salary"], errors="coerce").fillna(0).round(0).astype(int)

    # tenure
    payroll_df["DOJ"] = pd.to_datetime(payroll_df.get("Date of Joining"), errors="coerce")
    today = pd.to_datetime("today")
    payroll_df["Tenure_Y"] = ((today - payroll_df["DOJ"]).dt.days / 365.25).fillna(0).astype(int)
    payroll_df["Tenure_M"] = (((today - payroll_df["DOJ"]).dt.days % 365.25) / 30.44).fillna(0).astype(int)
    payroll_df["Tenure_Text"] = payroll_df.apply(
        lambda x: f"{int(x['Tenure_Y'])}y {int(x['Tenure_M'])}m" if pd.notna(x["DOJ"]) else "N/A",
        axis=1,
    )

    emp_df = pd.merge(payroll_df, m_clean, on="Match_Key", how="left")
    for c in ["Benchmark_Low", "Benchmark_Mid", "Benchmark_High", "Market_Avg"]:
        emp_df[c] = pd.to_numeric(emp_df[c], errors="coerce")
        emp_df[c] = emp_df[c].fillna(emp_df["Salary"])

    emp_df["Gap %"] = (
        (emp_df["Salary"] - emp_df["Market_Avg"]) / emp_df["Market_Avg"].replace(0, np.nan) * 100
    ).replace([np.inf, -np.inf], np.nan).fillna(0).round(0).astype(int)
    emp_df["Gap (AED)"] = (emp_df["Salary"] - emp_df["Market_Avg"]).astype(int)

    # employee type mapping from core_df
    t_map = dict(zip(core_df["Match_Key"], core_df.get("Employee Type", pd.Series(index=core_df.index, data="Worker"))))
    emp_df["Employee Type"] = emp_df["Match_Key"].map(t_map).fillna("Worker")

    # headcount allocation by role+dept (and fix mismatch)
    hc_d = payroll_df.groupby(["Match_Key", "Department"]).size().reset_index(name="HC_D")
    role_df = pd.merge(role_df, hc_d, on=["Match_Key", "Department"], how="left")
    role_df["Live_HC"] = role_df["HC_D"].fillna(0).astype(int)

    alloc = role_df.groupby("Match_Key")["Live_HC"].sum().reset_index(name="Alloc")
    act = payroll_df.groupby("Match_Key").size().reset_index(name="Actual")
    cm = pd.merge(act, alloc, on="Match_Key", how="left")
    res = cm[cm["Actual"] > cm["Alloc"].fillna(0)]
    for _, r in res.iterrows():
        key = r["Match_Key"]
        rem = int(r["Actual"] - r["Alloc"])
        idx = role_df[role_df["Match_Key"] == key].index
        if len(idx) > 0:
            role_df.at[idx[0], "Live_HC"] += rem

    return EngineResult(role_df=role_df, emp_df=emp_df, competitor_columns=competitor_cols)


def load_csvs(core_path: str, payroll_path: str, market_path: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    core_df = pd.read_csv(core_path, encoding="utf-8-sig")
    payroll_df = pd.read_csv(payroll_path, encoding="utf-8-sig")
    market_df = pd.read_csv(market_path, encoding="utf-8-sig")
    return core_df, payroll_df, market_df
