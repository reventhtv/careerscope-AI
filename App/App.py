import streamlit as st
import os
import re
import random
import csv
import datetime
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

# ================= Helpers =================

def extract_text_from_pdf(path):
    text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text.lower()

def render_pdf_preview_all_pages(path):
    st.subheader("📄 Resume Preview")
    try:
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                image = page.to_image(resolution=150).original
                st.image(image, caption=f"Page {i}", use_column_width=True)
    except Exception:
        st.info("Preview not available.")

# ================= Experience =================

def detect_experience_level(text, pages):
    if any(k in text for k in ["senior", "lead", "architect", "manager"]):
        return "Experienced"
    if any(k in text for k in ["internship", "intern", "trainee"]):
        return "Intermediate"
    if pages >= 2:
        return "Intermediate"
    return "Fresher"

# ================= Resume Score =================

def calculate_resume_score(text):
    score = 0
    feedback = []

    sections = {
        "Summary / Objective": (["summary", "objective"], 10),
        "Education": (["education"], 15),
        "Experience": (["experience", "work experience"], 20),
        "Skills": (["skills"], 15),
        "Projects": (["project"], 15),
        "Certifications": (["certification"], 10),
        "Achievements": (["achievement"], 10),
        "Internships": (["internship"], 5),
    }

    for name, (keys, pts) in sections.items():
        if any(k in text for k in keys):
            score += pts
        else:
            feedback.append(f"Add a {name} section.")

    return min(score, 100), feedback

# ================= Domain Detection + Confidence =================

def detect_domain_with_confidence(text, skills):
    scores = {
        "Embedded Systems": 0,
        "Telecommunications": 0,
        "Data Science": 0,
        "Web Development": 0,
    }

    domain_keywords = {
        "Embedded Systems": ["embedded", "firmware", "rtos", "microcontroller", "c", "c++", "iot"],
        "Telecommunications": ["telecom", "lte", "5g", "rf", "ran", "wireless", "protocol", "3gpp"],
        "Data Science": ["machine learning", "tensorflow", "pytorch", "data science"],
        "Web Development": ["react", "django", "javascript"]
    }

    for domain, keys in domain_keywords.items():
        for k in keys:
            if k in text or k in skills:
                scores[domain] += 3

    # Company boosts
    if "ericsson" in text:
        scores["Telecommunications"] += 6
    if "verisure" in text:
        scores["Embedded Systems"] += 5

    # Weak Python DS signal
    if "python" in skills:
        scores["Data Science"] += 1

    best_domain = max(scores, key=scores.get)
    total = sum(scores.values()) or 1
    confidence = int((scores[best_domain] / total) * 100)

    return best_domain, confidence

# ================= ATS GAP =================

ATS_KEYWORDS = {
    "Telecommunications": [
        "3gpp", "o-ran", "link budget", "ran", "mac layer",
        "physical layer", "call flow", "sctp", "protocol testing"
    ],
    "Embedded Systems": [
        "bare metal", "interrupts", "dma", "spi", "i2c",
        "uart", "low power", "memory management"
    ],
    "Program Management": [
        "risk management", "stakeholder management", "raids",
        "delivery milestones", "cross-functional", "program roadmap"
    ]
}

def ats_gap(domain, text):
    expected = ATS_KEYWORDS.get(domain, [])
    missing = [k for k in expected if k not in text]
    return missing

# ================= Management Qualification =================

def management_confidence(text):
    score = 0
    if "pmp" in text: score += 40
    if "capm" in text: score += 30
    if any(k in text for k in ["program manager", "project manager"]):
        score += 30
    return min(score, 100)

# ================= Feedback =================

FEEDBACK_FILE = "feedback.csv"

def save_feedback(name, rating, comment):
    exists = os.path.exists(FEEDBACK_FILE)
    with open(FEEDBACK_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(["timestamp", "name", "rating", "comment"])
        writer.writerow([datetime.datetime.now(), name, rating, comment])

# ================= UI =================

st.title("AI-Powered Resume Analyzer")
choice = st.sidebar.selectbox("Choose section", ["User", "About"])

if choice == "User":

    pdf = st.file_uploader("Upload your resume (PDF)", type=["pdf"])
    if pdf:
        os.makedirs("Uploaded_Resumes", exist_ok=True)
        path = f"Uploaded_Resumes/{pdf.name}"
        with open(path, "wb") as f:
            f.write(pdf.getbuffer())

        render_pdf_preview_all_pages(path)

        text = extract_text_from_pdf(path)
        pages = text.count("\f") + 1

        skills = [k for k in [
            "python","c","c++","rtos","lte","5g","rf","iot",
            "react","django","tensorflow","pmp","capm"
        ] if k in text]

        st.header("Resume Analysis")

        st.subheader("🧭 Experience Level")
        st.info(detect_experience_level(text, pages))

        st.subheader("📊 Resume Score")
        score, tips = calculate_resume_score(text)
        st.progress(score / 100)
        st.metric("Score", f"{score}/100")

        domain, confidence = detect_domain_with_confidence(text, skills)
        st.subheader("🎯 Primary Technical Domain")
        st.success(f"{domain} ({confidence}% confidence)")

        missing = ats_gap(domain, text)
        if missing:
            st.subheader("⚠️ ATS Keyword Gaps")
            for k in missing:
                st.write("•", k)

        pm_conf = management_confidence(text)
        if pm_conf > 0:
            st.subheader("📌 Program / Project Management Readiness")
            st.progress(pm_conf / 100)
            st.metric("PM Confidence", f"{pm_conf}%")

        st.subheader("🧠 Detected Skills")
        st_tags(label="Skills", value=skills, key="skills")

        st.markdown("---")
        st.subheader("🤖 AI Suggestions")
        if st.button("Get AI Suggestions"):
            st.write(ask_ai(text))

        st.subheader("⭐ Feedback")
        with st.form("feedback"):
            name = st.text_input("Name")
            rating = st.slider("Rating", 1, 5, 4)
            comment = st.text_area("Comment")
            if st.form_submit_button("Submit"):
                save_feedback(name, rating, comment)
                st.success("Thank you for your feedback!")

else:
    st.markdown("""
    ### AI Resume Analyzer (v1.7)

    - ATS gap analysis
    - Domain confidence scoring
    - PMP / CAPM readiness detection
    - Embedded & Telecom aware
    - Cloud-safe, no DB

    Built with ❤️ using Streamlit.
    """)
