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

def check_image_content(image_bytes: bytes, gemini_api_key: str = "") -> dict:
    """
    Image content governance using Google Gemini Vision (gemini-1.5-flash).

    Checks TWO things:
      1. Is the image appropriate? (no offensive/disturbing content)
      2. Is the image relevant? (actually shows a campus facility issue)

    Returns: {"appropriate": bool, "reason": str}

    Falls back to {"appropriate": True} if no key is configured,
    so the form never breaks if Gemini is unavailable.
    """
    if not image_bytes or not gemini_api_key.strip():
        return {"appropriate": True, "reason": ""}

    try:
        import google.generativeai as genai
        from PIL import Image
        import io

        # ── Configure Gemini with the key ──────────────────────────────
        genai.configure(api_key=gemini_api_key.strip())
        model = genai.GenerativeModel("gemini-1.5-flash")

        # ── Convert bytes → PIL Image (what Gemini Vision expects) ─────
        image = Image.open(io.BytesIO(image_bytes))

        prompt = """You are a content moderator for a university campus issue-reporting system.

A student has uploaded a photo to accompany a maintenance/facility report.

Evaluate this image on TWO criteria:

1. APPROPRIATENESS: Does it contain offensive, disturbing, violent, or adult content?
2. RELEVANCE: Does it plausibly show a campus environment or a physical issue
   (e.g. a broken door, water leak, dirty area, damaged equipment, blocked ramp,
   faulty light, vandalism, overflowing bin, etc.)?
   Accept photos even if blurry or taken from a distance.
   Reject only if clearly unrelated (selfie, food, meme, screenshot, etc.).

Respond ONLY with JSON — no markdown, no explanation:
{"appropriate": true, "reason": ""}
or
{"appropriate": false, "reason": "<brief user-friendly explanation>"}"""

        response = model.generate_content([prompt, image])
        raw = response.text.strip()

        # Strip any accidental markdown fences
        import re, json
        raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
        result = json.loads(raw)

        return {
            "appropriate": bool(result.get("appropriate", True)),
            "reason":      result.get("reason", ""),
        }

    except Exception as e:
        print(f"[ai_service.check_image_content] {e}")
        return {"appropriate": True, "reason": ""}   # fail open — never block on API error


def check_content(description: str, api_key: str = "") -> dict:
    """
    Content governance — analyse the description text for appropriateness.
    Returns {"appropriate": bool, "reason": str}

    What Groq/Llama CAN do:
      ✅ Analyse description TEXT for spam, abuse, or off-topic content.

    What Groq/Llama CANNOT do:
      ❌ Analyse uploaded IMAGES — Llama is a text-only model.
         For image moderation, a vision API such as Google Vision SafeSearch
         or AWS Rekognition would be required (outside current scope).
    """
    text = (description or "").strip()

    # Quick local checks (no API call needed for obvious cases)
    import re
    if len(text) < 10:
        return {"appropriate": False,
                "reason": "Description is too short. Please provide at least a brief description of the issue."}

    spam_re = [r"^(.)\1{9,}$", r"^[^a-zA-Z\u0080-\uFFFF]{0,3}$",
               r"(?i)^(test\d*|asdf|qwerty|lorem ipsum|1234|abc)$"]
    for pat in spam_re:
        if re.search(pat, text):
            return {"appropriate": False,
                    "reason": "Description appears to be a test or spam entry. Please describe a real campus issue."}

    if not api_key:
        return {"appropriate": True, "reason": ""}

    key = api_key.strip()
    try:
        from groq import Groq
        client = Groq(api_key=key)
        prompt = f"""You are a content moderator for a university campus issue-reporting system.

Review the description below and decide if it is appropriate for submission.

Description: "{text}"

APPROPRIATE: describes a genuine campus issue in any language (cleanliness, safety, facilities, IT, landscaping, noise, accessibility, vandalism, etc.)
INAPPROPRIATE: offensive/abusive language, threats, obvious spam, or completely unrelated to any campus facility.

Respond ONLY with JSON, no markdown:
{{"appropriate": true, "reason": ""}}
or
{{"appropriate": false, "reason": "<brief, user-friendly explanation>"}}"""

        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
            temperature=0.0,
        )
        import json, re as _re
        raw = _re.sub(r"```json\s*|\s*```", "", resp.choices[0].message.content.strip()).strip()
        result = json.loads(raw)
        return {"appropriate": bool(result.get("appropriate", True)),
                "reason": result.get("reason", "")}
    except Exception as e:
        print(f"[ai_service.check_content] {e}")
        return {"appropriate": True, "reason": ""}   # fail open


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
