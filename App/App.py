import streamlit as st
import os
import re
import random
import base64
import hashlib
import time
import pdfplumber
from collections import OrderedDict

from streamlit_tags import st_tags
from Courses import (
    resume_videos,
    interview_videos
)

# ---------------- Page Config ----------------
st.set_page_config(
    page_title="CareerScope AI",
    page_icon="🎯",
    layout="wide"
)

# ---------------- AI Client ----------------
try:
    from ai_client import ask_ai
except Exception:
    def ask_ai(prompt):
        return "AI service temporarily unavailable."

# ---------------- Constants ----------------
AI_CACHE_TTL = 30 * 60
AI_CACHE_MAX_SIZE = 20
PROMPT_VERSION = "v1.0.0"

# ---------------- Analytics Init ----------------
def init_analytics():
    if "analytics" not in st.session_state:
        st.session_state["analytics"] = {
            "resume_uploads": 0,
            "job_fit_runs": 0,
            "ai_calls": 0,
            "ai_cache_hits": 0,
            "ai_cache_misses": 0,
            "ai_feedback_positive": 0,
            "ai_feedback_negative": 0,
        }

init_analytics()

# ---------------- Sidebar ----------------
st.sidebar.title("CareerScope AI")
section = st.sidebar.radio(
    "Navigate",
    ["Resume Analysis", "Job Match", "About"]
)

st.sidebar.markdown("---")
st.sidebar.subheader("📊 Session Analytics")
for k, v in st.session_state["analytics"].items():
    st.sidebar.write(f"{k.replace('_',' ').title()}: {v}")

# ---------------- Helpers ----------------
def extract_text_from_pdf(path):
    text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text

def show_pdf(path):
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    st.markdown(
        f"""<iframe src="data:application/pdf;base64,{b64}"
        width="100%" height="900"></iframe>""",
        unsafe_allow_html=True
    )

def detect_experience(text):
    years = re.findall(r"(\d+)\+?\s+years", text.lower())
    y = max([int(x) for x in years], default=0)
    return "Senior / Lead" if y >= 8 else "Mid-level" if y >= 4 else "Junior" if y >= 1 else "Fresher"

def make_cache_key(*args):
    return hashlib.sha256("||".join(args).encode()).hexdigest()

def init_ai_cache():
    if "ai_cache" not in st.session_state:
        st.session_state["ai_cache"] = OrderedDict()

def is_cache_valid(entry):
    return time.time() - entry["timestamp"] < AI_CACHE_TTL

def enforce_cache_limit():
    while len(st.session_state["ai_cache"]) > AI_CACHE_MAX_SIZE:
        st.session_state["ai_cache"].popitem(last=False)

# ---------------- UI ----------------
st.title("🎯 CareerScope AI")

# ================= Resume Analysis =================
if section == "Resume Analysis":

    uploaded = st.file_uploader("Upload your resume (PDF)", type=["pdf"])

    if uploaded:
        st.session_state["analytics"]["resume_uploads"] += 1

        os.makedirs("uploads", exist_ok=True)
        path = f"uploads/{uploaded.name}"

        with open(path, "wb") as f:
            f.write(uploaded.getbuffer())

        st.session_state.pop("ai_cache", None)
        st.session_state.pop("job_fit_done", None)

        show_pdf(path)

        resume_text = extract_text_from_pdf(path)
        st.session_state["resume_text"] = resume_text

        skills = re.findall(
            r"\b(python|aws|docker|kubernetes|iot|5g|lte|ran|pmp|capm|scrum|ai|ml)\b",
            resume_text.lower()
        )

        st.metric("Experience Level", detect_experience(resume_text))
        st_tags("Detected Skills", sorted(set(skills)), key="skills")

        st.video(random.choice(resume_videos))
        st.video(random.choice(interview_videos))

# ================= Job Match =================
elif section == "Job Match":

    if "resume_text" not in st.session_state:
        st.warning("Upload a resume first.")
    else:
        jd = st.text_area("Paste Job Description")

        if st.button("Analyze Job Fit"):
            st.session_state["analytics"]["job_fit_runs"] += 1
            st.session_state["job_fit_done"] = True
            st.success("Job fit analyzed")

        if st.session_state.get("job_fit_done"):

            init_ai_cache()

            if st.button("Get AI Suggestions"):
                st.session_state["analytics"]["ai_calls"] += 1

                key = make_cache_key(
                    PROMPT_VERSION,
                    st.session_state["resume_text"],
                    jd
                )

                cache = st.session_state["ai_cache"]
                entry = cache.get(key)

                if entry and is_cache_valid(entry):
                    st.session_state["analytics"]["ai_cache_hits"] += 1
                    st.success("Loaded from cache")
                    st.write(entry["response"])
                else:
                    st.session_state["analytics"]["ai_cache_misses"] += 1
                    with st.spinner("Calling AI…"):
                        response = ask_ai(f"Resume:\n{st.session_state['resume_text']}\n\nJD:\n{jd}")
                        cache[key] = {"response": response, "timestamp": time.time()}
                        enforce_cache_limit()
                        st.write(response)

                col1, col2 = st.columns(2)
                if col1.button("👍 Helpful"):
                    st.session_state["analytics"]["ai_feedback_positive"] += 1
                if col2.button("👎 Not Helpful"):
                    st.session_state["analytics"]["ai_feedback_negative"] += 1

# ================= About =================
else:
    st.markdown("""
### About CareerScope AI

CareerScope AI provides privacy-first career insights using:
- Resume analysis
- Job matching
- AI guidance
- Cost-optimized LLM usage

No databases. No tracking. Just insights.
""")
