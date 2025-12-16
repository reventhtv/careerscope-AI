import streamlit as st
import os
import re
import random
import base64
import pdfplumber

from streamlit_tags import st_tags
from Courses import (
    ds_course, web_course, android_course,
    ios_course, uiux_course,
    resume_videos, interview_videos
)

# ===================== PAGE CONFIG =====================
st.set_page_config(
    page_title="CareerScope AI",
    page_icon="🎯",
    layout="wide"
)

# ===================== AI CLIENT =====================
try:
    from ai_client import ask_ai
except Exception:
    def ask_ai(prompt):
        return "AI service unavailable."

# ===================== SESSION STATE INIT =====================
if "resume_uploaded" not in st.session_state:
    st.session_state.resume_uploaded = False

if "resume_text" not in st.session_state:
    st.session_state.resume_text = ""

if "resume_path" not in st.session_state:
    st.session_state.resume_path = ""

# ===================== HELPERS =====================

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
        f"""
        <iframe src="data:application/pdf;base64,{b64}"
        width="100%" height="900"></iframe>
        """,
        unsafe_allow_html=True
    )


def course_recommender(course_list):
    st.subheader("📚 Course Recommendations")
    k = st.slider("Number of recommendations", 1, 10, 5)
    random.shuffle(course_list)
    for i, (name, link) in enumerate(course_list[:k], 1):
        st.markdown(f"{i}. [{name}]({link})")

# ===================== SCORING LOGIC =====================

def calculate_structure_score(resume_text):
    checks = {
        "email": bool(re.search(r"\S+@\S+\.\S+", resume_text)),
        "phone": bool(re.search(r"\+?\d[\d\s\-]{8,}", resume_text)),
        "education": "education" in resume_text.lower(),
        "experience": "experience" in resume_text.lower(),
        "skills": "skills" in resume_text.lower(),
    }
    score = int((sum(checks.values()) / len(checks)) * 100)
    return score, checks


def experience_level(resume_text):
    years = re.findall(r"\b(\d+)\+?\s+years?\b", resume_text.lower())
    years = [int(y) for y in years] if years else []
    max_years = max(years) if years else 0

    if max_years >= 8:
        return "Experienced"
    elif max_years >= 3:
        return "Mid-level"
    else:
        return "Entry-level"

# ===================== DOMAIN DETECTION =====================

DOMAINS = {
    "Telecommunications": ["lte", "5g", "ran", "telecom", "ericsson", "verisure"],
    "Embedded Systems": ["embedded", "firmware", "rtos", "cortex", "microcontroller"],
    "DevOps / Platform": ["docker", "kubernetes", "ci/cd", "terraform", "cloud"],
    "Data Science": ["machine learning", "tensorflow", "pytorch", "data science"],
}

def detect_domain(resume_text):
    scores = {d: 0 for d in DOMAINS}
    for domain, keywords in DOMAINS.items():
        for kw in keywords:
            if kw in resume_text.lower():
                scores[domain] += 1
    best = max(scores, key=scores.get)
    confidence = int((scores[best] / max(1, sum(scores.values()))) * 100)
    return best, confidence

# ===================== HEADER =====================
st.title("🎯 CareerScope AI")
st.caption("Career & Role Intelligence Platform")

# ===================== SIDEBAR =====================
page = st.sidebar.radio(
    "Navigate",
    ["Resume Overview", "Career Insights", "Growth & Guidance", "Job Match"]
)

st.sidebar.markdown("---")
pdf_file = st.sidebar.file_uploader("Upload Resume (PDF)", type=["pdf"])

if pdf_file:
    os.makedirs("Uploaded_Resumes", exist_ok=True)
    save_path = f"Uploaded_Resumes/{pdf_file.name}"

    with open(save_path, "wb") as f:
        f.write(pdf_file.getbuffer())

    st.session_state.resume_text = extract_text_from_pdf(save_path)
    st.session_state.resume_uploaded = True
    st.session_state.resume_path = save_path

# ===================== RESUME OVERVIEW =====================
if page == "Resume Overview":
    if st.session_state.resume_uploaded:
        st.subheader("📄 Resume Preview")
        show_pdf(st.session_state.resume_path)
    else:
        st.info("Upload a resume to begin analysis.")

# ===================== CAREER INSIGHTS =====================
if page == "Career Insights":

    if not st.session_state.resume_uploaded:
        st.warning("Please upload a resume first.")
        st.stop()

    resume_text = st.session_state.resume_text

    st.subheader("📊 Career Insights")

    # ATS SCORE
    ats_score, ats_checks = calculate_structure_score(resume_text)
    st.markdown("### 📈 Resume Structure Score (ATS Readiness)")
    st.progress(ats_score)
    st.metric("Score", f"{ats_score}%")

    # ✅ RESUME STRENGTH BREAKDOWN (NOW GUARANTEED)
    st.markdown("### 🧩 Resume Strength Breakdown")

    col1, col2 = st.columns(2)
    with col1:
        st.write("📧 Contact Info:", "✅" if ats_checks["email"] and ats_checks["phone"] else "❌")
        st.write("🎓 Education Section:", "✅" if ats_checks["education"] else "❌")
    with col2:
        st.write("💼 Experience Section:", "✅" if ats_checks["experience"] else "❌")
        st.write("🛠 Skills Section:", "✅" if ats_checks["skills"] else "❌")

    st.caption("Explains exactly why your ATS score is what it is.")

    # EXPERIENCE
    st.markdown("### 🧭 Experience Level")
    st.info(experience_level(resume_text))

    # DOMAIN
    domain, confidence = detect_domain(resume_text)
    st.markdown("### 🎯 Primary Technical Domain")
    st.success(f"{domain} ({confidence}% confidence)")

# ===================== GROWTH & GUIDANCE =====================
if page == "Growth & Guidance":
    if not st.session_state.resume_uploaded:
        st.warning("Upload a resume to get recommendations.")
        st.stop()

    course_recommender(ds_course)
    st.subheader("🎥 Resume Tips")
    st.video(random.choice(resume_videos))
    st.subheader("🎥 Interview Tips")
    st.video(random.choice(interview_videos))

# ===================== JOB MATCH =====================
if page == "Job Match":
    if not st.session_state.resume_uploaded:
        st.warning("Upload a resume to match with a job description.")
        st.stop()

    resume_text = st.session_state.resume_text

    st.subheader("🎯 Job Description Matcher")
    jd = st.text_area("Paste Job Description")

    if st.button("Analyze Job Fit") and jd:
        resume_words = set(resume_text.lower().split())
        jd_words = set(jd.lower().split())

        matched = resume_words & jd_words
        missing = jd_words - resume_words

        score = int((len(matched) / max(1, len(jd_words))) * 100)

        st.metric("Role Fit Score", f"{score}%")

        st.success("Matched Keywords")
        st.write(", ".join(list(matched)[:50]))

        st.warning("Missing Keywords")
        st.write(", ".join(list(missing)[:50]))

        st.markdown("### 🤖 AI JD-Specific Resume Improvements")
        with st.spinner("Generating suggestions..."):
            prompt = f"""
            Improve this resume for the following job description.

            RESUME:
            {resume_text}

            JOB DESCRIPTION:
            {jd}
            """
            st.write(ask_ai(prompt))
