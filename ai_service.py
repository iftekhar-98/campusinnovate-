"""
ai_service.py — Gemini AI for CampusInnovate (Streamlit version)

The API key is passed in directly from streamlit_app.py where st.secrets
is guaranteed to be available. This module never touches st.secrets itself,
which avoids silent failures caused by module-level import ordering on
Streamlit Cloud.
"""

import json
import io
import os
import google.generativeai as genai
from PIL import Image


def analyze_report(
    category: str,
    description: str,
    location_name: str,
    image_bytes: bytes = None,
    nearby_reports: list = None,
    api_key: str = "",
) -> dict:
    """
    Analyse a campus issue report with Gemini AI.

    Parameters
    ----------
    category        : User-selected category string
    description     : Free-text description (may be empty)
    location_name   : Human-readable location label
    image_bytes     : Raw bytes of an uploaded photo (optional)
    nearby_reports  : List of recent nearby report dicts for duplicate detection
    api_key         : Gemini API key — pass st.secrets["GEMINI_API_KEY"] from the
                      main Streamlit app. Falls back to GEMINI_API_KEY env var if empty.

    Returns a dict with keys:
        ai_category, ai_confidence, ai_urgency, ai_summary,
        ai_urgency_reason, is_duplicate, original_report_id
    """

    # ── Resolve API key ────────────────────────────────────────────────────────
    key = (api_key or "").strip()
    if not key:
        key = os.getenv("GEMINI_API_KEY", "").strip()

    if not key:
        print("[ai_service] No API key available — using rule-based fallback.")
        return _fallback(category, description, location_name)

    # ── Build model ────────────────────────────────────────────────────────────
    try:
        genai.configure(api_key=key)
        model = genai.GenerativeModel("gemini-1.5-flash")
    except Exception as e:
        print(f"[ai_service] Failed to initialise Gemini model: {type(e).__name__}: {e}")
        return _fallback(category, description, location_name)

    # ── Build nearby-reports context for duplicate detection ───────────────────
    nearby_ctx = ""
    if nearby_reports:
        nearby_ctx = "\n\nRecent reports within 300 m (last 7 days):\n"
        for r in nearby_reports[:6]:
            nearby_ctx += (
                f"  [{r.get('report_id')}] "
                f"{r.get('ai_category', r.get('category', ''))}: "
                f"{(r.get('description') or '')[:80]} "
                f"@ {r.get('location_name', '')}\n"
            )

    # ── Prompt ─────────────────────────────────────────────────────────────────
    prompt = f"""You are an AI assistant for CampusInnovate, a campus operations system
for the National University of Singapore (NUS).

Analyse the following campus issue report and respond ONLY with a valid JSON object.
Do NOT include markdown fences, code blocks, or any extra text — just the raw JSON.

--- REPORT ---
User-selected category : {category}
Location               : {location_name}
Description            : {description or "(none provided)"}
{nearby_ctx}
--- END REPORT ---

Return exactly this JSON structure (no extra keys):
{{
  "ai_category"        : "<one of: Facilities, Safety, Accessibility, Cleanliness, Utilities, Vandalism, Other>",
  "ai_confidence"      : <float between 0.0 and 1.0>,
  "ai_urgency"         : "<High | Medium | Low>",
  "ai_summary"         : "<1-2 sentence summary written for operations staff>",
  "ai_urgency_reason"  : "<one sentence explaining why this urgency level was chosen>",
  "is_duplicate"       : <true | false>,
  "original_report_id" : "<the report_id string if this is a duplicate, otherwise null>"
}}

Urgency guidelines:
  High   — safety hazards, water leaks, blocked accessibility ramps, unsecured entrances
  Medium — facility faults affecting service (HVAC, broken fixtures), recurring nuisances
  Low    — minor aesthetics, non-urgent suggestions, cosmetic issues

Duplicate: mark true only if this report clearly describes the same physical problem
as one of the nearby reports listed above (same area + same issue type within 24 h)."""

    # ── Call Gemini ─────────────────────────────────────────────────────────────
    parts = [prompt]
    if image_bytes:
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img.thumbnail((1024, 1024))
            parts.append(img)
        except Exception as img_err:
            print(f"[ai_service] Could not attach image: {img_err}")

    try:
        response = model.generate_content(parts)
        text = response.text.strip()

        # Strip any accidental markdown fences Gemini sometimes adds
        if text.startswith("```"):
            lines = text.splitlines()
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

        result = json.loads(text)

        # Ensure all expected keys exist
        result.setdefault("ai_category",        category)
        result.setdefault("ai_confidence",      0.75)
        result.setdefault("ai_urgency",         "Medium")
        result.setdefault("ai_summary",         "")
        result.setdefault("ai_urgency_reason",  "")
        result.setdefault("is_duplicate",       False)
        result.setdefault("original_report_id", None)

        # Normalise types
        result["ai_confidence"] = float(result["ai_confidence"])
        result["is_duplicate"]  = bool(result["is_duplicate"])

        return result

    except Exception as e:
        print(f"[ai_service] Gemini call/parse error: {type(e).__name__}: {e}")
        return _fallback(category, description, location_name)


# ── Rule-based fallback ────────────────────────────────────────────────────────

def _fallback(category: str, description: str, location_name: str) -> dict:
    """Simple keyword-based classifier used when Gemini is unavailable."""
    text = (description or "").lower()
    urgency = "Medium"
    if any(k in text for k in ["water", "leak", "fire", "block", "electric",
                                "unsafe", "danger", "collapse", "flood", "smoke"]):
        urgency = "High"
    elif any(k in text for k in ["minor", "cosmetic", "paint", "dim", "smell"]):
        urgency = "Low"

    return {
        "ai_category":        category,
        "ai_confidence":      0.60,
        "ai_urgency":         urgency,
        "ai_summary":         f"{category} issue reported at {location_name}. {(description or '')[:120]}".strip(),
        "ai_urgency_reason":  "Classified by rule-based fallback — Gemini API key not configured.",
        "is_duplicate":       False,
        "original_report_id": None,
    }
