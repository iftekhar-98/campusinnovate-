"""
pages/1_Staff_Dashboard.py — UCI Operations Triage Dashboard
Staff use this to review, approve, route, and analyse campus reports.
"""

import streamlit as st
import folium
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

from database import (
    init_db, seed_sample_data,
    get_all_reports, get_report_by_id,
    update_report, get_analytics, delete_all_and_reseed,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="UCI Dashboard — CampusInnovate",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()
seed_sample_data()

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* ── Aurora Glass — Staff Dashboard ── */
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding-top: 1rem; }

  /* Dark gradient background */
  .stApp {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    min-height: 100vh;
  }

  /* Dashboard header — aurora gradient */
  .dash-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
    border-radius: 16px; padding: 20px 26px; margin-bottom: 20px;
    color: white; position: relative; overflow: hidden;
  }
  .dash-header::before {
    content: ''; position: absolute;
    top: -50px; right: -50px; width: 180px; height: 180px;
    background: rgba(255,255,255,0.08); border-radius: 50%;
  }
  .dash-header h1 { font-size: 22px; margin: 0; position: relative; z-index: 1; }
  .dash-header p  { font-size: 13px; opacity: .8; margin: 4px 0 0; position: relative; z-index: 1; }

  /* KPI stat cards — glass with gradient tint */
  .kpi-card {
    flex: 1; border-radius: 14px; padding: 18px 20px;
    color: white; position: relative; overflow: hidden;
    border: 1px solid rgba(255,255,255,0.18);
    backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  }
  .kpi-card .val  { font-size: 34px; font-weight: 800; }
  .kpi-card .lbl  { font-size: 12px; opacity: .8; margin-bottom: 6px; }
  .kpi-card .icon { position: absolute; right: 16px; top: 16px;
    font-size: 28px; opacity: .35; }
  /* Each card gets a distinct aurora gradient */
  .kpi-purple { background: linear-gradient(135deg, rgba(109,40,217,0.7), rgba(139,92,246,0.5)); }
  .kpi-red    { background: linear-gradient(135deg, rgba(220,38,38,0.7),  rgba(248,113,113,0.5)); }
  .kpi-orange { background: linear-gradient(135deg, rgba(217,119,6,0.7),  rgba(251,191,36,0.5)); }
  .kpi-green  { background: linear-gradient(135deg, rgba(5,150,105,0.7),  rgba(52,211,153,0.5)); }

  /* Issue row cards — frosted glass */
  .issue-row {
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 14px; padding: 16px 18px;
    margin-bottom: 10px;
    backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
    transition: background 0.2s;
  }
  .issue-row:hover { background: rgba(255,255,255,0.13); }
  .issue-row.border-high   { border-left: 4px solid #FB7185; }
  .issue-row.border-medium { border-left: 4px solid #FBBF24; }
  .issue-row.border-low    { border-left: 4px solid #34D399; }

  /* Badges — glass tinted */
  .badge-high   { background:rgba(251,113,133,0.25); color:#FFF; border:1px solid rgba(251,113,133,0.4); padding:3px 10px; border-radius:999px; font-size:12px; font-weight:600; }
  .badge-medium { background:rgba(251,191,36,0.25);  color:#FFF; border:1px solid rgba(251,191,36,0.4);  padding:3px 10px; border-radius:999px; font-size:12px; font-weight:600; }
  .badge-low    { background:rgba(52,211,153,0.25);  color:#FFF; border:1px solid rgba(52,211,153,0.4);  padding:3px 10px; border-radius:999px; font-size:12px; font-weight:600; }
  .badge-blue   { background:rgba(102,126,234,0.25); color:#FFF; border:1px solid rgba(102,126,234,0.4); padding:3px 10px; border-radius:999px; font-size:12px; font-weight:600; }
  .badge-gray   { background:rgba(255,255,255,0.15); color:#FFF; border:1px solid rgba(255,255,255,0.2); padding:3px 10px; border-radius:999px; font-size:12px; font-weight:600; }

  /* Duplicate warning — glass amber */
  .dup-warn {
    background: rgba(251,191,36,0.15); border: 1px solid rgba(251,191,36,0.35);
    border-radius: 8px; padding: 8px 12px; font-size: 12px;
    color: #FDE68A; margin: 6px 0;
  }

  /* Issue text colors on dark bg */
  .issue-row .issue-title { color: #ffffff; }
  .issue-row .issue-loc   { color: rgba(255,255,255,0.65); }
  .issue-row .issue-sum   { color: rgba(255,255,255,0.55); }
  .issue-row .issue-rea   { color: rgba(255,255,255,0.4); }

  /* Sidebar glass effect */
  section[data-testid="stSidebar"] {
    background: rgba(255,255,255,0.06) !important;
    border-right: 1px solid rgba(255,255,255,0.12) !important;
    backdrop-filter: blur(12px);
  }
  section[data-testid="stSidebar"] * { color: rgba(255,255,255,0.85) !important; }

  /* Buttons */
  div[data-testid="stButton"] > button {
    background: rgba(255,255,255,0.10);
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 8px; font-weight: 600; color: white;
  }
  div[data-testid="stButton"] > button:hover {
    background: rgba(255,255,255,0.18);
  }
  div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #667eea, #764ba2);
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 8px; font-weight: 700; color: white;
  }

  /* Tabs */
  button[data-baseweb="tab"] {
    color: rgba(255,255,255,0.6) !important;
  }
  button[data-baseweb="tab"][aria-selected="true"] {
    color: white !important;
    border-bottom-color: #667eea !important;
  }

  /* Expander */
  details {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 10px !important;
  }
  details summary { color: rgba(255,255,255,0.85) !important; }

  /* Input fields */
  div[data-testid="stTextInput"] input,
  div[data-testid="stTextArea"] textarea,
  div[data-testid="stSelectbox"] > div {
    background: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(255,255,255,0.2) !important;
    border-radius: 10px !important; color: white !important;
  }

  /* Metrics */
  div[data-testid="stMetric"] {
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 12px; padding: 14px;
    backdrop-filter: blur(8px);
  }
  div[data-testid="stMetric"] label,
  div[data-testid="stMetric"] div { color: white !important; }
</style>
""", unsafe_allow_html=True)

ONEMAP_TILES = "https://www.onemap.gov.sg/maps/tiles/Default/{z}/{x}/{y}.png"
ONEMAP_ATTR  = '<a href="https://www.onemap.gov.sg/">OneMap</a> &copy; SLA'
NUS_CENTER   = [1.2966, 103.7764]

DEPARTMENTS = [
    "— Select department —",
    "Facilities Management", "Mechanical & Electrical",
    "Safety & Security", "Cleaning Services",
    "Accessibility Office", "IT Services", "Grounds & Landscaping",
]

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="dash-header">
  <h1>UCI Operations Dashboard</h1>
  <p>CampusInnovate — AI-Assisted Signal Governance</p>
</div>
""", unsafe_allow_html=True)

# Sidebar controls
with st.sidebar:
    st.markdown("### 🔧 Controls")
    st.page_link("streamlit_app.py", label=" Student Portal →")
    st.divider()
    status_filter = st.selectbox("Filter by status", ["All", "Submitted", "In Progress", "Resolved", "Closed"])
    search_q      = st.text_input(" Search reports", placeholder="ID, location, category…")
    st.divider()
    if st.button("🔄 Refresh data"):
        st.cache_data.clear()
        st.rerun()
    if st.button(" Reset to sample data", help="Clears all reports and reloads demo data"):
        delete_all_and_reseed()
        st.success("Reseeded!")
        st.rerun()

# ── Load data ─────────────────────────────────────────────────────────────────
all_reports = get_all_reports()

def time_ago(iso):
    if not iso: return ""
    diff  = datetime.utcnow() - datetime.fromisoformat(iso)
    mins  = int(diff.total_seconds() / 60)
    if mins < 1:   return "just now"
    if mins < 60:  return f"{mins}m ago"
    hrs = mins // 60
    if hrs < 24:   return f"{hrs}h ago"
    return f"{hrs // 24}d ago"

def urg_border(u):
    return {"High": "border-high", "Medium": "border-medium"}.get(u, "border-low")

def urg_badge(u):
    return {"High": "badge-high", "Medium": "badge-medium"}.get(u, "badge-low")

def cat_emoji(c):
    return {"Facilities":"🔧","Safety":"🔥","Accessibility":"♿",
            "Cleanliness":"🧹","Utilities":"⚡","Vandalism":"⚠️"}.get(c,"📋")

# ── KPI cards ─────────────────────────────────────────────────────────────────
total     = len(all_reports)
high_urg  = sum(1 for r in all_reports if r.get("ai_urgency") == "High")
dups      = sum(1 for r in all_reports if r.get("is_duplicate"))
resolved  = sum(1 for r in all_reports if r.get("status") == "Resolved")
dup_ratio = round(dups / total * 100, 1) if total else 0

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(f"""<div class="kpi-card kpi-purple"><div class="icon">📡</div>
    <div class="lbl">Total Signals</div><div class="val">{total}</div></div>""", unsafe_allow_html=True)
with col2:
    st.markdown(f"""<div class="kpi-card kpi-red"><div class="icon">🔥</div>
    <div class="lbl">High Urgency</div><div class="val">{high_urg}</div></div>""", unsafe_allow_html=True)
with col3:
    st.markdown(f"""<div class="kpi-card kpi-orange"><div class="icon">🔁</div>
    <div class="lbl">Duplicate Ratio</div><div class="val">{dup_ratio}%</div></div>""", unsafe_allow_html=True)
with col4:
    st.markdown(f"""<div class="kpi-card kpi-green"><div class="icon">✅</div>
    <div class="lbl">Resolved</div><div class="val">{resolved}</div></div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Main Tabs ─────────────────────────────────────────────────────────────────
tab_inbox, tab_map, tab_analytics = st.tabs([" Inbox", " Campus Map", "Analytics"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — INBOX
# ══════════════════════════════════════════════════════════════════════════════
with tab_inbox:

    # Apply filters
    filtered = all_reports
    if status_filter != "All":
        filtered = [r for r in filtered if r.get("status") == status_filter]
    if search_q:
        q = search_q.lower()
        filtered = [r for r in filtered if q in (
            f"{r.get('report_id','')} {r.get('ai_category','')} "
            f"{r.get('category','')} {r.get('description','')} "
            f"{r.get('location_name','')}").lower()
        ]

    st.markdown(f"**{len(filtered)} reports** matching current filter")

    if not filtered:
        st.info("No reports match this filter.")
    else:
        for r in filtered:
            rid   = r["report_id"]
            urg   = r.get("ai_urgency", "Low")
            cat   = r.get("ai_category") or r.get("category","Other")
            conf  = int((r.get("ai_confidence") or 0) * 100)

            # ── Build card HTML ──
            dup_html = ""
            if r.get("is_duplicate"):
                orig = r.get("original_report_id","")
                dup_html = f'<div class="dup-warn">⚠️ Possible duplicate — original: <code>{orig}</code></div>'

            status_badge = ""
            if r.get("status") == "Resolved":
                status_badge = '<span class="badge-blue">✓ Resolved</span>'
            elif r.get("status") == "In Progress":
                status_badge = '<span class="badge-gray">⟳ In Progress</span>'

            dept_html = ""
            if r.get("assigned_department"):
                dept_html = f'<span style="font-size:12px;color:rgba(255,255,255,0.55)">→ {r["assigned_department"]}</span>'

            title = r.get("description","")
            if title:
                title = title.split(".")[0][:80]
            if not title:
                title = r.get("ai_summary","")[:80] or f"{cat} issue"

            st.markdown(f"""
            <div class="issue-row {urg_border(urg)}">
              <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px">
                <span style="font-size:12px;color:rgba(255,255,255,0.5);font-weight:500">{rid}</span>
                <span class="{urg_badge(urg)}">{cat_emoji(cat)} {cat} ({conf}%)</span>
                <span style="font-size:12px;color:rgba(255,255,255,0.4)">🕐 {time_ago(r.get('created_at'))}</span>
                {status_badge}
                {dept_html}
              </div>
              <div style="font-size:16px;font-weight:700;margin-bottom:6px;color:#fff">{title}</div>
              <div style="font-size:13px;color:rgba(255,255,255,0.6);margin-bottom:6px">📍 {r.get('location_name','—')}</div>
              {dup_html}
              <div style="font-size:13px;color:rgba(255,255,255,0.55)">{r.get('ai_summary','')}</div>
              {f'<div style="font-size:12px;color:rgba(255,255,255,0.35);margin-top:6px">ℹ️ {r.get("ai_urgency_reason","")}</div>' if r.get("ai_urgency_reason") else ''}
            </div>
            """, unsafe_allow_html=True)

            # ── Route action ──
            with st.expander(f"✅ Approve & Route — {rid}"):
                c1, c2 = st.columns(2)
                with c1:
                    dept = st.selectbox("Department", DEPARTMENTS, key=f"dept_{rid}")
                with c2:
                    new_status = st.selectbox("Status", ["Submitted","In Progress","Resolved","Closed"],
                                              index=["Submitted","In Progress","Resolved","Closed"].index(
                                                  r.get("status","Submitted")) if r.get("status") in
                                                  ["Submitted","In Progress","Resolved","Closed"] else 1,
                                              key=f"status_{rid}")
                notes = st.text_area("Staff notes (optional)", key=f"notes_{rid}",
                                      value=r.get("staff_notes","") or "")
                if st.button("✓ Confirm routing", key=f"route_{rid}", type="primary"):
                    if dept == "— Select department —":
                        st.error("Please select a department.")
                    else:
                        update_report(rid, new_status, dept, notes)
                        st.success(f"✅ {rid} routed to {dept} — status: {new_status}")
                        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — CAMPUS MAP
# ══════════════════════════════════════════════════════════════════════════════
with tab_map:
    st.markdown("**All active reports plotted by urgency. Click a marker for details.**")

    active = [r for r in all_reports if r.get("status") not in ("Resolved","Closed")]

    # Map summary stats
    mc1, mc2, mc3, mc4 = st.columns(4)
    with mc1: st.metric("Active Issues", len(active))
    with mc2: st.metric("🔴 High",   sum(1 for r in active if r.get("ai_urgency")=="High"))
    with mc3: st.metric("🟠 Medium", sum(1 for r in active if r.get("ai_urgency")=="Medium"))
    with mc4: st.metric("🟡 Low",    sum(1 for r in active if r.get("ai_urgency")=="Low"))

    # Build map
    m2 = folium.Map(location=NUS_CENTER, zoom_start=16, tiles=None)
    folium.TileLayer(tiles=ONEMAP_TILES, attr=ONEMAP_ATTR, min_zoom=11, max_zoom=19).add_to(m2)

    color_map = {"High": "red", "Medium": "orange", "Low": "beige"}
    for r in all_reports:
        if not r.get("location_lat"): continue
        c = color_map.get(r.get("ai_urgency","Low"), "gray")
        popup_html = f"""
        <div style="font-family:sans-serif;min-width:200px">
          <b style="font-size:13px">{r['report_id']}</b><br>
          <span style="color:#666;font-size:11px">{r.get('ai_category') or r.get('category','')}</span>
          &nbsp;•&nbsp;
          <span style="color:#666;font-size:11px">{r.get('ai_urgency','')}</span><br><br>
          <b>{r.get('location_name','')}</b><br>
          <span style="font-size:12px;color:#555">{r.get('ai_summary') or r.get('description','')}</span><br><br>
          <span style="font-size:11px;color:#888">Status: {r.get('status','')}</span>
          {f'<br><span style="font-size:11px;color:#888">→ {r.get("assigned_department","")}</span>' if r.get("assigned_department") else ""}
        </div>"""
        folium.Marker(
            location=[r["location_lat"], r["location_lng"]],
            popup=folium.Popup(popup_html, max_width=260),
            tooltip=f"{r['report_id']} — {r.get('ai_urgency','')}",
            icon=folium.Icon(color=c, icon="exclamation-circle", prefix="fa"),
        ).add_to(m2)

    st_folium(m2, width="100%", height=520, returned_objects=[])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════
with tab_analytics:
    data = get_analytics()

    # KPI row
    ak1, ak2, ak3 = st.columns(3)
    with ak1:
        st.markdown(f"""<div class="kpi-card kpi-purple" style="margin-bottom:16px">
        <div class="icon">🤖</div><div class="lbl">AI Accuracy</div>
        <div class="val">{data['ai_accuracy']}%</div></div>""", unsafe_allow_html=True)
    with ak2:
        st.markdown(f"""<div class="kpi-card kpi-orange" style="margin-bottom:16px">
        <div class="icon">🔁</div><div class="lbl">Duplicate Ratio</div>
        <div class="val">{data['duplicate_ratio']}%</div></div>""", unsafe_allow_html=True)
    with ak3:
        st.markdown(f"""<div class="kpi-card kpi-green" style="margin-bottom:16px">
        <div class="icon">✅</div><div class="lbl">Resolved</div>
        <div class="val">{data['resolved']}</div></div>""", unsafe_allow_html=True)

    chart_col1, chart_col2 = st.columns(2)

    # ── Category Donut ──
    with chart_col1:
        st.markdown("**Issue Categories**")
        cats = data.get("categories", [])
        if cats:
            df_cat = pd.DataFrame(cats)
            fig = px.pie(df_cat, names="category", values="count", hole=0.55,
                         color_discrete_sequence=["#667eea","#f093fb","#34D399","#FBBF24","#FB7185","#60A5FA","#a78bfa"])
            fig.update_layout(
                margin=dict(t=20,b=20,l=20,r=20), height=280,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="rgba(255,255,255,0.8)"),
                legend=dict(orientation="h", yanchor="bottom", y=-0.35,
                            font=dict(color="rgba(255,255,255,0.7)")),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data yet.")

    # ── Urgency Bar ──
    with chart_col2:
        st.markdown("**Urgency Breakdown**")
        urgs = data.get("urgency", [])
        if urgs:
            df_urg = pd.DataFrame(urgs)
            df_urg = df_urg.rename(columns={"ai_urgency": "Urgency", "count": "Count"})
            color_seq = {"High": "#FB7185", "Medium": "#FBBF24", "Low": "#34D399"}
            fig2 = px.bar(df_urg, x="Urgency", y="Count",
                          color="Urgency", color_discrete_map=color_seq,
                          text="Count")
            fig2.update_layout(
                showlegend=False, margin=dict(t=20,b=20,l=20,r=20), height=280,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="rgba(255,255,255,0.8)"),
                xaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
                yaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
            )
            fig2.update_traces(textposition="outside", textfont_color="white")
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No data yet.")

    # ── Daily Trend Line ──
    st.markdown("**Signal Volume — Last 30 Days**")
    daily = data.get("daily", [])
    if daily:
        df_daily = pd.DataFrame(daily)
        df_daily["date"] = pd.to_datetime(df_daily["date"])
        fig3 = px.area(df_daily, x="date", y="count",
                       color_discrete_sequence=["#667eea"])
        fig3.update_layout(
            margin=dict(t=10,b=20,l=20,r=20), height=220,
            xaxis_title="", yaxis_title="Reports",
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="rgba(255,255,255,0.7)"),
            xaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
            yaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
        )
        fig3.update_traces(line_width=2.5, fillcolor="rgba(102,126,234,0.2)")
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("Trend data will appear after reports are submitted over multiple days.")

    # ── Export ──
    if all_reports:
        st.divider()
        df_export = pd.DataFrame(all_reports)[
            ["report_id","ai_category","ai_urgency","status","location_name","created_at"]
        ]
        csv = df_export.to_csv(index=False)
        st.download_button("Export CSV", csv, "campusinnovate_export.csv", "text/csv")
