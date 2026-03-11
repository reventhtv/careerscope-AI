"""
ai_client.py — Dual-provider AI client for CareerScope AI

Primary:  Google Gemini 1.5 Flash  (1,500 req/day free)
Fallback: Groq Llama 3.3 70B       (14,400 req/day free)

Environment variables to set in Render:
  GEMINI_API_KEY   — from Google AI Studio (aistudio.google.com)
  GROQ_API_KEY     — from Groq Console (console.groq.com)
  AI_MODEL         — optional override, default: gemini-1.5-flash
  GROQ_MODEL       — optional override, default: llama-3.3-70b-versatile
"""

import os
import logging

log = logging.getLogger("careerscopeai.ai")

# ── Config ─────────────────────────────────────────────────────
GEMINI_API_KEY = (
    os.environ.get("GEMINI_API_KEY")
    or os.environ.get("AI_API_KEY")
    or os.environ.get("GENAI_API_KEY")
)
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY")
GEMINI_MODEL   = os.environ.get("AI_MODEL",   "gemini-1.5-flash")
GROQ_MODEL     = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

# ── Gemini client ──────────────────────────────────────────────
_gemini_client = None
try:
    from google import genai as _genai
    _gemini_client = (
        _genai.Client(api_key=GEMINI_API_KEY)
        if GEMINI_API_KEY
        else _genai.Client()          # uses ADC if available
    )
    log.info("AI | Gemini client initialised (model=%s)", GEMINI_MODEL)
except Exception as exc:
    log.warning("AI | Gemini client unavailable: %s", exc)

# ── Groq client ────────────────────────────────────────────────
_groq_client = None
try:
    from groq import Groq as _Groq
    if GROQ_API_KEY:
        _groq_client = _Groq(api_key=GROQ_API_KEY)
        log.info("AI | Groq client initialised (model=%s)", GROQ_MODEL)
    else:
        log.warning("AI | GROQ_API_KEY not set — Groq fallback disabled")
except Exception as exc:
    log.warning("AI | Groq client unavailable: %s", exc)


# ── Quota error detection ──────────────────────────────────────
def _is_quota_error(msg: str) -> bool:
    triggers = ["429", "quota", "rate_limit", "resource_exhausted", "rateLimitExceeded"]
    m = msg.lower()
    return any(t in m for t in triggers)

def _is_unavailable(msg: str) -> bool:
    triggers = ["503", "unavailable", "overloaded", "server_error", "500"]
    m = msg.lower()
    return any(t in m for t in triggers)


# ── Gemini call ────────────────────────────────────────────────
def _ask_gemini(prompt: str) -> str:
    if _gemini_client is None:
        raise RuntimeError("Gemini client not initialised")
    response = _gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    return response.text if hasattr(response, "text") else str(response)


# ── Groq call ──────────────────────────────────────────────────
def _ask_groq(prompt: str) -> str:
    if _groq_client is None:
        raise RuntimeError("Groq client not initialised")
    completion = _groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=2048,
    )
    return completion.choices[0].message.content


# ── Public interface ───────────────────────────────────────────
def ask_ai(prompt: str) -> str:
    """
    Send a prompt to the best available AI provider.

    Strategy:
      1. Try Gemini 1.5 Flash
      2. On quota / unavailable error → fall back to Groq Llama 3.3 70B
      3. If both fail → return a user-friendly error message

    Always returns a string, never raises.
    """
    if not prompt or not prompt.strip():
        return "No input provided."

    if _gemini_client is None and _groq_client is None:
        return (
            "⚠️ **AI service not configured.**\n\n"
            "Please set `GEMINI_API_KEY` and/or `GROQ_API_KEY` "
            "in your Render environment variables."
        )

    # ── Attempt 1: Gemini ──────────────────────────────────────
    if _gemini_client is not None:
        try:
            result = _ask_gemini(prompt)
            log.info("AI | provider=gemini success")
            return result
        except Exception as exc:
            msg = str(exc)
            if _is_quota_error(msg) or _is_unavailable(msg):
                log.warning("AI | Gemini quota/unavailable — falling back to Groq: %s", msg[:120])
                # fall through to Groq
            else:
                # Unexpected Gemini error — still try Groq before giving up
                log.error("AI | Gemini unexpected error — trying Groq: %s", msg[:200])

    # ── Attempt 2: Groq fallback ───────────────────────────────
    if _groq_client is not None:
        try:
            result = _ask_groq(prompt)
            log.info("AI | provider=groq success (fallback)")
            return result
        except Exception as exc:
            msg = str(exc)
            log.error("AI | Groq also failed: %s", msg[:200])
            if _is_quota_error(msg):
                return (
                    "⚠️ **Both AI providers are rate-limited.**\n\n"
                    "Gemini and Groq daily quotas are both exhausted. "
                    "Please try again tomorrow or upgrade your API plan."
                )
            return (
                f"⚠️ **AI service temporarily unavailable.**\n\n"
                "Both providers returned errors. Please wait a minute and try again."
            )

    # ── Both clients exist but both failed above ───────────────
    return (
        "⚠️ **AI service temporarily unavailable.**\n\n"
        "Please wait 30–60 seconds and try again."
    )


# ── Health check (for /health endpoint) ───────────────────────
def ai_status() -> dict:
    """Returns which providers are configured — used by /health."""
    return {
        "gemini": {
            "configured": _gemini_client is not None,
            "model": GEMINI_MODEL,
        },
        "groq": {
            "configured": _groq_client is not None,
            "model": GROQ_MODEL,
        },
    }