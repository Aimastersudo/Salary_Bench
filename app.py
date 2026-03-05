
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

# Page config
st.set_page_config(page_title="PCI | Salary Intelligence", layout="wide")

st.markdown("""
<style>
.main { background-color: #0b0f19; color: #f8fafc; }
[data-testid="stSidebar"] { background-color: #111827; border-right: 1px solid #1f2937; }
.stMetric { background-color: #1f2937; padding: 20px; border-radius: 15px; border: 1px solid #374151; }
.salary-card { background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); padding: 25px; border-radius: 15px; border-left: 5px solid #3b82f6; margin-bottom: 20px; }
.ai-insight-box { background-color: rgba(59, 130, 246, 0.1); border: 1px solid #3b82f6; padding: 20px; border-radius: 12px; color: #93c5fd; font-size: 15px; line-height: 1.6; border-left: 5px solid #3b82f6; }
.market-box { background-color: #1e293b; border: 1px solid #475569; padding: 15px; border-radius: 10px; text-align: center; margin-top: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
.note-box { background-color: rgba(245, 158, 11, 0.1); border-left: 5px solid #f59e0b; padding: 15px; margin: 10px 0; border-radius: 5px; color: #fbbf24; }
.value-text { color: #38bdf8; font-size: 18px; font-weight: bold; }
.highlight-red { color: #ef4444; font-weight: bold; }
.highlight-green { color: #22c55e; font-weight: bold; }
.profile-card { background-color: #1f2937; padding: 20px; border-radius: 15px; border: 1px solid #3b82f6; }
</style>
""", unsafe_allow_html=True)

# PDF generator
def generate_graphical_pdf(f_df, avg_v, worst_d, total_hc, crit_df, loyalty_count):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_fill_color(15, 23, 42); pdf.rect(0, 0, 210, 40, 'F')
    pdf.set_text_color(255, 255, 255); pdf.set_font("Arial", 'B', 18)
    pdf.cell(190, 15, "PCI STRATEGIC SALARY INTELLIGENCE REPORT", 0, 1, 'C')
    pdf.set_font("Arial", '', 10); pdf.cell(190, 5, f"Snapshot: {datetime.now().strftime('%d %b %Y')}", 0, 1, 'C')
    pdf.ln(25); pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", 'B', 14); pdf.set_fill_color(230, 235, 255)
    pdf.cell(190, 10, " 1. Executive Summary", 1, 1, 'L', True)
    pdf.set_font("Arial", '', 11)
    summary = (f"Market Disparity (Avg Gap): {avg_v}% | Total Workforce: {total_hc} | Roles: {len(f_df)}\n\n"
               f"Key Insight: The {worst_d} department shows the highest competitive risk. "
               f"Recommended focus: align pay for {loyalty_count} loyal employees (5y+ tenure) "
               f"and close critical gaps for high-demand technical roles.")
    pdf.multi_cell(190, 8, summary, 1); pdf.ln(10)
    pdf.set_font("Arial", 'B', 14); pdf.set_fill_color(255, 230, 230)
    pdf.cell(190, 10, " 2. Critical High-Priority Gaps (<= -15%)", 1, 1, 'L', True)
    pdf.set_font("Arial", 'B', 10); pdf.cell(90, 8, "Role", 1); pdf.cell(50, 8, "Dept", 1); pdf.cell(30, 8, "Gap %", 1); pdf.cell(20, 8, "HC", 1, 1)
    pdf.set_font("Arial", '', 9)
    for _, row in crit_df.head(15).iterrows():
        pdf.cell(90, 7, str(row['Designation']), 1); pdf.cell(50, 7, str(row['Department']), 1)
        pdf.cell(30, 7, f"{int(row['Variance %'])}%", 1); pdf.cell(20, 7, str(int(row['Live_HC'])), 1, 1)
    pdf.ln(15); pdf.set_font("Arial", 'I', 8); pdf.cell(190, 5, "CONFIDENTIAL - PCI HR", 0, 1, 'C')
    return pdf.output(dest='S').encode('latin-1')

@st.cache_data
def load_data(core_bytes, payroll_bytes, market_bytes, competitor_include):
    # load from uploads or local
    if core_bytes is None:
        core_path = "salary_data.csv"
        payroll_path = "actuals_payroll.csv"
        market_path = "Market_salary.csv"
        core_df, payroll_df, market_df = load_csvs(core_path, payroll_path, market_path)
    else:
        core_df = pd.read_csv(core_bytes, encoding="utf-8-sig")
        payroll_df = pd.read_csv(payroll_bytes, encoding="utf-8-sig")
        market_df = pd.read_csv(market_bytes, encoding="utf-8-sig")

    res = build_engine(core_df, payroll_df, market_df, competitor_include=competitor_include)
    return res.role_df, res.emp_df, res.competitor_columns, market_df

# Sidebar
with st.sidebar:
    # logo
    l_path = None
    for ex in ["jpg", "png"]:
        if os.path.exists(f"PCI_Logo.{ex}"):
            l_path = f"PCI_Logo.{ex}"
            break
    if l_path:
        st.image(l_path, use_container_width=True)

    st.caption("Data Sources (optional uploads)")
    up_core = st.file_uploader("Upload salary_data.csv (core roles)", type=["csv"])
    up_payroll = st.file_uploader("Upload actuals_payroll.csv (employees)", type=["csv"])
    up_market = st.file_uploader("Upload Market_salary.csv (competitors)", type=["csv"])

    # competitor include list (needs market columns; load a tiny preview from local if no upload)
    try:
        if up_market is None:
            m_preview = pd.read_csv("Market_salary.csv", encoding="utf-8-sig")
        else:
            m_preview = pd.read_csv(up_market, encoding="utf-8-sig")
            up_market.seek(0)
        m_preview.columns = m_preview.columns.str.strip()
        all_companies = [c for c in m_preview.columns if c not in {"#", "Designation"}]
    except Exception:
        all_companies = []

    st.markdown("---")
    st.caption("Benchmark Scope")
    competitor_include = st.multiselect("Include competitor companies", all_companies, default=all_companies)

    page = st.radio("MENU", ["📊 Executive Dashboard", "📉 Market Analysis", "👥 PCI Employees", "📈 Increment Planner", "📦 Export"])
    st.markdown("---")

    # load data (cache)
    core_bytes = up_core if up_core is not None else None
    payroll_bytes = up_payroll if up_payroll is not None else None
    market_bytes = up_market if up_market is not None else None

# Load
df, emp_df, comp_cols, raw_market_df = load_data(core_bytes, payroll_bytes, market_bytes, competitor_include)

# Filters
with st.sidebar:
    depts = sorted(df['Department'].dropna().unique().tolist())
    sel_depts = st.multiselect("Filter Dept:", depts, default=depts)

f_df = df[df['Department'].isin(sel_depts)].copy()
f_emp = emp_df[emp_df['Department'].isin(sel_depts)].copy()

# Pages
if page == "📊 Executive Dashboard":
    st.title("Strategic Salary Benchmark Dashboard")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Designations", len(f_df))
    c2.metric("Total Headcount", int(f_df['Live_HC'].sum()))
    mean_v = f_df['Variance %'].mean() if len(f_df) else 0
    c3.metric("Avg. Market Gap", f"{int(mean_v) if pd.notna(mean_v) else 0}%")
    c4.metric("Critical Roles (<= -20%)", int((f_df['Variance %'] <= -20).sum()))

    st.dataframe(
        f_df[['Designation','Department','Employee Type','Live_HC',
              'Your Salary (AED)','Benchmark_Low','Benchmark_Mid','Benchmark_High','Market_Avg','Variance %']],
        use_container_width=True,
        hide_index=True
    )

    st.markdown("---")
    st.subheader("🔍 Role Deep-Dive")
    sel_role = st.selectbox("Select a Role:", sorted(f_df['Designation'].unique()))
    if sel_role:
        row = f_df[f_df['Designation'] == sel_role].iloc[0]
        gap = int(row['Variance %'])
        st.markdown(
            f"""<div class="salary-card"><div class="ai-insight-box">
            <b>Insight:</b> {row['Designation']} is <b>{abs(gap)}%</b> {"below" if gap < 0 else "above"} the market average.
            Benchmark range (midpoints): <b>{int(row['Benchmark_Low']):,}</b> to <b>{int(row['Benchmark_High']):,}</b> AED.
            </div></div>""",
            unsafe_allow_html=True
        )
        # company cards (original strings)
        cols = st.columns(max(1, len(comp_cols)))
        for i, c in enumerate(comp_cols):
            val = str(row.get(c, "nan"))
            with cols[i]:
                st.markdown(
                    f"""<div class="market-box"><small>{c}</small><br>
                    <b class="value-text">{val if val not in ['nan','-','None'] else 'N/A'}</b></div>""",
                    unsafe_allow_html=True
                )

elif page == "📉 Market Analysis":
    st.title("📉 Market Disparity Analysis")

    if len(f_df):
        avg_var = int(f_df['Variance %'].mean())
        worst_d = f_df.groupby('Department')['Variance %'].mean().idxmin()
        st.markdown(
            f"""<div class="salary-card"><div class="ai-insight-box">
            <b>Summary:</b> PCI is {abs(avg_var)}% {"behind" if avg_var < 0 else "ahead of"} the selected market scope.
            Highest risk department: <b>{worst_d}</b>. Bubble size shows headcount.
            </div></div>""",
            unsafe_allow_html=True
        )

        c1, c2 = st.columns(2)
        with c1:
            fig = px.scatter(
                f_df, x='Market_Avg', y='Your Salary (AED)', size='Live_HC', color='Department',
                hover_name='Designation', title="Positioning Matrix (PCI vs Market Avg)"
            )
            diag_max = float(max(f_df['Market_Avg'].max(), f_df['Your Salary (AED)'].max()))
            fig.add_shape(type='line', x0=0, y0=0, x1=diag_max, y1=diag_max,
                          line=dict(color='white', dash='dash'))
            fig.update_layout(template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            dept_var = f_df.groupby('Department')['Variance %'].mean().reset_index().sort_values('Variance %')
            fig2 = px.bar(
                dept_var, x='Variance %', y='Department', orientation='h', title="Avg Gap by Department (%)"
            )
            fig2.update_layout(template="plotly_dark")
            st.plotly_chart(fig2, use_container_width=True)

        st.subheader("⚠️ High-Priority Adjustment List (<= -20%)")
        st.dataframe(
            f_df[f_df['Variance %'] <= -20][['Designation','Department','Live_HC','Your Salary (AED)','Market_Avg','Variance %']]
            .sort_values('Variance %'),
            use_container_width=True,
            hide_index=True
        )

elif page == "👥 PCI Employees":
    st.title("👥 PCI Employees Intelligence")

    if len(f_emp):
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Selected Employees", len(f_emp))
        e2.metric("Loyal Staff (>5y)", int((f_emp['Tenure_Y'] >= 5).sum()))
        e3.metric("Avg. Tenure", f"{round(f_emp['Tenure_Y'].mean(), 1)} Yrs")
        e4.metric("Employees <= -15%", int((f_emp['Gap %'] <= -15).sum()))

        st.markdown(
            f"""<div class="salary-card"><div class="ai-insight-box">
            <b>Payroll health:</b> {int((f_emp['Gap %'] < -10).sum())} employees are under market by more than 10%.
            Loyal-at-risk (3y+ and <= -10%): <b>{int(((f_emp['Tenure_Y'] >= 3) & (f_emp['Gap %'] < -10)).sum())}</b>.
            </div></div>""",
            unsafe_allow_html=True
        )

        sel_name = st.selectbox("Spotlight Employee:", sorted(f_emp['Employee Name'].unique()))
        if sel_name:
            ed = f_emp[f_emp['Employee Name'] == sel_name].iloc[0]
            ca, cb = st.columns([1, 2])
            with ca:
                st.markdown(
                    f"""<div class="profile-card"><h3>{ed['Employee Name']}</h3>
                    <p>ID: {ed['Employee ID']} | Tenure: {ed['Tenure_Text']}</p>
                    <p>Joined: {ed['Date of Joining']}</p><hr>
                    <p>Salary: {int(ed['Salary']):,} AED |
                    <span class="{'highlight-red' if ed['Gap %'] < 0 else 'highlight-green'}">
                    Gap: {int(ed['Gap %'])}%</span></p></div>""",
                    unsafe_allow_html=True
                )
            with cb:
                st.markdown("#### Role Benchmark (Selected Market Scope)")
                st.write(
                    {
                        "Benchmark Low": f"{int(ed['Benchmark_Low']):,}",
                        "Benchmark Mid": f"{int(ed['Benchmark_Mid']):,}",
                        "Benchmark High": f"{int(ed['Benchmark_High']):,}",
                        "Market Avg": f"{int(ed['Market_Avg']):,}",
                    }
                )

        def style_status(v):
            return f'color: {"#ef4444" if v < 0 else "#22c55e"}; font-weight: bold'

        st.dataframe(
            f_emp[['Employee ID','Employee Name','Designation','Department','Tenure_Text','Salary','Market_Avg','Gap %']]
            .style.applymap(style_status, subset=['Gap %']),
            use_container_width=True,
            hide_index=True
        )

elif page == "📈 Increment Planner":
    st.title("📈 Increment Strategy Simulator")

    target = st.selectbox("Select Employee:", sorted(f_emp['Employee Name'].unique()) if len(f_emp) else [])
    if target:
        data = f_emp[f_emp['Employee Name'] == target].iloc[0]
        col1, col2 = st.columns([1, 2])
        with col1:
            pct = st.number_input("Increment %", 0.0, 50.0, 5.0)
            new_s = int(data['Salary'] * (1 + pct/100))
            gap_af = int(((new_s - data['Market_Avg']) / data['Market_Avg'] if data['Market_Avg'] != 0 else 0) * 100)
            st.metric("Proposed Salary", f"{new_s:,} AED", f"+{new_s - int(data['Salary']):,}")
            st.metric("New Market Gap", f"{gap_af}%")
        with col2:
            st.markdown(
                f"""<div class="salary-card"><div class="ai-insight-box">
                <b>Budget note:</b> Monthly impact: {new_s - int(data['Salary']):,} AED.
                After increment, employee is: <b>{'Still under market' if gap_af < -5 else 'Near aligned'}</b>.
                </div></div>""",
                unsafe_allow_html=True
            )
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=new_s,
                title={'text': "Market Position Gauge"},
                gauge={
                    'axis': {'range': [0, data['Market_Avg']*1.5 if data['Market_Avg'] != 0 else 10000]},
                    'steps': [
                        {'range': [0, data['Market_Avg']*0.9], 'color': "red"},
                        {'range': [data['Market_Avg']*0.9, data['Market_Avg']*1.1], 'color': "green"},
                    ]
                }
            ))
            fig.update_layout(template="plotly_dark", height=280)
            st.plotly_chart(fig, use_container_width=True)

elif page == "📦 Export":
    st.title("📦 Export & Automation")

    st.markdown(
        """<div class="note-box">
        Exports use the currently selected filters (departments + competitor scope).
        </div>""",
        unsafe_allow_html=True
    )

    # Build filtered exports
    exp_role = f_df.copy()
    exp_emp = f_emp.copy()

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Generate Strategy PDF"):
            avg_v = int(exp_role['Variance %'].mean()) if len(exp_role) else 0
            worst_d = exp_role.groupby('Department')['Variance %'].mean().idxmin() if len(exp_role) else "N/A"
            crit_df = exp_role[exp_role['Variance %'] <= -15].sort_values('Variance %')
            loyalty_count = int((exp_emp['Tenure_Y'] >= 5).sum()) if len(exp_emp) else 0
            pdf_bytes = generate_graphical_pdf(exp_role, avg_v, worst_d, int(exp_role['Live_HC'].sum()), crit_df, loyalty_count)
            st.download_button("📥 Download PDF Report", data=pdf_bytes, file_name="PCI_Strategic_Report.pdf", mime="application/pdf")

    with c2:
        if st.button("Build Excel Benchmark Pack"):
            xlsx_bytes = build_excel_pack(exp_role, exp_emp)
            st.download_button("📥 Download Excel Pack", data=xlsx_bytes, file_name="PCI_Salary_Benchmark_Pack.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.markdown("### Automated (Batch) Run")
    st.code(
        "python build_reports.py --core salary_data.csv --payroll actuals_payroll.csv --market Market_salary.csv --out PCI_Salary_Benchmark_Pack.xlsx",
        language="bash"
    )
