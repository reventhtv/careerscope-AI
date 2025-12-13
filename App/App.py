import streamlit as st
import os
import re
import random
import base64
import csv
import datetime
import pdfplumber
from PIL import Image

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

def render_pdf_preview_all_pages(path):
    """
    Streamlit-safe multi-page PDF preview.
    Renders each page as an image stacked vertically.
    """
    try:
        with pdfplumber.open(path) as pdf:
            st.subheader("📄 Resume Preview")
            for i, page in enumerate(pdf.pages, start=1):
                image = page.to_image(resolution=150).original
                st.image(
                    image,
                    caption=f"Page {i}",
                    use_column_width=True
                )
    except Exception:
        st.info("Preview not available. Please use the download option below.")

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

    if any(k in text for k in ["senior", "lead", "manager", "architect", "work experience"]):
        return "Experienced"
    if any(k in text for k in ["internship", "intern", "trainee"]):
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
        "summary": (["summary", "objective"], 10),
        "education": (["education", "degree"], 15),
        "experience": (["experience", "work experience"], 20),
        "skills": (["skills"], 15),
        "projects": (["project"], 15),
        "certifications": (["certification"], 10),
        "achievements": (["achievement"], 10),
        "internships": (["internship"], 5),
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
        "Data Science": (["python", "ml", "ai", "tensorflow"], ds_course),
        "Web Development": (["react", "django", "javascript"], web_course),
        "Android Development": (["android", "kotlin", "flutter"], android_course),
        "iOS Development": (["ios", "swift"], ios_course),
        "UI/UX Design": (["figma", "ux", "ui"], uiux_course),
        "Embedded Systems": (["embedded", "microcontroller", "rtos", "firmware", "c"], []),
        "Telecommunications": (["telecom", "lte", "5g", "rf", "wireless"], []),
    }

    for domain, (keywords, courses) in domains.items():
        if any(k in skills or k in text for k in keywords):
            return domain, courses

    return "General / Undetermined", []

# ================= FEATURE 4: FEEDBACK (CSV) =================

FEEDBACK_FILE = "feedback.csv"

def save_feedback(name, rating, comment):
    file_exists = os.path.exists(FEEDBACK_FILE)
    with open(FEEDBACK_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "name", "rating", "comment"])
        writer.writerow([
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            name, rating, comment
        ])

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

        # ✅ MULTI-PAGE PREVIEW
        render_pdf_preview_all_pages(save_path)

        # Download button
        with open(save_path, "rb") as f:
            st.download_button(
                "⬇️ Download Resume (PDF)",
                f,
                file_name=pdf_file.name,
                mime="application/pdf"
            )

        try:
            resume_text = extract_text_from_pdf(save_path)
        except Exception:
            resume_text = ""

        st.session_state["resume_text"] = resume_text

        email = re.search(r"\S+@\S+\.\S+", resume_text or "")
        phone = re.search(r"\+?\d[\d\s\-]{8,}", resume_text or "")

        skills = []
        keywords = [
            "python","java","c","c++","react","django","flask","sql","aws",
            "ml","ai","tensorflow","docker","javascript","html","css",
            "flutter","kotlin","swift","embedded","rtos","lte","5g","rf"
        ]

        for kw in keywords:
            if kw in (resume_text or "").lower():
                skills.append(kw)

        pages = resume_text.count("\f") + 1 if resume_text else 1

        # ---------- Analysis ----------
        st.header("Resume Analysis")
        st.write("**Email:**", email.group(0) if email else "")
        st.write("**Phone:**", phone.group(0) if phone else "")
        st.write("**Pages:**", pages)

        st.subheader("🧭 Experience Level")
        st.info(detect_experience_level(resume_text, pages))

        st.subheader("📊 Resume Score")
        score, tips = calculate_resume_score(resume_text)
        st.progress(score / 100)
        st.metric("Score", f"{score}/100")
        for t in tips:
            st.write("•", t)

        domain, domain_courses = detect_domain(skills, resume_text)
        st.subheader("🎯 Best-fit Domain")
        st.success(domain)

        st.subheader("Detected Skills")
        st_tags(label="Skills", value=skills, key="skills")

        if domain_courses:
            course_recommender(domain_courses)

        st.markdown("---")
        st.subheader("🤖 AI Resume Suggestions")
        if st.button("Get AI Suggestions"):
            with st.spinner("Analyzing with Gemini…"):
                st.write(ask_ai(resume_text))

        st.subheader("🎥 Resume Tips")
        st.video(random.choice(resume_videos))

        st.subheader("🎥 Interview Tips")
        st.video(random.choice(interview_videos))

        st.markdown("---")
        st.subheader("⭐ Share your feedback")

        with st.form("feedback_form"):
            name = st.text_input("Your name (optional)")
            rating = st.slider("Rating", 1, 5, 4)
            comment = st.text_area("Comments")
            submitted = st.form_submit_button("Submit Feedback")
            if submitted:
                save_feedback(name, rating, comment)
                st.success("Thank you! Your feedback was saved 🙌")

# ================= ABOUT =================

else:
    st.markdown("""
    ### About AI Resume Analyzer

    - Multi-page resume preview (scrollable)
    - Experience level detection
    - Resume scoring
    - Domain classification (incl. Embedded & Telecom)
    - AI-powered suggestions
    - Feedback without databases

    Built with ❤️ using Streamlit.
    """)
