"""
ai_service.py — CampusInnovate AI Service (Groq / Llama 3.3)

Uses Groq's free API with Llama 3.3-70b for issue classification.
The api_key is passed in from streamlit_app.py where st.secrets is reliable.
"""

import json
import os
from groq import Groq


def analyze_report(
    category: str,
    description: str,
    location_name: str,
    image_bytes: bytes = None,
    nearby_reports: list = None,
    api_key: str = "",
) -> dict:
    """
    Analyse a campus issue report using Groq (Llama 3.3-70b).

    Returns a dict with:
        ai_category, ai_confidence, ai_urgency, ai_summary,
        ai_urgency_reason, is_duplicate, original_report_id
    """

    # ── Resolve API key ────────────────────────────────────────────────────────
    key = (api_key or "").strip()
    if not key:
        key = os.getenv("GROQ_API_KEY", "").strip()

    if not key:
        print("[ai_service] No GROQ_API_KEY found — using rule-based fallback.")
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
    prompt = f"""You are an AI assistant for CampusInnovate, a campus issue reporting system
for the National University of Singapore (NUS).

Analyse the campus issue report below and respond ONLY with a valid JSON object.
No markdown, no code fences, no explanation — just the raw JSON.

--- REPORT ---
User-selected category : {category}
Location               : {location_name}
Description            : {description or "(none provided)"}
{nearby_ctx}
--- END REPORT ---

Return exactly this JSON (no extra keys):
{{
  "ai_category"        : "<one of: Facilities, Safety, Accessibility, Cleanliness, Utilities, Vandalism, Other>",
  "ai_confidence"      : <float 0.0-1.0>,
  "ai_urgency"         : "<High | Medium | Low>",
  "ai_summary"         : "<1-2 sentence summary for operations staff>",
  "ai_urgency_reason"  : "<one sentence explaining the urgency level>",
  "is_duplicate"       : <true | false>,
  "original_report_id" : "<report_id if duplicate, else null>"
}}

Urgency rules:
  High   = safety hazards, water leaks, blocked accessibility ramps, unsecured doors
  Medium = HVAC failures, broken fixtures, recurring nuisances affecting service
  Low    = minor aesthetics, cosmetic issues, non-urgent suggestions

Duplicate = true only if this report describes the same physical issue as a nearby
report in the same area within the last 24 hours."""

    # ── Call Groq API ──────────────────────────────────────────────────────────
    try:
        client = Groq(api_key=key)
        chat   = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are a JSON-only response bot. You never include markdown, "
                               "code fences, or explanatory text. You respond only with raw JSON.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0.1,   # Low temperature = consistent, structured output
            max_tokens=512,
        )

        text = chat.choices[0].message.content.strip()

        # Safety: strip any accidental fences
        if text.startswith("```"):
            lines = [l for l in text.splitlines() if not l.strip().startswith("```")]
            text  = "\n".join(lines).strip()

        result = json.loads(text)

        # Ensure all expected keys exist with safe defaults
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
        print(f"[ai_service] Groq error: {type(e).__name__}: {e}")
        return _fallback(category, description, location_name)


# ── Rule-based fallback ────────────────────────────────────────────────────────

def _fallback(category: str, description: str, location_name: str) -> dict:
    """Keyword-based classifier used when the API is unavailable."""
    text    = (description or "").lower()
    urgency = "Medium"
    if any(k in text for k in ["water","leak","fire","block","electric",
                                "unsafe","danger","collapse","flood","smoke"]):
        urgency = "High"
    elif any(k in text for k in ["minor","cosmetic","paint","dim","smell"]):
        urgency = "Low"

    return {
        "ai_category":        category,
        "ai_confidence":      0.60,
        "ai_urgency":         urgency,
        "ai_summary":         f"{category} issue reported at {location_name}. {(description or '')[:120]}".strip(),
        "ai_urgency_reason":  "Classified by rule-based fallback — GROQ_API_KEY not configured.",
        "is_duplicate":       False,
        "original_report_id": None,
    }
