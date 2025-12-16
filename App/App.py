import streamlit as st
import os
import io
import re
import random
import base64
import pdfplumber
from PIL import Image

# ---------- Page Config ----------
st.set_page_config(
    page_title="CareerScope AI",
    page_icon="🎯",
    layout="wide"
)

# ---------- AI Client ----------
try:
    from ai_client import ask_ai
except Exception:
    def ask_ai(prompt: str):
        return "AI service temporarily unavailable."

# ---------- Courses ----------
from Courses import (
    ds_course, web_course, android_course,
    ios_course, uiux_course,
    resume_videos, interview_videos
)

# ---------- Sidebar ----------
st.sidebar.title("Navigate")

section = st.sidebar.radio(
    "",
    ["Resume Overview", "Career Insights", "Growth & Guidance", "Job Match"]
)

st.sidebar.markdown("### Upload Resume (PDF)")
pdf_file = st.sidebar.file_uploader(
    "Drag and drop file here",
    type=["pdf"]
)

# ---------- Buy Me a Coffee (STABLE) ----------
st.sidebar.markdown("---")
st.sidebar.markdown(
    """
    <div style="text-align:center; margin-top:20px;">
        <p style="font-size:14px; color:#bbb;">
            Enjoying CareerScope AI?
        </p>
        <a href="https://www.buymeacoffee.com/revanththiruvallur"
           target="_blank"
           style="
             display:inline-block;
             padding:8px 16px;
             background-color:#ffdd00;
             color:#000;
             font-weight:600;
             border-radius:8px;
             text-decoration:none;
             font-size:14px;
           ">
           ☕ Buy me a coffee
        </a>
    </div>
    """,
    unsafe_allow_html=True
)

# ---------- Helpers ----------
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
                width="100%" height="900"
                style="border:none;"></iframe>
        """,
        unsafe_allow_html=True
    )

def keyword_score(text, keywords):
    return sum(1 for k in keywords if k in text.lower())

# ---------- Save & Parse Resume ----------
resume_text = ""
resume_data = {}

if pdf_file:
    os.makedirs("Uploaded_Resumes", exist_ok=True)
    file_path = f"Uploaded_Resumes/{pdf_file.name}"

    with open(file_path, "wb") as f:
        f.write(pdf_file.getbuffer())

    resume_text = extract_text_from_pdf(file_path)
    st.session_state["resume_text"] = resume_text

    try:
        from pyresparser import ResumeParser
        parsed = ResumeParser(file_path).get_extracted_data()
        if parsed:
            resume_data = parsed
    except Exception:
        resume_data = {}

    if not resume_data:
        email = re.search(r"\S+@\S+\.\S+", resume_text)
        phone = re.search(r"\+?\d[\d\s\-]{8,}", resume_text)
        resume_data = {
            "email": email.group(0) if email else "",
            "mobile_number": phone.group(0) if phone else "",
            "skills": [],
            "no_of_pages": resume_text.count("\f") + 1
        }

# ================= HEADER =================
st.markdown(
    """
    <h1>🎯 CareerScope AI</h1>
    <p style="color:#aaa;">
    Career & Role Intelligence Platform
    </p>
    """,
    unsafe_allow_html=True
)

# ================= Resume Overview =================
if section == "Resume Overview":

    if not pdf_file:
        st.info("Upload a resume to begin.")
    else:
        st.subheader("📄 Resume Preview")
        show_pdf(file_path)

        st.subheader("📊 Resume Structure Score (ATS Readiness)")
        structure_score = min(100, 40 + resume_text.lower().count("experience") * 5)
        st.progress(structure_score / 100)
        st.write(f"**Score:** {structure_score}%")

# ================= Career Insights =================
elif section == "Career Insights":

    if not resume_text:
        st.info("Upload a resume to see insights.")
    else:
        st.subheader("🧠 Experience Level")

        if resume_text.lower().count("year") >= 5:
            exp_level = "Experienced"
        elif resume_text.lower().count("intern") > 0:
            exp_level = "Intermediate"
        else:
            exp_level = "Fresher"

        st.success(exp_level)

        st.subheader("🎯 Primary Domain")

        domain_keywords = {
            "Telecommunications": ["5g", "ran", "lte", "telecom", "wireless"],
            "Embedded Systems": ["embedded", "rtos", "firmware", "cortex", "c"],
            "Cloud / DevOps": ["aws", "azure", "gcp", "docker", "kubernetes", "ci/cd"],
            "FinTech": ["payments", "banking", "fintech", "pci", "ledger"],
            "Program Management": ["pmp", "capm", "stakeholder", "roadmap", "delivery"]
        }

        domain_scores = {
            d: keyword_score(resume_text, k)
            for d, k in domain_keywords.items()
        }

        primary_domain = max(domain_scores, key=domain_scores.get)
        confidence = min(100, domain_scores[primary_domain] * 10)

        st.success(f"{primary_domain} ({confidence}% confidence)")

        st.subheader("🧠 Domain Expertise Score")
        expertise_score = min(100, domain_scores[primary_domain] * 10)
        st.progress(expertise_score / 100)
        st.write(f"**Expertise:** {expertise_score}%")

# ================= Growth & Guidance =================
elif section == "Growth & Guidance":

    if not resume_text:
        st.info("Upload a resume to continue.")
    else:
        st.subheader("📌 ATS Keyword Gaps")

        ats_keywords = ["aws", "docker", "kubernetes", "observability", "metrics"]
        missing = [k for k in ats_keywords if k not in resume_text.lower()]

        if missing:
            st.warning("Missing Keywords:")
            for k in missing:
                st.write(f"- {k}")
        else:
            st.success("Strong ATS alignment")

        st.subheader("🎥 Resume Tips")
        st.video(random.choice(resume_videos))

        st.subheader("🎥 Interview Tips")
        st.video(random.choice(interview_videos))

# ================= Job Match =================
elif section == "Job Match":

    if not resume_text:
        st.info("Upload a resume first.")
    else:
        st.subheader("🧩 Job Description Matcher")

        jd_text = st.text_area(
            "Paste Job Description",
            height=200
        )

        if st.button("Analyze Job Fit"):
            matched = keyword_score(resume_text, jd_text.split())
            fit_score = min(100, matched * 2)

            st.subheader("📊 Role Fit Score")
            st.progress(fit_score / 100)
            st.write(f"**Fit Score:** {fit_score}%")

            st.subheader("🤖 AI JD-Specific Resume Improvements")

            with st.spinner("Generating suggestions..."):
                prompt = f"""
                You are a senior career advisor.

                Resume:
                {resume_text}

                Job Description:
                {jd_text}

                Provide:
                1. What to improve
                2. Missing skills
                3. Bullet-level suggestions
                """

                ai_out = ask_ai(prompt)
                st.write(ai_out)
