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
    Two separate checks so Gemini can't conflate them:
      Step 1 — Is it appropriate? (no offensive/adult content)
      Step 2 — Is it relevant?   (must visibly show a campus facility issue)
    Returns: {"appropriate": bool, "reason": str}
    Fails open if key is missing or API errors, so students are never blocked by outages.
    """
    if not image_bytes or not gemini_api_key.strip():
        return {"appropriate": True, "reason": ""}

    try:
        import google.generativeai as genai
        from PIL import Image
        import io, re, json

        genai.configure(api_key=gemini_api_key.strip())
        model = genai.GenerativeModel("gemini-1.5-flash")
        image = Image.open(io.BytesIO(image_bytes))

        # ── Step 1: Appropriateness check ──────────────────────────────
        prompt_safe = """Look at this image carefully.

Does it contain ANY of the following? Answer only YES or NO, then a dash, then one sentence reason.
- Nudity or sexual content
- Graphic violence, blood, or gore
- Hate symbols or extremist content
- Personally identifiable information (faces, ID cards, screens with personal data)

Format: YES - reason   OR   NO - reason"""

        resp_safe = model.generate_content([prompt_safe, image])
        safe_text = resp_safe.text.strip().upper()
        if safe_text.startswith("YES"):
            reason = resp_safe.text.strip().split("-", 1)[-1].strip()
            return {
                "appropriate": False,
                "reason": f"Photo contains inappropriate content: {reason}",
            }

        # ── Step 2: Relevance check ─────────────────────────────────────
        # Only runs if step 1 passed
        prompt_relevant = """You are reviewing a photo submitted for a university campus facility issue report.

Your job: decide if this photo is RELEVANT to a campus maintenance or facility issue.

RELEVANT means the photo shows one of these (even partially, even blurry, even from a distance):
- Physical damage: broken furniture, cracked walls, shattered glass, damaged equipment
- Cleanliness: overflowing bins, litter, dirty toilets, stains, pest evidence
- Safety hazards: blocked ramps/exits, missing handrails, flooded floor, exposed wires
- Infrastructure: faulty lights, broken doors/locks, leaking pipes, non-working lifts
- IT/facilities: broken screens, damaged lab equipment, disconnected cables
- Outdoor issues: damaged benches, broken signage, blocked pathways
- Any photo of a building, corridor, room, or outdoor campus area — even if the issue is subtle

NOT RELEVANT means the photo clearly shows:
- Clothing, fashion items, or accessories (laid flat, on a person, or on a hanger)
- Food, drinks, or meals
- Selfies or portraits with no campus context visible
- Screenshots, memes, documents, or digital content
- Animals or nature with no campus context
- Vehicles with no campus context

Be strict: if the photo clearly does NOT show a campus environment or physical issue, reject it.
If you are even slightly unsure, ACCEPT it.

Respond ONLY with JSON — no markdown fences:
{"relevant": true, "reason": ""}
or
{"relevant": false, "reason": "<one sentence, friendly, telling the student what to upload instead>"}"""

        resp_rel = model.generate_content([prompt_relevant, image])
        raw = re.sub(r"```json\s*|\s*```", "", resp_rel.text.strip()).strip()

        # Gemini sometimes returns a plain sentence instead of JSON — handle gracefully
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            # If we can't parse it, check if it contains negative signals
            lower = raw.lower()
            if any(w in lower for w in ["not relevant", "irrelevant", "false", "reject"]):
                return {
                    "appropriate": False,
                    "reason": "Please upload a photo that shows the actual campus issue you are reporting.",
                }
            return {"appropriate": True, "reason": ""}

        if not result.get("relevant", True):
            reason = result.get("reason", "Please upload a photo that shows the actual campus issue.")
            return {"appropriate": False, "reason": reason}

        return {"appropriate": True, "reason": ""}

    except Exception as e:
        print(f"[ai_service.check_image_content] {e}")
        return {"appropriate": True, "reason": ""}   # fail open



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
