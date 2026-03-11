"""
ai_client.py — Google Gemini client for CareerScope AI
No Streamlit dependency; reads API key from environment variables.
Set GEMINI_API_KEY in your Render dashboard (or local .env).
"""

import os

API_KEY     = os.environ.get("GEMINI_API_KEY") or os.environ.get("AI_API_KEY") or os.environ.get("GENAI_API_KEY")
GEMINI_MODEL = os.environ.get("AI_MODEL", "gemini-1.5-flash")

_client = None

try:
    from google import genai as _genai
    _client = _genai.Client(api_key=API_KEY) if API_KEY else _genai.Client()
except Exception as _e:
    _client = None


def ask_ai(prompt: str) -> str:
    """
    Send a prompt to Gemini and return a plain-text response.
    Always returns a string — never raises.
    """
    if not prompt or not prompt.strip():
        return "No input provided."

    if _client is None:
        return (
            "⚠️ **AI service not configured.**\n\n"
            "Please set the `GEMINI_API_KEY` environment variable in your Render dashboard "
            "and redeploy the service."
        )

    try:
        response = _client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        return response.text if hasattr(response, "text") else str(response)

    except Exception as exc:
        msg = str(exc)
        if "503" in msg or "UNAVAILABLE" in msg:
            return (
                "⚠️ **AI service is temporarily busy.**\n\n"
                "The Gemini model is under heavy load. "
                "Please wait 30–60 seconds and try again."
            )
        if "429" in msg or "QUOTA" in msg.upper():
            return (
                "⚠️ **API quota reached.**\n\n"
                "Your Gemini API quota has been exceeded. "
                "Please check your Google AI Studio usage limits."
            )
        return f"⚠️ **AI error:** {msg}"