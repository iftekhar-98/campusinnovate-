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

# ── Gemini API key — read here in main context where st.secrets is reliable ──
_gemini_key = ""
try:
    _gemini_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    pass  # Key missing or secrets not configured — AI will use rule-based fallback

# ── Init DB once ──────────────────────────────────────────────────────────────
init_db()
seed_sample_data()

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Hide default Streamlit chrome */
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding-top: 1rem; padding-bottom: 1rem; }

  /* App header */
  .app-header {
    background: linear-gradient(135deg, #1B2A47, #2563EB);
    border-radius: 14px; padding: 18px 24px; margin-bottom: 20px;
    display: flex; align-items: center; justify-content: space-between;
  }
  .app-header h1 { color: white; font-size: 22px; margin: 0; }
  .app-header p  { color: rgba(255,255,255,.75); font-size: 13px; margin: 4px 0 0; }

  /* Stat metric cards */
  .metric-box {
    background: white; border-radius: 12px; padding: 18px;
    box-shadow: 0 2px 8px rgba(0,0,0,.08); text-align: center;
    border-left: 4px solid #2563EB;
  }
  .metric-box .val { font-size: 28px; font-weight: 800; color: #1B2A47; }
  .metric-box .lbl { font-size: 12px; color: #64748B; margin-top: 4px; }

  /* Section card */
  .section-card {
    background: white; border-radius: 14px; padding: 22px;
    box-shadow: 0 2px 10px rgba(0,0,0,.07); margin-bottom: 16px;
  }
  .section-title { font-size: 16px; font-weight: 700; color: #1E293B; margin-bottom: 4px; }
  .section-sub   { font-size: 13px; color: #64748B; margin-bottom: 16px; }

  /* Report cards in tracking */
  .report-card {
    background: #F8FAFC; border-radius: 10px; padding: 16px;
    border-left: 4px solid #2563EB; margin-bottom: 10px;
  }
  .report-card.high   { border-left-color: #EF4444; }
  .report-card.medium { border-left-color: #F97316; }
  .report-card.low    { border-left-color: #F59E0B; }

  /* Urgency badges */
  .badge-high   { background:#FEE2E2; color:#B91C1C; padding:3px 10px; border-radius:999px; font-size:12px; font-weight:600; }
  .badge-medium { background:#FEF3C7; color:#92400E; padding:3px 10px; border-radius:999px; font-size:12px; font-weight:600; }
  .badge-low    { background:#D1FAE5; color:#065F46; padding:3px 10px; border-radius:999px; font-size:12px; font-weight:600; }

  /* Success box */
  .success-box {
    background: linear-gradient(135deg, #065F46, #10B981);
    border-radius: 14px; padding: 28px; text-align: center; color: white;
  }
  .success-box .report-id {
    background: rgba(255,255,255,.2); border-radius: 10px;
    padding: 14px; font-size: 26px; font-weight: 800;
    letter-spacing: 2px; margin: 16px 0;
  }
  .duplicate-warn {
    background: #FFFBEB; border: 1px solid #FDE68A; border-radius: 10px;
    padding: 12px 16px; font-size: 13px; color: #92400E;
  }

  /* Hide the Streamlit sidebar page navigation on the student page
     (students should not see or navigate to the Staff Dashboard) */
  [data-testid="stSidebarNav"] { display: none !important; }

  div[data-testid="stButton"] > button[kind="primary"] {
    background: #2563EB; border-radius: 10px;
    font-weight: 700; font-size: 15px; padding: 12px;
  }
  div[data-testid="stButton"] > button {
    border-radius: 10px; font-weight: 600;
  }
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

# Navigation — Track button only (staff dashboard is staff-only, accessed via its own URL)
col_nav1, col_nav2 = st.columns([1, 5])
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
      <div style="font-size:40px">✅</div>
      <h2 style="margin:10px 0 4px">Report Submitted!</h2>
      <p style="opacity:.85">Received and awaiting staff review.</p>
      <div class="report-id">{r['report_id']}</div>
      <p style="opacity:.75;font-size:13px">Save this ID to track your report status</p>
    </div>
    """, unsafe_allow_html=True)
    if r.get("is_duplicate"):
        st.markdown(f"""
        <div class="duplicate-warn" style="margin-top:12px">
          ⚠️ <strong>Possible duplicate detected.</strong>
          Your report may be related to an existing issue in this area.
          Original: <code>{r.get('original_report_id','—')}</code>
        </div>
        """, unsafe_allow_html=True)
    if st.button("🗺️ Submit another report", use_container_width=True):
        st.session_state.last_submitted = None
        st.rerun()
    st.stop()

# ── Status Tracking Panel ──────────────────────────────────────────────────────
if st.session_state.show_tracking:
    with st.container():
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("### 📋 Track Your Report")
        track_id = st.text_input("Enter your Report ID", placeholder="e.g. CI-2026-A3F7",
                                  key="track_input").strip().upper()
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
                    <div class="report-card {urg}">
                      <strong>{report['report_id']}</strong>
                      <span class="{badge_cls}" style="margin-left:10px">{report.get('ai_urgency','—')}</span>
                      <p style="margin:8px 0 4px;font-size:14px">📍 {report.get('location_name','—')}</p>
                      <p style="font-size:13px;color:#475569">{report.get('ai_summary') or report.get('description','')}</p>
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
left_col, right_col = st.columns([3, 2], gap="large")

# ── LEFT: Map ─────────────────────────────────────────────────────────────────
with left_col:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🗺️ Select Location on Map</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">Click anywhere on the NUS campus map to set your issue location</div>', unsafe_allow_html=True)

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
    # Adds a "locate me" button to the map that uses the browser's GPS.
    # When clicked, it centres the map on the user and drops a blue marker.
    # The user can then still click anywhere to adjust the pin manually.
    from folium.plugins import LocateControl
    LocateControl(
        auto_start=False,          # Don't auto-trigger — wait for user to tap the button
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
    map_data = st_folium(m, width="100%", height=450, returned_objects=["last_clicked"])

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
    st.markdown('<div class="section-sub">Fill in the details below and submit</div>', unsafe_allow_html=True)

    with st.form("report_form", clear_on_submit=True):

        # Photo
        photo_file = st.file_uploader("📷 Add a photo (optional)",
                                       type=["jpg","jpeg","png","webp"],
                                       help="Photos help AI classify the issue more accurately")
        if photo_file:
            st.image(photo_file, use_column_width=True)

        # Location display (read-only)
        loc_display = st.session_state.selected_location or "No location selected yet"
        st.text_input("📍 Location (select on map)", value=loc_display, disabled=True)

        # Category
        category = st.selectbox("🏷️ Category", [
            "Accessibility", "Facilities", "Safety",
            "Cleanliness", "Utilities", "Other",
        ])

        # Description
        description = st.text_area("📄 Description (optional)",
                                    placeholder="Briefly describe the issue…",
                                    max_chars=200,
                                    help="Max 200 characters")

        char_left = 200 - len(description)
        st.caption(f"{char_left} characters remaining")

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

    # Tips box
    st.markdown("""
    <div class="section-card" style="margin-top:0">
      <div class="section-title">💡 Tips</div>
      <ul style="font-size:13px;color:#475569;margin:0;padding-left:18px">
        <li>Click exactly on the building or area with the issue</li>
        <li>Use the search bar to find a specific building quickly</li>
        <li>Adding a photo improves AI accuracy significantly</li>
        <li>After submitting, save your Report ID to track progress</li>
      </ul>
    </div>
    """, unsafe_allow_html=True)
