# ai_client.py
# Safe placeholder so your app doesn't crash if AI isn't enabled yet.

import os

def ask_ai(prompt: str):
    """
    Placeholder AI function.
    If AI_API_KEY is not set, this returns a fallback message.
    Later you can replace this with Gemini or Z-ai API calls.
    """
    api_key = os.getenv("AI_API_KEY")

    if not api_key:
        # No API key = no AI call, so return a basic message
        return "AI suggestions are not enabled yet. Add your AI_API_KEY in Streamlit secrets to activate this feature."

    # TODO: Replace with real AI provider call (Gemini/Z-ai)
    return "Real AI suggestions will appear here once the API client is connected."
