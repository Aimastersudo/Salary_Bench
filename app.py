import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os
from datetime import datetime
from fpdf import FPDF

from salary_engine import load_csvs, build_engine
from report_builder import build_excel_pack

# -----------------------------
# Page config
# -----------------------------
st.set_page_config(
    page_title="PCI Salary Benchmark Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------
# Modern UI CSS
# -----------------------------
BASE_CSS = """
<style>
/* Fonts + base spacing */
html, body, [class*="css"]  { font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
.block-container { padding-top: 1.0rem; padding-bottom: 2.5rem; max-width: 1400px; }

/* Remove default top padding */
header { visibility: hidden; height: 0px; }

/* Cards */
.kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
@media (max-width: 1100px) { .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 650px)  { .kpi-grid { grid-template-columns: repeat(1, minmax(0, 1fr)); } }

.kpi-card {
  border-radius: 16px;
  padding: 16px 16px 14px 16px;
  border: 1px solid rgba(255,255,255,0.12);
  backdrop-filter: blur(8px);
}

.kpi-title { font-size: 12px; opacity: 0.75; margin-bottom: 6px; }
.kpi-value { font-size: 26px; font-weight: 700; line-height: 1.1; margin-bottom: 4px; }
.kpi-sub   { font-size: 12px; opacity: 0.75; }

.badge {
  display: inline-block;
  font-size: 11px;
  padding: 4px 8px;
  border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.14);
  opacity: 0.9;
  margin-left: 8px;
}

.section-title {
  font-size: 16px;
  font-weight: 700;
  margin: 12px 0 4px 0;
}

.muted { opacity: 0.75; }

hr.soft {
  border: none;
  border-top: 1px solid rgba(255,255,255,0.08);
  margin: 14px 0;
}

/* Table title row */
.table-head {
  display:flex;
  align-items:flex-end;
  justify-content:space-between;
  gap: 12px;
  margin-top: 10px;
  margin-bottom: 8px;
}

.small-help { font-size: 12px; opacity: 0.75; }

.insight {
  border-radius: 14px;
  padding: 14px 14px;
  border: 1px solid rgba(255,255,255,0.12);
}

/* Hide Streamlit footer */
footer { visibility: hidden; }
</style>
"""

LIGHT_THEME_CSS = """
<style>
/* Light theme card background */
.kpi-card { background: linear-gradient(135deg, rgba(0,0,0,0.03), rgba(0,0,0,0.01)); }
.insight  { background: rgba(0,0,0,0.02); }
</style>
"""

DARK_THEME_CSS = """
<style>
/* Dark theme card background */
.kpi-card { background: linear-gradient(135deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02)); }
.insight  { background: rgba(255,255,255,0.04); }
</style>
"""

# -----------------------------
# Theme state
# -----------------------------
if "theme_mode" not in st.session_state:
    st.session_state["theme_mode"] = "Dark"

def apply_theme(mode: str):
    st.markdown(BASE_CSS, unsafe_allow_html=True)
    if mode == "Light":
        st.markdown(LIGHT_THEME_CSS, unsafe_allow_html=True)
    else:
        st.markdown(DARK_THEME_CSS, unsafe_allow_html=True)

# -----------------------------
# Helpers
# -----------------------------
def fmt_aed(x):
    try:
        if pd.isna(x):
            return "-"
        return f"{float(x):,.0f}"
    except Exception:
        return "-"

def safe_pct(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "-"
    return f"{x:.1f}%"

def choose_plotly_template(mode: str):
    return "plotly_white" if mode == "Light" else "plotly_dark"

def build_kpi_card(title, value, subtitle="", badge_text=None):
    badge_html = f'<span class="badge">{badge_text}</span>' if badge_text else ""
    return f"""
    <div class="kpi-card">
      <div class="kpi-title">{title}{badge_html}</div>
      <div class="kpi-value">{value}</div>
      <div class="kpi-sub">{subtitle}</div>
    </div>
    """

def df_to_download_bytes(df: pd.DataFrame, filetype="csv"):
    if filetype == "csv":
        return df.to_csv(index=False).encode("utf-8")
    elif filetype == "xlsx":
        from io import BytesIO
        bio = BytesIO()
        with pd.ExcelWriter(bio, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Data")
        return bio.getvalue()
    return None

# -----------------------------
# PDF report
# -----------------------------
class SimplePDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 12)
        self.cell(0, 10, "Salary Benchmark Summary Report", ln=True, align="L")
        self.ln(2)

def export_pdf_summary(summary_lines, out_path):
    pdf = SimplePDF()
    pdf.add_page()
    pdf.set_font("Arial", "", 10)
    for line in summary_lines:
        pdf.multi_cell(0, 6, line)
    pdf.output(out_path)

# -----------------------------
# Sidebar (Uploads + scope)
# -----------------------------
st.sidebar.markdown("## ⚙️ Settings")

theme_mode = st.sidebar.radio(
    "Theme",
    ["Dark", "Light"],
    index=0 if st.session_state["theme_mode"] == "Dark" else 1,
    horizontal=True,
)
st.session_state["theme_mode"] = theme_mode
apply_theme(theme_mode)

with st.sidebar.expander("📥 Upload / Replace CSVs", expanded=False):
    st.caption("If you upload new files here, dashboard will use them immediately.")
    upl_market = st.file_uploader("Market_salary.csv", type=["csv"], key="upl_market")
    upl_payroll = st.file_uploader("actuals_payroll.csv", type=["csv"], key="upl_payroll")
    upl_core = st.file_uploader("salary_data.csv (optional)", type=["csv"], key="upl_core")

st.sidebar.markdown("---")

st.sidebar.markdown("### 📌 Benchmark Scope")
st.sidebar.caption("Select which competitor companies to include in benchmark calculations.")

# -----------------------------
# Load data (from uploads or local files)
# -----------------------------
DATA_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_MARKET = os.path.join(DATA_DIR, "Market_salary.csv")
DEFAULT_PAYROLL = os.path.join(DATA_DIR, "actuals_payroll.csv")
DEFAULT_CORE = os.path.join(DATA_DIR, "salary_data.csv")

def load_df_from_uploader(upl, fallback_path):
    if upl is not None:
        return pd.read_csv(upl)
    if os.path.exists(fallback_path):
        return pd.read_csv(fallback_path)
    return pd.DataFrame()

market_df = load_df_from_uploader(upl_market, DEFAULT_MARKET)
payroll_df = load_df_from_uploader(upl_payroll, DEFAULT_PAYROLL)
core_df = load_df_from_uploader(upl_core, DEFAULT_CORE)

# Basic validation / normalize columns
for df in [market_df, payroll_df, core_df]:
    if len(df) > 0:
        df.columns = [c.strip() for c in df.columns]

# Build engine (uses salary_engine module)
engine = None
try:
    engine = build_engine(market_df, payroll_df, core_df)
except Exception as e:
    engine = None
    st.error(f"Could not build engine: {e}")

# If engine is not available, show instructions
if engine is None:
    st.warning("Engine not ready. Please ensure CSV files are present and have correct columns.")
    st.stop()

# Determine competitor list from engine
competitors = engine.get("competitors", [])
if not competitors:
    competitors = sorted(list(set(market_df.get("Company", pd.Series([])).dropna().astype(str).tolist())))

selected_companies = st.sidebar.multiselect(
    "Competitor Companies",
    options=competitors,
    default=competitors,
)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📅 Snapshot")
st.sidebar.write(datetime.now().strftime("%d %b %Y • %I:%M %p"))

# -----------------------------
# Top header
# -----------------------------
colA, colB = st.columns([0.7, 0.3])
with colA:
    st.markdown("## 📊 PCI Salary Benchmark Dashboard")
    st.markdown('<div class="muted">Modern benchmarking view: PCI vs UAE cement market (select competitors in sidebar).</div>', unsafe_allow_html=True)
with colB:
    st.markdown("")
    st.markdown("")
    st.markdown(
        f'<div class="insight"><b>Scope:</b> {len(selected_companies)} companies<br/>'
        f'<b>Roles:</b> {engine["roles_count"]} &nbsp; • &nbsp; <b>Employees:</b> {engine["employees_count"]}</div>',
        unsafe_allow_html=True
    )

st.markdown('<hr class="soft"/>', unsafe_allow_html=True)

# -----------------------------
# Navigation tabs
# -----------------------------
tabs = st.tabs(["🏁 Executive", "🏢 Market", "👥 Employees", "🧭 Planner", "📤 Export"])

plot_template = choose_plotly_template(theme_mode)

# -----------------------------
# EXECUTIVE TAB
# -----------------------------
with tabs[0]:
    # Compute KPIs for selected scope
    kpis = engine["kpis"](selected_companies)

    k1 = build_kpi_card("PCI Avg Salary (AED)", fmt_aed(kpis["pci_avg"]), "Average across all employees")
    k2 = build_kpi_card("Market Avg (AED)", fmt_aed(kpis["market_avg"]), "Average midpoint across selected competitors")
    k3 = build_kpi_card("Avg Gap vs Market", safe_pct(kpis["avg_gap_pct"]), "Positive = PCI above market", badge_text=("Above" if kpis["avg_gap_pct"] and kpis["avg_gap_pct"] > 0 else "Below"))
    k4 = build_kpi_card("Critical Roles", f"{kpis['critical_roles']}", "Roles with gap below -10%")

    st.markdown(f'<div class="kpi-grid">{k1}{k2}{k3}{k4}</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-title">Top Insights</div>', unsafe_allow_html=True)

    insights = engine["insights"](selected_companies)
    left, right = st.columns([0.55, 0.45], gap="large")

    with left:
        st.markdown('<div class="insight">', unsafe_allow_html=True)
        st.markdown("**Key findings (auto):**")
        for line in insights["bullets"][:7]:
            st.write("• " + line)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="section-title">Gap Distribution</div>', unsafe_allow_html=True)
        hist_df = insights["gap_distribution"]
        if len(hist_df) > 0:
            fig = px.histogram(
                hist_df,
                x="GapPct",
                nbins=20,
                title="PCI vs Market Gap (%) across roles",
                template=plot_template,
            )
            fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=320)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Gap distribution not available.")

    with right:
        st.markdown('<div class="section-title">Roles to Watch</div>', unsafe_allow_html=True)
        watch_df = insights["watch_roles"]
        if len(watch_df) > 0:
            st.dataframe(watch_df, use_container_width=True, hide_index=True)
        else:
            st.info("No watch roles detected based on current rules.")

        st.markdown('<div class="section-title">Department Heatmap</div>', unsafe_allow_html=True)
        heat = insights["dept_heatmap"]
        if len(heat) > 0:
            fig2 = px.imshow(
                heat,
                aspect="auto",
                title="Avg Gap% by Department & Role Cluster",
                template=plot_template,
            )
            fig2.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=360)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Heatmap not available (missing department/cluster fields).")

# -----------------------------
# MARKET TAB
# -----------------------------
with tabs[1]:
    st.markdown('<div class="section-title">Market Benchmark Table</div>', unsafe_allow_html=True)
    st.markdown('<div class="muted">Benchmark Low/Mid/High are calculated from competitor salary ranges (midpoint aggregation).</div>', unsafe_allow_html=True)

    market_table = engine["market_table"](selected_companies)

    # Search
    c1, c2 = st.columns([0.6, 0.4])
    with c1:
        query = st.text_input("🔎 Search role / designation", value="")
    with c2:
        gap_filter = st.selectbox("Filter by gap", ["All", "PCI Below Market (<0%)", "PCI Far Below (<= -10%)", "PCI Above (>0%)"])

    filtered = market_table.copy()
    if query.strip():
        q = query.strip().lower()
        for col in ["Designation", "Department"]:
            if col in filtered.columns:
                filtered = filtered[filtered[col].astype(str).str.lower().str.contains(q, na=False)]
                break

    if "GapPct" in filtered.columns:
        if gap_filter == "PCI Below Market (<0%)":
            filtered = filtered[filtered["GapPct"] < 0]
        elif gap_filter == "PCI Far Below (<= -10%)":
            filtered = filtered[filtered["GapPct"] <= -10]
        elif gap_filter == "PCI Above (>0%)":
            filtered = filtered[filtered["GapPct"] > 0]

    st.dataframe(filtered, use_container_width=True, hide_index=True)

    st.markdown('<hr class="soft"/>', unsafe_allow_html=True)

    st.markdown('<div class="section-title">Role Comparison Chart</div>', unsafe_allow_html=True)
    st.caption("Pick a role to compare PCI vs Benchmark Range.")

    roles = market_table["Designation"].dropna().unique().tolist() if "Designation" in market_table.columns else []
    picked_role = st.selectbox("Select Role", roles if roles else ["(No roles)"])

    if roles and picked_role:
        row = market_table[market_table["Designation"] == picked_role].head(1)
        if len(row) > 0:
            low = float(row["BenchLow"].values[0]) if "BenchLow" in row.columns else np.nan
            mid = float(row["BenchMid"].values[0]) if "BenchMid" in row.columns else np.nan
            high = float(row["BenchHigh"].values[0]) if "BenchHigh" in row.columns else np.nan
            pci = float(row["PCISalary"].values[0]) if "PCISalary" in row.columns else np.nan

            fig = go.Figure()
            fig.add_trace(go.Bar(name="Benchmark Low", x=["Range"], y=[low]))
            fig.add_trace(go.Bar(name="Benchmark Mid", x=["Range"], y=[mid]))
            fig.add_trace(go.Bar(name="Benchmark High", x=["Range"], y=[high]))
            fig.add_trace(go.Scatter(name="PCI Salary", x=["Range"], y=[pci], mode="markers", marker=dict(size=14)))
            fig.update_layout(
                barmode="group",
                template=plot_template,
                title=f"{picked_role}: PCI vs Market Benchmark (AED)",
                margin=dict(l=10, r=10, t=50, b=10),
                height=380,
            )
            st.plotly_chart(fig, use_container_width=True)

# -----------------------------
# EMPLOYEES TAB
# -----------------------------
with tabs[2]:
    st.markdown('<div class="section-title">Employee Salary View</div>', unsafe_allow_html=True)
    st.markdown('<div class="muted">Search employees and review distribution by department/designation.</div>', unsafe_allow_html=True)

    emp = engine["employees_table"]()

    e1, e2, e3 = st.columns([0.45, 0.25, 0.30])
    with e1:
        emp_query = st.text_input("🔎 Search Employee (Name/ID)", "")
    with e2:
        dept = st.selectbox("Department", ["All"] + sorted(emp["Department"].dropna().astype(str).unique().tolist()) if "Department" in emp.columns else ["All"])
    with e3:
        desig = st.selectbox("Designation", ["All"] + sorted(emp["Designation"].dropna().astype(str).unique().tolist()) if "Designation" in emp.columns else ["All"])

    emp_f = emp.copy()
    if emp_query.strip():
        q = emp_query.strip().lower()
        cols = [c for c in emp_f.columns if c.lower() in ["employee name", "employee", "name", "emp no", "employee id", "id", "emp id"]]
        if cols:
            mask = False
            for c in cols:
                mask = mask | emp_f[c].astype(str).str.lower().str.contains(q, na=False)
            emp_f = emp_f[mask]
        else:
            # fallback: search all columns
            mask = emp_f.apply(lambda r: r.astype(str).str.lower().str.contains(q, na=False).any(), axis=1)
            emp_f = emp_f[mask]

    if dept != "All" and "Department" in emp_f.columns:
        emp_f = emp_f[emp_f["Department"].astype(str) == dept]
    if desig != "All" and "Designation" in emp_f.columns:
        emp_f = emp_f[emp_f["Designation"].astype(str) == desig]

    st.dataframe(emp_f, use_container_width=True, hide_index=True)

    st.markdown('<hr class="soft"/>', unsafe_allow_html=True)

    c1, c2 = st.columns([0.5, 0.5], gap="large")
    with c1:
        st.markdown('<div class="section-title">Salary Distribution</div>', unsafe_allow_html=True)
        if "Salary" in emp.columns:
            fig = px.histogram(emp_f, x="Salary", nbins=30, template=plot_template, title="Salary Distribution (AED)")
            fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=330)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Salary column not found.")

    with c2:
        st.markdown('<div class="section-title">Top 10 Salaries</div>', unsafe_allow_html=True)
        if "Salary" in emp_f.columns:
            top10 = emp_f.sort_values("Salary", ascending=False).head(10)
            fig = px.bar(top10, x="Salary", y=("Employee Name" if "Employee Name" in top10.columns else top10.columns[0]),
                         orientation="h", template=plot_template, title="Top 10 Salaries (AED)")
            fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=330)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Salary column not found.")

# -----------------------------
# PLANNER TAB
# -----------------------------
with tabs[3]:
    st.markdown('<div class="section-title">Increment / Budget Planner</div>', unsafe_allow_html=True)
    st.markdown('<div class="muted">Simulate a budget-based increment plan for critical below-market roles.</div>', unsafe_allow_html=True)

    planner = engine["planner"](selected_companies)

    c1, c2, c3 = st.columns([0.33, 0.33, 0.34])
    with c1:
        total_budget = st.number_input("Total Budget (AED)", min_value=0.0, value=float(planner["default_budget"]), step=1000.0)
    with c2:
        target_gap = st.slider("Target Minimum Gap%", min_value=-30, max_value=0, value=-5, step=1)
    with c3:
        focus_only_critical = st.checkbox("Only roles <= -10% gap", value=True)

    plan_df, summary = engine["build_plan"](selected_companies, total_budget, target_gap, focus_only_critical)

    st.markdown('<div class="section-title">Plan Summary</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="insight">'
        f'<b>Roles in plan:</b> {summary["roles_in_plan"]} &nbsp; • &nbsp; '
        f'<b>Employees impacted:</b> {summary["employees_impacted"]} &nbsp; • &nbsp; '
        f'<b>Budget used:</b> AED {fmt_aed(summary["budget_used"])} / {fmt_aed(total_budget)}'
        f'<br/><span class="muted">Rule:</span> bring roles up to at least {target_gap}% gap where possible.</div>',
        unsafe_allow_html=True
    )

    st.markdown('<div class="section-title">Recommended Adjustments</div>', unsafe_allow_html=True)
    st.dataframe(plan_df, use_container_width=True, hide_index=True)

    st.download_button(
        "⬇️ Download Plan (CSV)",
        data=df_to_download_bytes(plan_df, "csv"),
        file_name="increment_plan.csv",
        mime="text/csv",
    )

# -----------------------------
# EXPORT TAB
# -----------------------------
with tabs[4]:
    st.markdown('<div class="section-title">Export Reports</div>', unsafe_allow_html=True)
    st.markdown('<div class="muted">Generate board-ready Excel pack and a quick PDF summary.</div>', unsafe_allow_html=True)

    out_dir = os.path.join(DATA_DIR, "exports")
    os.makedirs(out_dir, exist_ok=True)

    c1, c2 = st.columns([0.55, 0.45], gap="large")

    with c1:
        st.markdown("### 📘 Excel Benchmark Pack")
        st.caption("Includes: Market table, PCI vs Market gap, benchmark low/mid/high, summary KPIs.")
        if st.button("Generate Excel Pack"):
            try:
                excel_path = os.path.join(out_dir, f"PCI_Salary_Benchmark_Pack_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")
                build_excel_pack(engine, selected_companies, excel_path)
                with open(excel_path, "rb") as f:
                    st.download_button(
                        "⬇️ Download Excel Pack",
                        data=f,
                        file_name=os.path.basename(excel_path),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                st.success("Excel pack generated.")
            except Exception as e:
                st.error(f"Excel generation failed: {e}")

    with c2:
        st.markdown("### 🧾 PDF Summary")
        st.caption("One-page summary: KPIs + key bullets + snapshot.")
        if st.button("Generate PDF Summary"):
            try:
                kpis = engine["kpis"](selected_companies)
                insights = engine["insights"](selected_companies)
                lines = [
                    f"Date: {datetime.now().strftime('%d %b %Y %H:%M')}",
                    "",
                    f"PCI Avg Salary (AED): {fmt_aed(kpis['pci_avg'])}",
                    f"Market Avg (AED): {fmt_aed(kpis['market_avg'])}",
                    f"Avg Gap vs Market: {safe_pct(kpis['avg_gap_pct'])}",
                    f"Critical Roles (<= -10%): {kpis['critical_roles']}",
                    "",
                    "Key Findings:",
                ] + [f"- {b}" for b in insights["bullets"][:10]]

                pdf_path = os.path.join(out_dir, f"PCI_Benchmark_Summary_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf")
                export_pdf_summary(lines, pdf_path)

                with open(pdf_path, "rb") as f:
                    st.download_button(
                        "⬇️ Download PDF",
                        data=f,
                        file_name=os.path.basename(pdf_path),
                        mime="application/pdf",
                    )
                st.success("PDF summary generated.")
            except Exception as e:
                st.error(f"PDF generation failed: {e}")

    st.markdown('<hr class="soft"/>', unsafe_allow_html=True)
    st.markdown("### 📦 Data Export")
    market_table = engine["market_table"](selected_companies)
    st.download_button(
        "⬇️ Download Market Table (CSV)",
        data=df_to_download_bytes(market_table, "csv"),
        file_name="market_table.csv",
        mime="text/csv",
    )
    emp = engine["employees_table"]()
    st.download_button(
        "⬇️ Download Employee Table (CSV)",
        data=df_to_download_bytes(emp, "csv"),
        file_name="employee_table.csv",
        mime="text/csv",
    )

# -----------------------------
# Notes / footer help
# -----------------------------
st.markdown('<hr class="soft"/>', unsafe_allow_html=True)
st.markdown(
    '<div class="muted small-help">Tip: Use the sidebar to select competitor companies. '
    'Benchmark Low/Mid/High and Gap% will update instantly.</div>',
    unsafe_allow_html=True
)
