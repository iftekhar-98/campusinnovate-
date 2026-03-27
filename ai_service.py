"""
ai_service.py — Gemini AI for CampusInnovate (Streamlit version)
Reads GEMINI_API_KEY from st.secrets (Streamlit Cloud) or environment.
"""

import json
import io
import os
from typing import Optional
import google.generativeai as genai
from PIL import Image


def _get_model():
    # Try Streamlit secrets first, then environment variable
    try:
        import streamlit as st
        key = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        key = ""
    if not key:
        key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        raise EnvironmentError("No GEMINI_API_KEY found.")
    genai.configure(api_key=key)
    return genai.GenerativeModel("gemini-1.5-flash")


def analyze_report(category, description, location_name,
                   image_bytes=None, nearby_reports=None) -> dict:
    try:
        model = _get_model()
    except EnvironmentError:
        return _fallback(category, description, location_name)

    nearby_ctx = ""
    if nearby_reports:
        nearby_ctx = "\n\nRecent reports within 300 m (last 7 days):\n"
        for r in (nearby_reports or [])[:6]:
            nearby_ctx += (
                f"  [{r.get('report_id')}] "
                f"{r.get('ai_category', r.get('category'))}: "
                f"{(r.get('description') or '')[:80]} "
                f"@ {r.get('location_name')}\n"
            )

    prompt = f"""You are an AI assistant for CampusInnovate, a campus operations system
for the National University of Singapore (NUS).

Analyse the following campus issue report and respond ONLY with a valid JSON object
(no markdown fences, no extra text).

--- REPORT ---
User-selected category : {category}
Location               : {location_name}
Description            : {description or "(none provided)"}
{nearby_ctx}
--- END REPORT ---

Return exactly this JSON structure:
{{
  "ai_category"        : "<one of: Facilities, Safety, Accessibility, Cleanliness, Utilities, Vandalism, Other>",
  "ai_confidence"      : <float 0.0-1.0>,
  "ai_urgency"         : "<High | Medium | Low>",
  "ai_summary"         : "<1-2 sentence summary for operations staff>",
  "ai_urgency_reason"  : "<brief reason for urgency level>",
  "is_duplicate"       : <true | false>,
  "original_report_id" : "<report_id if duplicate, else null>"
}}

Urgency: High=safety/water/access hazards. Medium=facility faults affecting service. Low=minor/aesthetic."""

    parts = [prompt]
    if image_bytes:
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img.thumbnail((1024, 1024))
            parts.append(img)
        except Exception:
            pass

    try:
        response = model.generate_content(parts)
        text = response.text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.lower().startswith("json"):
                text = text[4:]
        result = json.loads(text.strip())
        result.setdefault("ai_category",       category)
        result.setdefault("ai_confidence",     0.75)
        result.setdefault("ai_urgency",        "Medium")
        result.setdefault("ai_summary",        "")
        result.setdefault("ai_urgency_reason", "")
        result.setdefault("is_duplicate",      False)
        result.setdefault("original_report_id", None)
        result["ai_confidence"] = float(result["ai_confidence"])
        return result
    except Exception as e:
        print(f"Gemini error: {e}")
        return _fallback(category, description, location_name)


def _fallback(category, description, location_name) -> dict:
    text = (description or "").lower()
    urgency = "Medium"
    if any(k in text for k in ["water","leak","fire","block","electric","unsafe","danger","collapse"]):
        urgency = "High"
    elif any(k in text for k in ["minor","cosmetic","paint","dim"]):
        urgency = "Low"
    return {
        "ai_category": category, "ai_confidence": 0.60,
        "ai_urgency": urgency,
        "ai_summary": f"Issue reported at {location_name}. {(description or '')[:120]}",
        "ai_urgency_reason": "Classified by rule-based fallback (add Gemini API key for full AI).",
        "is_duplicate": False, "original_report_id": None,
    }
