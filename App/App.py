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

def calculate_resume_score(resume_text: str):
    if not resume_text:
        return 0, ["No resume text found."]

    text = resume_text.lower()
    score = 0
    feedback = []

    sections = {
        "summary": (["summary", "objective", "profile"], 10),
        "education": (["education", "degree", "university"], 15),
        "experience": (["experience", "work experience"], 20),
        "skills": (["skills", "technical skills"], 15),
        "projects": (["project", "projects"], 15),
        "certifications": (["certification", "certifications"], 10),
        "achievements": (["achievement", "achievements"], 10),
        "internships": (["internship", "internships"], 5),
    }

    for name, (keys, points) in sections.items():
        if any(k in text for k in keys):
            score += points
        else:
            feedback.append(f"Consider adding a {name} section.")

    return min(score, 100), feedback

# ================= FEATURE 3: DOMAIN DETECTION =================

def detect_domain(skills, resume_text):
    text = (resume_text or "").lower()
    skills = [s.lower() for s in skills]

    domains = {
        "Data Science": (
            ["python", "ml", "ai", "tensorflow", "pytorch", "data analysis"],
            ds_course
        ),
        "Web Development": (
            ["react", "django", "flask", "javascript", "html", "css"],
            web_course
        ),
        "Android Development": (
            ["android", "kotlin", "flutter", "java"],
            android_course
        ),
        "iOS Development": (
            ["ios", "swift", "xcode"],
            ios_course
        ),
        "UI/UX Design": (
            ["figma", "ux", "ui", "wireframe", "prototype"],
            uiux_course
        ),
        "Embedded Systems": (
            ["embedded", "microcontroller", "arm", "avr", "rtos", "firmware", "c", "c++"],
            []
        ),
        "Telecommunications": (
            ["telecom", "lte", "5g", "4g", "rf", "wireless", "networking", "protocol"],
            []
        ),
    }

    for domain, (keywords, courses) in domains.items():
        if any(k in skills or k in text for k in keywords):
            return domain, courses

    return "General / Undetermined", []

# =============================================================

# ---------- UI ----------

st.title("AI-Powered Resume Analyzer")

choice = st.sidebar.selectbox("Choose section", ["User", "About"])

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

        try:
            resume_text = extract_text_from_pdf(save_path)
        except Exception:
            resume_text = ""

        st.session_state["resume_text"] = resume_text

        # ---------- Basic parsing ----------
        email = re.search(r"\S+@\S+\.\S+", resume_text or "")
        phone = re.search(r"\+?\d[\d\s\-]{8,}", resume_text or "")

        skills = []
        keywords = [
            "python","java","c++","c","react","django","flask","sql","aws",
            "ml","ai","tensorflow","pytorch","docker","kubernetes",
            "javascript","html","css","flutter","kotlin","swift",
            "embedded","rtos","microcontroller","arm","lte","5g","rf"
        ]

        for kw in keywords:
            if kw in (resume_text or "").lower():
                skills.append(kw)

        pages = resume_text.count("\f") + 1 if resume_text else 1

        # ---------- Display ----------
        st.header("Resume Analysis")
        st.write("**Email:**", email.group(0) if email else "")
        st.write("**Phone:**", phone.group(0) if phone else "")
        st.write("**Pages:**", pages)

        # Experience level
        level = detect_experience_level(resume_text, pages)
        st.subheader("🧭 Experience Level")
        st.info(level)

        # Resume score
        st.subheader("📊 Resume Score")
        score, feedback = calculate_resume_score(resume_text)
        st.progress(score / 100)
        st.metric("Score", f"{score}/100")
        for f in feedback:
            st.write("•", f)

        # Domain detection
        domain, domain_courses = detect_domain(skills, resume_text)
        st.subheader("🎯 Best-fit Domain")
        st.success(domain)

        # Skills
        st.subheader("Detected Skills")
        st_tags(label="Skills", value=skills, key="skills")

        # Courses
        if domain_courses:
            course_recommender(domain_courses)
        else:
            st.info("No predefined courses for this domain yet.")

        # AI Suggestions
        st.markdown("---")
        st.subheader("🤖 AI Resume Suggestions")

        if st.button("Get AI Suggestions"):
            with st.spinner("Analyzing with Gemini…"):
                prompt = (
                    "Analyze this resume and provide strengths, gaps, "
                    "ATS keyword suggestions, and improvement tips:\n\n"
                    f"{resume_text}"
                )
                st.write(ask_ai(prompt))

        # Videos
        st.subheader("🎥 Resume Tips")
        st.video(random.choice(resume_videos))

        st.subheader("🎥 Interview Tips")
        st.video(random.choice(interview_videos))

# ================= ABOUT =================

else:
    st.markdown("""
    ### About AI Resume Analyzer

    - Detects **Experience Level**
    - Calculates **Resume Score**
    - Identifies **Best-fit Domain**
    - Supports **Data Science, Web, Mobile, UI/UX, Embedded & Telecom**
    - AI-powered suggestions using **Google Gemini**

    Built with ❤️ using Streamlit.
    """)
