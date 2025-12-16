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
    score = 0
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
    scores = {}
    for domain, keywords in DOMAINS.items():
        scores[domain] = sum(1 for k in keywords if k in resume_text.lower())
    best = max(scores, key=scores.get)
    confidence = int((scores[best] / max(1, sum(scores.values()))) * 100)
    return best, confidence


# ===================== UI HEADER =====================

st.title("🎯 CareerScope AI")
st.caption("Career & Role Intelligence Platform")

# ===================== SIDEBAR =====================

page = st.sidebar.radio(
    "Navigate",
    ["Resume Overview", "Career Insights", "Growth & Guidance", "Job Match"]
)

st.sidebar.markdown("---")
pdf_file = st.sidebar.file_uploader("Upload Resume (PDF)", type=["pdf"])

resume_uploaded = False
resume_text = ""

if pdf_file:
    os.makedirs("Uploaded_Resumes", exist_ok=True)
    save_path = f"Uploaded_Resumes/{pdf_file.name}"
    with open(save_path, "wb") as f:
        f.write(pdf_file.getbuffer())
    resume_text = extract_text_from_pdf(save_path)
    resume_uploaded = True

# ===================== RESUME OVERVIEW =====================

if page == "Resume Overview":
    if resume_uploaded:
        st.subheader("📄 Resume Preview")
        show_pdf(save_path)
    else:
        st.info("Upload a resume to begin analysis.")

# ===================== CAREER INSIGHTS =====================

if page == "Career Insights":

    if not resume_uploaded:
        st.warning("Please upload a resume first.")
    else:
        st.subheader("📊 Career Insights")

        # ---------- ATS SCORE ----------
        ats_score, ats_checks = calculate_structure_score(resume_text)
        st.markdown("### 📈 Resume Structure Score (ATS Readiness)")
        st.progress(ats_score)
        st.metric("Score", f"{ats_score}%")

        # ---------- RESUME STRENGTH BREAKDOWN (FIXED) ----------
        st.markdown("### 🧩 Resume Strength Breakdown")

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Contact Information", "Present" if ats_checks["email"] and ats_checks["phone"] else "Missing")
            st.metric("Education Section", "Present" if ats_checks["education"] else "Missing")
        with col2:
            st.metric("Experience Section", "Present" if ats_checks["experience"] else "Missing")
            st.metric("Skills Section", "Present" if ats_checks["skills"] else "Missing")

        st.caption(
            "This breakdown explains *why* your ATS score is what it is. "
            "Missing sections directly reduce ATS compatibility."
        )

        # ---------- EXPERIENCE ----------
        st.markdown("### 🧭 Experience Level")
        st.info(experience_level(resume_text))

        # ---------- DOMAIN ----------
        domain, confidence = detect_domain(resume_text)
        st.markdown("### 🎯 Primary Technical Domain")
        st.success(f"{domain} ({confidence}% confidence)")

# ===================== GROWTH & GUIDANCE =====================

if page == "Growth & Guidance":
    if not resume_uploaded:
        st.warning("Upload a resume to get recommendations.")
    else:
        course_recommender(ds_course)
        st.subheader("🎥 Resume Tips")
        st.video(random.choice(resume_videos))
        st.subheader("🎥 Interview Tips")
        st.video(random.choice(interview_videos))

# ===================== JOB MATCH =====================

if page == "Job Match":
    if not resume_uploaded:
        st.warning("Upload a resume to match with a job description.")
    else:
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
