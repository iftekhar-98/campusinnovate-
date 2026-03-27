"""
database.py — SQLite storage for CampusInnovate (Streamlit version)
Uses Python's built-in sqlite3 — no extra install needed.
"""

import sqlite3
import uuid
from datetime import datetime, timedelta

DB_PATH = "campusinnovate.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id            TEXT UNIQUE NOT NULL,
            location_name        TEXT,
            location_lat         REAL,
            location_lng         REAL,
            category             TEXT,
            description          TEXT,
            photo_path           TEXT,
            ai_category          TEXT,
            ai_confidence        REAL,
            ai_urgency           TEXT,
            ai_summary           TEXT,
            ai_urgency_reason    TEXT,
            is_duplicate         INTEGER DEFAULT 0,
            original_report_id   TEXT,
            duplicate_cluster_id TEXT,
            status               TEXT DEFAULT 'Submitted',
            assigned_department  TEXT,
            staff_notes          TEXT,
            created_at           TEXT,
            updated_at           TEXT
        )
    """)
    conn.commit()
    conn.close()


def _new_id():
    return f"CI-{datetime.now().year}-{str(uuid.uuid4())[:4].upper()}"


def create_report(data: dict) -> dict:
    conn = get_conn()
    now  = datetime.utcnow().isoformat()
    rid  = _new_id()
    conn.execute("""
        INSERT INTO reports (
            report_id, location_name, location_lat, location_lng,
            category, description, photo_path,
            ai_category, ai_confidence, ai_urgency, ai_summary, ai_urgency_reason,
            is_duplicate, original_report_id, duplicate_cluster_id,
            status, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        rid,
        data.get("location_name"), data.get("location_lat"), data.get("location_lng"),
        data.get("category"), data.get("description"), data.get("photo_path"),
        data.get("ai_category"), data.get("ai_confidence"),
        data.get("ai_urgency"), data.get("ai_summary"), data.get("ai_urgency_reason"),
        1 if data.get("is_duplicate") else 0,
        data.get("original_report_id"), data.get("duplicate_cluster_id"),
        "Submitted", now, now,
    ))
    conn.commit()
    row = conn.execute("SELECT * FROM reports WHERE report_id=?", (rid,)).fetchone()
    conn.close()
    return dict(row)


def get_all_reports(status=None) -> list:
    conn = get_conn()
    rank = "CASE ai_urgency WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END"
    if status:
        rows = conn.execute(
            f"SELECT * FROM reports WHERE status=? ORDER BY {rank}, created_at DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT * FROM reports ORDER BY {rank}, created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_report_by_id(report_id: str) -> dict | None:
    conn = get_conn()
    row  = conn.execute("SELECT * FROM reports WHERE report_id=?", (report_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_nearby_reports(lat, lng, radius=0.003) -> list:
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM reports
        WHERE ABS(location_lat-?) < ? AND ABS(location_lng-?) < ?
          AND created_at >= datetime('now','-7 days')
        ORDER BY created_at DESC LIMIT 8
    """, (lat, radius, lng, radius)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_report(report_id, status, department=None, notes=None):
    conn = get_conn()
    now  = datetime.utcnow().isoformat()
    conn.execute("""
        UPDATE reports SET status=?, assigned_department=?, staff_notes=?, updated_at=?
        WHERE report_id=?
    """, (status, department, notes, now, report_id))
    conn.commit()
    conn.close()


def get_analytics() -> dict:
    conn = get_conn()
    total    = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    high     = conn.execute("SELECT COUNT(*) FROM reports WHERE ai_urgency='High'").fetchone()[0]
    dups     = conn.execute("SELECT COUNT(*) FROM reports WHERE is_duplicate=1").fetchone()[0]
    resolved = conn.execute("SELECT COUNT(*) FROM reports WHERE status='Resolved'").fetchone()[0]
    avg_conf = conn.execute("SELECT AVG(ai_confidence) FROM reports WHERE ai_confidence IS NOT NULL").fetchone()[0] or 0.75

    cats  = [dict(r) for r in conn.execute("SELECT category, COUNT(*) as count FROM reports GROUP BY category").fetchall()]
    urgs  = [dict(r) for r in conn.execute("SELECT ai_urgency, COUNT(*) as count FROM reports GROUP BY ai_urgency").fetchall()]
    daily = [dict(r) for r in conn.execute("""
        SELECT DATE(created_at) as date, COUNT(*) as count FROM reports
        WHERE created_at >= datetime('now','-30 days')
        GROUP BY DATE(created_at) ORDER BY date
    """).fetchall()]
    conn.close()
    return {
        "total": total, "high_urgency": high,
        "duplicate_ratio": round(dups / total * 100, 1) if total else 0,
        "resolved": resolved, "ai_accuracy": round(avg_conf * 100, 1),
        "categories": cats, "urgency": urgs, "daily": daily,
    }


def delete_all_and_reseed():
    conn = get_conn()
    conn.execute("DELETE FROM reports")
    conn.commit()
    conn.close()
    seed_sample_data()


# ── Sample data ──────────────────────────────────────────────────────────────

SAMPLES = [
    {
        "location_name": "COM2 Level 2 · North Wing Corridor",
        "location_lat": 1.2950, "location_lng": 103.7744,
        "category": "Facilities",
        "description": "Water leaking from ceiling tile, puddle forming on floor.",
        "ai_category": "Facilities", "ai_confidence": 0.92, "ai_urgency": "High",
        "ai_summary": "Ceiling water leak poses slip hazard and potential electrical risk.",
        "ai_urgency_reason": "Water damage near electrical fixtures — immediate action required.",
        "status": "Submitted",
    },
    {
        "location_name": "ENG1 Ground Floor · Main Entrance",
        "location_lat": 1.2998, "location_lng": 103.7719,
        "category": "Safety",
        "description": "Main handle on right door is completely detached. Propped open with a wedge.",
        "ai_category": "Vandalism", "ai_confidence": 0.88, "ai_urgency": "High",
        "ai_summary": "Entrance door handle detached — door unsecured, security risk after hours.",
        "ai_urgency_reason": "Unsecured building entrance after hours.",
        "status": "In Progress", "assigned_department": "Facilities Management",
    },
    {
        "location_name": "LIB Level 3 · Zone A",
        "location_lat": 1.2966, "location_lng": 103.7764,
        "category": "Facilities",
        "description": "Lights flickering in the quiet study zone.",
        "ai_category": "Utilities", "ai_confidence": 0.95, "ai_urgency": "Medium",
        "ai_summary": "Flickering lights in library study zone affecting student productivity.",
        "ai_urgency_reason": "Non-critical but affects learning environment.",
        "status": "Submitted",
    },
    {
        "location_name": "UTown · Residential College 4",
        "location_lat": 1.3044, "location_lng": 103.7742,
        "category": "Cleanliness",
        "description": "Rubbish overflowing from bins near common area.",
        "ai_category": "Cleanliness", "ai_confidence": 0.91, "ai_urgency": "Medium",
        "ai_summary": "Overflowing bins in residential common area require clearance.",
        "ai_urgency_reason": "Hygiene concern in high-traffic area.",
        "status": "Resolved", "assigned_department": "Cleaning Services",
    },
    {
        "location_name": "Science Drive 2 · Block S1",
        "location_lat": 1.2946, "location_lng": 103.7814,
        "category": "Accessibility",
        "description": "Ramp near entrance blocked by construction materials.",
        "ai_category": "Accessibility", "ai_confidence": 0.93, "ai_urgency": "High",
        "ai_summary": "Ramp obstruction prevents wheelchair access near Science block.",
        "ai_urgency_reason": "Accessibility barrier — immediate clearance needed.",
        "status": "Submitted",
    },
    {
        "location_name": "Yusof Ishak House · Level 1",
        "location_lat": 1.2982, "location_lng": 103.7756,
        "category": "Facilities",
        "description": "Air conditioning not working, temperature very high.",
        "ai_category": "Facilities", "ai_confidence": 0.89, "ai_urgency": "Medium",
        "ai_summary": "HVAC failure in student facility during peak hours.",
        "ai_urgency_reason": "Comfort issue affecting large number of students.",
        "status": "In Progress", "assigned_department": "Mechanical & Electrical",
    },
]


def seed_sample_data():
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    conn.close()
    if count > 0:
        return
    for i, s in enumerate(SAMPLES):
        fake_time = (datetime.utcnow() - timedelta(hours=(len(SAMPLES) - i) * 4)).isoformat()
        conn = get_conn()
        conn.execute("""
            INSERT INTO reports (
                report_id, location_name, location_lat, location_lng,
                category, description, ai_category, ai_confidence,
                ai_urgency, ai_summary, ai_urgency_reason,
                is_duplicate, status, assigned_department, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            _new_id(),
            s["location_name"], s["location_lat"], s["location_lng"],
            s["category"], s["description"],
            s["ai_category"], s["ai_confidence"], s["ai_urgency"],
            s["ai_summary"], s["ai_urgency_reason"],
            0, s.get("status", "Submitted"), s.get("assigned_department"),
            fake_time, fake_time,
        ))
        conn.commit()
        conn.close()
