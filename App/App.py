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

# ---------- Page config ----------
st.set_page_config(
    page_title="AI Resume Analyzer",
    page_icon="📄",
    layout="wide"
)

# ---------- AI client ----------
try:
    from ai_client import ask_ai
except Exception:
    def ask_ai(prompt):
        return "AI client not configured."

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
        f'<iframe src="data:application/pdf;base64,{b64}" '
        f'width="700" height="900"></iframe>',
        unsafe_allow_html=True
    )

def course_recommender(course_list):
    st.subheader("📚 Course Recommendations")
    k = st.slider("Number of recommendations", 1, 10, 5)
    random.shuffle(course_list)
    for i, (name, link) in enumerate(course_list[:k], 1):
        st.markdown(f"{i}. [{name}]({link})")

# ================= FEATURE 1: EXPERIENCE LEVEL =================

def detect_experience_level(resume_text: str, pages: int | None = None) -> str:
    if not resume_text:
        return "Unknown"

    text = resume_text.lower()

    experienced_keywords = [
        "work experience", "professional experience",
        "experience", "senior", "lead", "manager", "architect"
    ]

    intermediate_keywords = [
        "internship", "intern", "trainee", "apprentice"
    ]

    for kw in experienced_keywords:
        if kw in text:
            return "Experienced"

    for kw in intermediate_keywords:
        if kw in text:
            return "Intermediate"

    if pages and pages >= 2:
        return "Intermediate"

    return "Fresher"

# ================= FEATURE 2: RESUME SCORE =================

def calculate_resume_score(resume_text: str) -> tuple[int, list[str]]:
    """
    Simple heuristic-based resume scoring.
    Returns (score out of 100, feedback list)
    """
    if not resume_text:
        return 0, ["No resume text found."]

    text = resume_text.lower()
    score = 0
    feedback = []

    checks = {
        "summary": (["summary", "objective", "profile"], 10, "Add a professional summary."),
        "education": (["education", "university", "college", "degree"], 15, "Add education details."),
        "experience": (["experience", "work experience"], 20, "Add work experience section."),
        "skills": (["skills", "technical skills"], 15, "Add a skills section."),
        "projects": (["projects", "project"], 15, "Add project details."),
        "certifications": (["certification", "certifications"], 10, "Add certifications."),
        "achievements": (["achievement", "achievements"], 10, "Add achievements or awards."),
        "internships": (["internship", "internships"], 5, "Add internship experience."),
    }

    for _, (keywords, points, suggestion) in checks.items():
        if any(k in text for k in keywords):
            score += points
        else:
            feedback.append(suggestion)

    return min(score, 100), feedback

# =============================================================

# ---------- UI ----------

st.title("AI-Powered Resume Analyzer")

choice = st.sidebar.selectbox(
    "Choose section",
    ["User", "About"]
)

# ================= USER =================

if choice == "User":

    st.subheader("Upload your resume (PDF)")
    pdf_file = st.file_uploader("Upload PDF", type=["pdf"])

    if pdf_file:
        os.makedirs("Uploaded_Resumes", exist_ok=True)
        save_path = f"Uploaded_Resumes/{pdf_file.name}"

        with open(save_path, "wb") as f:
            f.write(pdf_file.getbuffer())

        show_pdf(save_path)

        # ---------- Extract text ----------
        try:
            resume_text = extract_text_from_pdf(save_path)
        except Exception:
            resume_text = ""

        # Store for AI section
        st.session_state["resume_text"] = resume_text
        globals()["resume_text"] = resume_text

        # ---------- Parse resume (safe) ----------
        resume_data = {}

        try:
            from pyresparser import ResumeParser
            parsed = ResumeParser(save_path).get_extracted_data()
            if parsed:
                resume_data = parsed
        except Exception:
            resume_data = {}

        # ---------- Fallback parsing ----------
        if not resume_data:
            email = re.search(r"\S+@\S+\.\S+", resume_text or "")
            phone = re.search(r"\+?\d[\d\s\-]{8,}", resume_text or "")

            skills = []
            keywords = [
                "python","java","c++","react","django","flask","sql","aws",
                "ml","ai","tensorflow","pytorch","docker","kubernetes",
                "javascript","html","css","flutter","kotlin","swift"
            ]
            for kw in keywords:
                if kw in (resume_text or "").lower():
                    skills.append(kw)

            resume_data = {
                "email": email.group(0) if email else "",
                "mobile_number": phone.group(0) if phone else "",
                "skills": skills,
                "no_of_pages": resume_text.count("\f") + 1 if resume_text else 1
            }

        # ---------- Display ----------
        st.header("Resume Analysis")

        st.write("**Email:**", resume_data.get("email", ""))
        st.write("**Phone:**", resume_data.get("mobile_number", ""))
        st.write("**Pages:**", resume_data.get("no_of_pages", 1))

        # ===== Experience Level =====
        experience_level = detect_experience_level(
            resume_text,
            pages=resume_data.get("no_of_pages", 1)
        )

        st.subheader("🧭 Experience Level")
        if experience_level == "Experienced":
            st.success("🟢 Experienced")
        elif experience_level == "Intermediate":
            st.info("🟡 Intermediate")
        else:
            st.warning("🔵 Fresher")

        # ===== Resume Score =====
        st.subheader("📊 Resume Score")

        score, score_feedback = calculate_resume_score(resume_text)

        st.progress(score / 100)
        st.metric(label="Resume Score", value=f"{score} / 100")

        if score_feedback:
            st.markdown("**Suggestions to improve your score:**")
            for item in score_feedback:
                st.write("•", item)

        # ===== Skills =====
        st.subheader("Detected Skills")
        st_tags(
            label="Skills",
            value=resume_data.get("skills", []),
            key="skills"
        )

        # ---------- Recommendations ----------
        skills_lower = [s.lower() for s in resume_data.get("skills", [])]

        if any(s in skills_lower for s in ["python","ml","ai","tensorflow"]):
            course_recommender(ds_course)
        elif any(s in skills_lower for s in ["react","django","javascript"]):
            course_recommender(web_course)
        elif any(s in skills_lower for s in ["android","kotlin","flutter"]):
            course_recommender(android_course)
        elif any(s in skills_lower for s in ["ios","swift"]):
            course_recommender(ios_course)
        elif any(s in skills_lower for s in ["figma","ux","ui"]):
            course_recommender(uiux_course)

        # ---------- AI Suggestions ----------
        st.markdown("---")
        st.subheader("🤖 AI Resume Suggestions")

        if st.button("Get AI Suggestions"):
            with st.spinner("Analyzing with Gemini…"):
                prompt = (
                    "You are a career coach.\n\n"
                    "Analyze the following resume and provide:\n"
                    "1. Strengths\n"
                    "2. Weaknesses\n"
                    "3. Missing ATS keywords\n"
                    "4. Improvement suggestions\n\n"
                    f"Resume:\n{resume_text}"
                )
                out = ask_ai(prompt)
                st.write(out)

        # ---------- Videos ----------
        st.subheader("🎥 Resume Tips")
        st.video(random.choice(resume_videos))

        st.subheader("🎥 Interview Tips")
        st.video(random.choice(interview_videos))

# ================= ABOUT =================

else:
    st.markdown("""
    ### About AI Resume Analyzer

    - Upload a resume
    - Detect experience level
    - Score resume quality
    - Get AI-powered feedback using **Google Gemini**
    - Designed for learning, demos & portfolios

    Built with ❤️ using Streamlit.
    """)
