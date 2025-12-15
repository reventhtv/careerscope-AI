"""
ai_client.py
-----------------
AI client for CareerScope AI using Google Gemini (google-genai).

Features:
- Reads API key from Streamlit secrets or environment variables
- Gracefully handles model overload (503 UNAVAILABLE)
- Never crashes Streamlit UI
- Returns clean, user-facing messages
"""

import os
import traceback

# -------------------- Helpers --------------------

def _get_secret(key: str):
    """
    Try reading from Streamlit secrets first, then environment variables
    """
    try:
        import streamlit as st
        if key in st.secrets:
            return st.secrets.get(key)
    except Exception:
        pass
    return os.environ.get(key)


# -------------------- Config --------------------

API_KEY = (
    _get_secret("AI_API_KEY")
    or _get_secret("GEMINI_API_KEY")
    or _get_secret("GENAI_API_KEY")
)

DEFAULT_MODEL = _get_secret("AI_MODEL") or "gemini-2.5-flash"

# -------------------- Gemini Init --------------------

_genai_client = None
_has_genai = False

try:
    from google import genai
    _has_genai = True
except Exception:
    _has_genai = False


def _init_client():
    global _genai_client
    if not _has_genai:
        return None

    try:
        if API_KEY:
            _genai_client = genai.Client(api_key=API_KEY)
        else:
            _genai_client = genai.Client()
        return _genai_client
    except Exception:
        _genai_client = None
        return None


if _has_genai:
    _init_client()


# -------------------- Core Call --------------------

def call_gemini(prompt: str, model: str = None):
    if not _has_genai or _genai_client is None:
        raise RuntimeError("Gemini SDK not initialized.")

    model = model or DEFAULT_MODEL

    response = _genai_client.models.generate_content(
        model=model,
        contents=prompt
    )

    # Handle different response shapes safely
    if hasattr(response, "text"):
        return response.text

    return str(response)


# -------------------- Public API --------------------

def ask_ai(prompt: str):
    """
    Safe wrapper used by App.py
    Always returns a string (never raises)
    """

    if not prompt or not prompt.strip():
        return "No input provided for AI analysis."

    try:
        return call_gemini(prompt)

    except Exception as e:
        msg = str(e)

        # ---- Gemini overload / rate limit ----
        if "503" in msg or "UNAVAILABLE" in msg:
            return (
                "⚠️ **AI service is temporarily busy**\n\n"
                "The Gemini model is under heavy load right now.\n"
                "Please wait **30–60 seconds** and try again.\n\n"
                "Your analysis and data are safe."
            )

        # ---- Generic fallback ----
        return (
            "⚠️ **AI encountered an unexpected issue**\n\n"
            f"Details: {msg}"
        )
