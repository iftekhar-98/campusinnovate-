"""
streamlit_app.py — CampusInnovate Student Reporting Interface
This is Page 1 (main page). Students use this to submit campus issues.
"""

import streamlit as st
import folium
from streamlit_folium import st_folium
import httpx
import os
import uuid
from datetime import datetime

from database import init_db, seed_sample_data, create_report, get_nearby_reports, get_report_by_id
from ai_service import analyze_report

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CampusInnovate — Report an Issue",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Groq API key — read here in main context where st.secrets is reliable ─────
_gemini_key = ""
try:
    _gemini_key = st.secrets["GROQ_API_KEY"]
except Exception:
    pass  # Key missing — AI will use rule-based fallback

# ── Init DB once ──────────────────────────────────────────────────────────────
init_db()
seed_sample_data()

# ── Custom CSS (MODIFIED FOR MODERN UI) ───────────────────────────────────────
st.markdown("""
<style>
  /* 1. Global App Background & Spacing */
  .stApp { background-color: #F8FAFC; }
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding-top: 2rem; padding-bottom: 2rem; max-width: 1200px; }

  /* 2. Elegant Header */
  .app-header {
    background: #FFFFFF;
    border-radius: 16px;
    padding: 24px 32px;
    margin-bottom: 28px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
    display: flex;
    align-items: center;
    justify-content: space-between;
    border: 1px solid #E2E8F0;
  }
  .app-header h1 { color: #0F172A; font-size: 28px; font-weight: 800; margin: 0; letter-spacing: -0.5px; }
  .app-header p  { color: #64748B; font-size: 15px; margin: 6px 0 0; font-weight: 400; }

  /* 3. Section Cards (For Map and Form) */
  .section-card {
    background: #FFFFFF; 
    border-radius: 16px; 
    padding: 28px;
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.04); 
    border: 1px solid #E2E8F0;
    margin-bottom: 20px;
  }
  .section-title { font-size: 18px; font-weight: 700; color: #0F172A; margin-bottom: 6px; }
  .section-sub   { font-size: 14px; color: #64748B; margin-bottom: 24px; }

  /* 4. Streamlit Input Overrides (Making form fields look modern) */
  div[data-baseweb="input"] > div,
  div[data-baseweb="textarea"] > div,
  div[data-baseweb="select"] > div {
    background-color: #F8FAFC !important;
    border-radius: 10px !important;
    border: 1px solid #CBD5E1 !important;
    transition: all 0.2s ease;
  }
  div[data-baseweb="input"] > div:focus-within,
  div[data-baseweb="textarea"] > div:focus-within {
    border-color: #3B82F6 !important;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2) !important;
  }

  /* 5. Buttons Styling */
  div[data-testid="stButton"] > button[kind="primary"],
  div[data-testid="stFormSubmitButton"] > button {
    background: linear-gradient(135deg, #2563EB, #1D4ED8);
    color: white;
    border-radius: 10px;
    font-weight: 600;
    font-size: 16px;
    padding: 14px 24px;
    border: none;
    box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.2);
    transition: all 0.2s;
  }
  div[data-testid="stButton"] > button[kind="primary"]:hover,
  div[data-testid="stFormSubmitButton"] > button:hover {
    box-shadow: 0 6px 8px -1px rgba(37, 99, 235, 0.3);
    transform: translateY(-1px);
  }
  
  /* 6. Success & Warning Boxes */
  .success-box {
    background: linear-gradient(135deg, #059669, #10B981);
    border-radius: 16px; padding: 32px; text-align: center; color: white;
    box-shadow: 0 10px 15px -3px rgba(16, 185, 129, 0.3);
  }
  .success-box .report-id {
    background: rgba(255,255,255,0.2); border-radius: 12px;
    padding: 16px; font-size: 28px; font-weight: 800;
    letter-spacing: 2px; margin: 20px 0; border: 1px dashed rgba(255,255,255,0.5);
  }
  .duplicate-warn {
    background: #FFFBEB; border: 1px solid #FDE68A; border-radius: 12px;
    padding: 16px; font-size: 14px; color: #92400E; margin-top: 16px;
    display: flex; align-items: center; gap: 8px;
  }

  /* Hide the Streamlit sidebar page navigation on the student page */
  [data-testid="stSidebarNav"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ── OneMap tile URL ───────────────────────────────────────────────────────────
ONEMAP_TILES = "https://www.onemap.gov.sg/maps/tiles/Default/{z}/{x}/{y}.png"
ONEMAP_ATTR  = (
    '<img src="https://www.onemap.gov.sg/docs/maps/images/oneMap64-01.png" '
    'style="height:16px;vertical-align:middle"/> '
    '<a href="https://www.onemap.gov.sg/">OneMap</a> &copy; SLA'
)
NUS_CENTER   = [1.2966, 103.7764]

# ── Session state defaults ────────────────────────────────────────────────────
for key, val in {
    "selected_lat": None, "selected_lng": None,
    "selected_location": None, "last_submitted": None,
    "show_tracking": False,
}.items():
    if key not in st.session_state:
        st.session_state[key] = val


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
  <div>
    <h1>🏛️ CampusInnovate</h1>
    <p>AI-Assisted Campus Issue Reporting — National University of Singapore</p>
  </div>
</div>
""", unsafe_allow_html=True)

# Navigation — Track button only
col_nav1, col_nav2 = st.columns([1.5, 5])
with col_nav1:
    if st.button("📋 Track my report", use_container_width=True):
        st.session_state.show_tracking = not st.session_state.show_tracking

st.divider()

# ── Show success after submission ──────────────────────────────────────────────
if st.session_state.last_submitted:
    r = st.session_state.last_submitted
    urg = r.get("ai_urgency", "Medium").lower()
    st.markdown(f"""
    <div class="success-box">
      <div style="font-size:48px">✅</div>
      <h2 style="margin:10px 0 4px">Report Submitted!</h2>
      <p style="opacity:.9">Received and awaiting staff review.</p>
      <div class="report-id">{r['report_id']}</div>
      <p style="opacity:.8;font-size:14px">Save this ID to track your report status</p>
    </div>
    """, unsafe_allow_html=True)
    if r.get("is_duplicate"):
        st.markdown(f"""
        <div class="duplicate-warn">
          <strong>⚠️ Possible duplicate detected:</strong>
          Your report may be related to an existing issue in this area.
          (Original: <code>{r.get('original_report_id','—')}</code>)
        </div>
        """, unsafe_allow_html=True)
    
    st.write("") # Spacer
    if st.button("🗺️ Submit another report", type="primary", use_container_width=True):
        st.session_state.last_submitted = None
        st.rerun()
    st.stop()

# ── Status Tracking Panel ──────────────────────────────────────────────────────
if st.session_state.show_tracking:
    with st.container():
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">📋 Track Your Report</div>', unsafe_allow_html=True)
        track_id = st.text_input("Enter your Report ID", placeholder="e.g. CI-2026-A3F7",
                                  key="track_input", label_visibility="collapsed").strip().upper()
        if st.button("Check Status", key="track_btn"):
            if track_id:
                report = get_report_by_id(track_id)
                if report:
                    urg = report.get("ai_urgency","Medium").lower()
                    badge_cls = f"badge-{urg}"
                    statuses = ["Submitted","In Progress","Resolved"]
                    cur_idx  = statuses.index(report["status"]) if report["status"] in statuses else 0
                    timeline = " → ".join([
                        f"**{'✅' if i < cur_idx else '🔵' if i == cur_idx else '⬜'} {s}**"
                        for i, s in enumerate(statuses)
                    ])
                    st.markdown(f"""
                    <div style="background: #F8FAFC; border-radius: 12px; padding: 20px; border: 1px solid #E2E8F0; margin: 16px 0;">
                      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <strong style="font-size: 18px; color: #0F172A;">{report['report_id']}</strong>
                        <span style="background:#F1F5F9; color:#475569; padding:4px 12px; border-radius:20px; font-size:12px; font-weight:600;">{report.get('ai_urgency','—')} Urgency</span>
                      </div>
                      <p style="margin:0 0 8px; font-size:14px; color: #334155;">📍 {report.get('location_name','—')}</p>
                      <p style="font-size:14px; color:#64748B; margin: 0;">{report.get('ai_summary') or report.get('description','')}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    st.markdown(timeline)
                    if report.get("assigned_department"):
                        st.info(f"Assigned to: **{report['assigned_department']}**")
                else:
                    st.error("Report not found. Please check the ID.")
            else:
                st.warning("Please enter a Report ID.")
        st.markdown('</div>', unsafe_allow_html=True)
    st.divider()

# ── Main layout: Map (left) + Form (right) ────────────────────────────────────
left_col, right_col = st.columns([1.2, 1], gap="large")

# ── LEFT: Map ─────────────────────────────────────────────────────────────────
with left_col:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🗺️ Select Location on Map</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">Click anywhere on the NUS campus map to set your issue location.</div>', unsafe_allow_html=True)

    # OneMap search
    search_q = st.text_input("🔍 Search campus location", placeholder="e.g. COM2, Central Library, UTown…", label_visibility="collapsed")

    search_lat, search_lng, search_name = None, None, None
    if search_q and len(search_q) >= 2:
        try:
            resp = httpx.get(
                "https://www.onemap.gov.sg/api/common/elastic/search",
                params={"searchVal": search_q, "returnGeom": "Y",
                        "getAddrDetails": "Y", "pageNum": 1},
                timeout=8,
            )
            results = resp.json().get("results", [])[:5]
            if results:
                options = {
                    f"{r.get('BUILDINGNAME') or r.get('ADDRESS','')}": r
                    for r in results if r.get("LATITUDE")
                }
                chosen_label = st.selectbox("Select a result:", list(options.keys()), label_visibility="visible")
                chosen = options[chosen_label]
                search_lat  = float(chosen["LATITUDE"])
                search_lng  = float(chosen["LONGITUDE"])
                search_name = chosen.get("BUILDINGNAME") or chosen.get("ADDRESS","")
                if st.button("📍 Use this location", key="use_search"):
                    st.session_state.selected_lat      = search_lat
                    st.session_state.selected_lng      = search_lng
                    st.session_state.selected_location = search_name
                    st.rerun()
        except Exception as e:
            st.caption(f"Search unavailable: {e}")

    # Build Folium map
    map_center = NUS_CENTER
    zoom_start = 16

    # If a location is already selected, centre on it
    if st.session_state.selected_lat:
        map_center = [st.session_state.selected_lat, st.session_state.selected_lng]
        zoom_start = 18

    m = folium.Map(
        location=map_center, zoom_start=zoom_start,
        tiles=None, prefer_canvas=True,
    )
    folium.TileLayer(
        tiles=ONEMAP_TILES, attr=ONEMAP_ATTR,
        name="OneMap", min_zoom=11, max_zoom=19,
    ).add_to(m)

    # ── Geolocation button (Fix 2) ─────────────────────────────────────────
    from folium.plugins import LocateControl
    LocateControl(
        auto_start=False,
        position="topright",
        strings={"title": "Use my current location"},
        flyTo=True,
        keepCurrentZoomLevel=False,
        drawCircle=True,
        drawMarker=True,
    ).add_to(m)

    # Show selected marker
    if st.session_state.selected_lat:
        folium.Marker(
            location=[st.session_state.selected_lat, st.session_state.selected_lng],
            tooltip=st.session_state.selected_location or "Selected location",
            icon=folium.Icon(color="blue", icon="map-marker", prefix="fa"),
        ).add_to(m)

    # Render map and capture clicks
    map_data = st_folium(m, width="100%", height=420, returned_objects=["last_clicked"])

    # Handle click
    if map_data and map_data.get("last_clicked"):
        clicked = map_data["last_clicked"]
        st.session_state.selected_lat      = clicked["lat"]
        st.session_state.selected_lng      = clicked["lng"]
        st.session_state.selected_location = f"{clicked['lat']:.5f}°N, {clicked['lng']:.5f}°E"

    # Show selected location
    if st.session_state.selected_lat:
        st.success(f"📍 **Selected:** {st.session_state.selected_location}  \n"
                   f"`{st.session_state.selected_lat:.5f}°N, {st.session_state.selected_lng:.5f}°E`")
    else:
        st.info("👆 Click on the map to select your issue location, or tap 📍 to use your current location")

    st.markdown('</div>', unsafe_allow_html=True)

# ── RIGHT: Report Form ─────────────────────────────────────────────────────────
with right_col:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">📝 Report an Issue</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">Fill in the details below to notify the campus team.</div>', unsafe_allow_html=True)

    with st.form("report_form", clear_on_submit=True):

        # Photo
        photo_file = st.file_uploader("📷 Add a photo (optional)",
                                       type=["jpg","jpeg","png","webp"],
                                       help="Photos help AI classify the issue more accurately")
        if photo_file:
            st.image(photo_file, use_column_width=True)

        # Location display (read-only)
        loc_display = st.session_state.selected_location or "No location selected yet"
        st.text_input("📍 Selected Location", value=loc_display, disabled=True)

        # Category
        category = st.selectbox("🏷️ Category", [
            "Accessibility", "Facilities", "Safety",
            "Cleanliness", "Utilities", "Other",
        ])

        # Description
        description = st.text_area("📄 Description (optional)",
                                    placeholder="Briefly describe the issue (e.g., Water leaking from the ceiling)...",
                                    max_chars=200,
                                    help="Max 200 characters")

        char_left = 200 - len(description)
        st.caption(f"✏️ {char_left} characters remaining")

        st.write("") # Spacer before button

        submitted = st.form_submit_button(
            "🤖 Submit & Analyse with AI",
            type="primary", use_container_width=True,
        )

    if submitted:
        if not st.session_state.selected_lat:
            st.error("⚠️ Please click on the map to select a location first.")
        else:
            # Save photo
            photo_path  = None
            image_bytes = None
            if photo_file:
                image_bytes = photo_file.read()
                ext         = photo_file.name.rsplit(".", 1)[-1].lower()
                os.makedirs("uploads", exist_ok=True)
                photo_path  = f"uploads/{uuid.uuid4()}.{ext}"
                with open(photo_path, "wb") as f:
                    f.write(image_bytes)

            with st.spinner("🤖 AI is analysing your report… (classifying, checking for duplicates, scoring urgency)"):
                nearby = get_nearby_reports(
                    st.session_state.selected_lat,
                    st.session_state.selected_lng,
                )
                ai_result = analyze_report(
                    category, description,
                    st.session_state.selected_location,
                    image_bytes, nearby,
                    api_key=_gemini_key,
                )

            report = create_report({
                "location_name":       st.session_state.selected_location,
                "location_lat":        st.session_state.selected_lat,
                "location_lng":        st.session_state.selected_lng,
                "category":            category,
                "description":         description,
                "photo_path":          photo_path,
                **ai_result,
            })

            st.session_state.last_submitted   = report
            st.session_state.selected_lat     = None
            st.session_state.selected_lng     = None
            st.session_state.selected_location = None
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)
    
    # Clean Tips box
    st.markdown("""
    <div style="background: transparent; padding: 0 10px;">
      <strong style="color: #475569; font-size: 14px;">💡 Quick Tips:</strong>
      <ul style="font-size:13px; color:#64748B; margin-top: 6px; padding-left:20px; line-height: 1.6;">
        <li>Adding a photo helps the AI automatically categorize the fault.</li>
        <li>Ensure your map pin is as accurate as possible to speed up maintenance routing.</li>
      </ul>
    </div>
    """, unsafe_allow_html=True)
