import streamlit as st
import os
import io
import re
import time
import random
import base64
from PIL import Image
import pdfplumber

from streamlit_tags import st_tags
from Courses import (
    ds_course, web_course, android_course,
    ios_course, uiux_course,
    resume_videos, interview_videos
)

# ================== PAGE CONFIG ==================
st.set_page_config(
    page_title="CareerScope AI",
    page_icon="🧭",
    layout="wide"
)

# ================== AI CLIENT ==================
try:
    from ai_client import ask_ai
except Exception:
    def ask_ai(prompt):
        return "AI client not configured."

# ================== HELPERS ==================

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
        f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="900"></iframe>',
        unsafe_allow_html=True
    )

def course_recommender(course_list):
    st.subheader("📚 Recommended Learning")
    k = st.slider("Number of recommendations", 1, 8, 4)
    random.shuffle(course_list)
    for i, (name, link) in enumerate(course_list[:k], 1):
        st.markdown(f"{i}. [{name}]({link})")

# ================== SCORING LOGIC ==================

def resume_strength_breakdown(text: str, skills: list):
    breakdown = []

    sections = {
        "Experience": ["experience", "work history", "employment"],
        "Projects": ["project"],
        "Skills": ["skills", "technical skills"],
        "Education": ["education", "degree", "university"],
        "Certifications": ["certification", "certified", "pmp", "capm"],
        "Summary": ["summary", "profile", "objective"]
    }

    structure_score = 0
    max_structure = len(sections) * 10

    for section, keywords in sections.items():
        if any(k in text.lower() for k in keywords):
            breakdown.append(f"✅ {section} section found")
            structure_score += 10
        else:
            breakdown.append(f"❌ {section} section missing or weak")

    # Expertise score
    expertise_score = min(len(skills) * 4, 40)

    return breakdown, structure_score, expertise_score, max_structure

def detect_experience_level(text):
    text = text.lower()
    if "intern" in text:
        return "Intermediate"
    if any(k in text for k in ["lead", "manager", "architect", "owner"]):
        return "Senior"
    if any(k in text for k in ["experience", "worked", "responsible"]):
        return "Experienced"
    return "Fresher"

# ================== UI ==================

st.title("🧭 CareerScope AI")
st.caption("AI-powered career intelligence for modern professionals")

choice = st.sidebar.selectbox(
    "Navigate",
    ["Resume Analyzer", "About"]
)

# ================== MAIN APP ==================

if choice == "Resume Analyzer":

    st.subheader("📄 Upload your resume (PDF)")
    pdf_file = st.file_uploader("Upload PDF", type=["pdf"])

    if pdf_file:
        os.makedirs("Uploaded_Resumes", exist_ok=True)
        path = f"Uploaded_Resumes/{pdf_file.name}"

        with open(path, "wb") as f:
            f.write(pdf_file.getbuffer())

        st.markdown("### Resume Preview")
        show_pdf(path)

        # ---------- Extract text ----------
        resume_text = extract_text_from_pdf(path)
        st.session_state["resume_text"] = resume_text

        # ---------- Parse Resume ----------
        skills = []
        try:
            from pyresparser import ResumeParser
            parsed = ResumeParser(path).get_extracted_data()
            if parsed and parsed.get("skills"):
                skills = parsed["skills"]
        except Exception:
            pass

        if not skills:
            keywords = [
                "python","c","c++","embedded","rtos","linux",
                "lte","5g","ran","telecom","aws","cloud",
                "docker","kubernetes","devops","ci/cd",
                "fintech","payments","sql","microservices"
            ]
            for kw in keywords:
                if kw in resume_text.lower():
                    skills.append(kw)

        # ---------- EXPERIENCE ----------
        exp_level = detect_experience_level(resume_text)
        st.subheader("🧑‍💼 Experience Level")
        st.success(exp_level)

        # ---------- STRENGTH BREAKDOWN ----------
        st.subheader("🧠 Resume Strength Breakdown")

        breakdown, structure_score, expertise_score, max_structure = resume_strength_breakdown(
            resume_text, skills
        )

        for item in breakdown:
            st.write(item)

        # ---------- SCORES ----------
        structure_pct = int((structure_score / max_structure) * 100)
        expertise_pct = min(expertise_score, 100)

        overall_score = int((structure_pct * 0.6) + (expertise_pct * 0.4))

        col1, col2, col3 = st.columns(3)

        col1.metric("📐 Structure Score", f"{structure_pct}%")
        col2.metric("🛠 Expertise Score", f"{expertise_pct}%")
        col3.metric("⭐ Overall Resume Score", f"{overall_score}%")

        st.info(
            "Structure score reflects resume completeness. "
            "Expertise score reflects skill depth and relevance."
        )

        # ---------- SKILLS ----------
        st.subheader("🧩 Detected Skills")
        st_tags(label="Skills", value=skills, key="skills")

        # ---------- AI INSIGHTS ----------
        st.markdown("---")
        st.subheader("🤖 AI Career Insights")

        if st.button("Get AI Suggestions"):
            with st.spinner("Analyzing your profile…"):
                prompt = (
                    "You are an expert career coach.\n\n"
                    "Provide concise insights:\n"
                    "1. Strengths\n"
                    "2. Gaps\n"
                    "3. Improvement advice\n\n"
                    f"Resume:\n{resume_text}"
                )
                st.write(ask_ai(prompt))

        # ---------- VIDEOS ----------
        st.markdown("---")
        st.subheader("🎥 Career Tips")
        st.video(random.choice(resume_videos))
        st.video(random.choice(interview_videos))

# ================== ABOUT ==================

else:
    st.markdown("""
    ## About CareerScope AI

    CareerScope AI helps professionals understand **where they stand**,  
    **why a role fits**, and **how to improve** — not just parse resumes.

    ### What makes it different:
    - Dual scoring (Structure vs Expertise)
    - Explainable domain and role fit
    - AI-powered career insights
    - No databases, no tracking, privacy-first

    Built with ❤️ using Streamlit & Google Gemini.
    """)
