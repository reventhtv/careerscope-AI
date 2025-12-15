import streamlit as st
import os
import io
import re
import base64
import random
import pdfplumber
from streamlit_tags import st_tags
from Courses import (
    ds_course, web_course, android_course,
    ios_course, uiux_course,
    resume_videos, interview_videos
)

# ---------------- Page Config ----------------
st.set_page_config(
    page_title="CareerScope AI",
    page_icon="🚀",
    layout="wide"
)

# ---------------- AI Client ----------------
try:
    from ai_client import ask_ai
except Exception:
    def ask_ai(prompt):
        return "AI is not configured."

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
        f"<iframe src='data:application/pdf;base64,{b64}' width='100%' height='800'></iframe>",
        unsafe_allow_html=True
    )

def normalize(text):
    return text.lower() if text else ""

# ---------------- UI ----------------
st.title("🚀 CareerScope AI")
st.caption("AI-powered career clarity beyond resume analysis")

page = st.sidebar.radio(
    "Navigate",
    ["Resume Analyzer", "Job Match", "About"]
)

# ======================================================
# ================ RESUME ANALYZER =====================
# ======================================================
if page == "Resume Analyzer":

    st.subheader("📄 Upload your resume (PDF)")
    pdf_file = st.file_uploader("Upload PDF", type=["pdf"])

    if pdf_file:
        os.makedirs("Uploaded_Resumes", exist_ok=True)
        path = f"Uploaded_Resumes/{pdf_file.name}"

        with open(path, "wb") as f:
            f.write(pdf_file.getbuffer())

        show_pdf(path)

        resume_text = extract_text_from_pdf(path)
        st.session_state["resume_text"] = resume_text

        text = normalize(resume_text)

        # ---------------- Experience Level ----------------
        if "manager" in text or "lead" in text or "architect" in text:
            experience = "Senior / Lead"
        elif "intern" in text:
            experience = "Intermediate"
        else:
            experience = "Early / Mid-level"

        st.markdown(f"### 🧠 Experience Level: **{experience}**")

        # ---------------- Domain Detection ----------------
        domains = {
            "Telecommunications": ["ran", "lte", "5g", "ericsson", "telecom"],
            "Embedded Systems": ["embedded", "rtos", "firmware", "microcontroller"],
            "Cloud & DevOps": ["aws", "azure", "gcp", "docker", "kubernetes", "terraform"],
            "Cybersecurity": ["security", "siem", "soc", "iso", "penetration"],
            "FinTech": ["payments", "banking", "fintech", "risk", "trading"],
            "Data Science": ["machine learning", "data science", "tensorflow"],
            "Program Management": ["pmp", "capm", "program manager", "scrum"]
        }

        domain_scores = {}
        for d, kws in domains.items():
            domain_scores[d] = sum(1 for k in kws if k in text)

        best_domain = max(domain_scores, key=domain_scores.get)
        st.markdown(f"### 🎯 Best-fit Primary Domain: **{best_domain}**")

        # ---------------- Resume Scores ----------------
        structure_score = min(50, len(re.findall(r"\n", resume_text)) * 2)
        expertise_score = min(50, sum(domain_scores.values()) * 5)
        total_score = structure_score + expertise_score

        st.subheader("📊 Resume Strength")
        st.progress(total_score / 100)
        st.write(f"**Structure:** {structure_score}/50")
        st.write(f"**Expertise:** {expertise_score}/50")
        st.write(f"**Overall Score:** {total_score}/100")

        # ---------------- Skills ----------------
        keywords = [
            "python","c","c++","java","cloud","aws","docker","kubernetes",
            "telecom","5g","iot","embedded","pmp","capm","devops"
        ]
        skills = [k for k in keywords if k in text]

        st.subheader("🛠 Detected Skills")
        st_tags(label="Skills", value=skills, key="skills")

# ======================================================
# ================= JOB MATCH ==========================
# ======================================================
elif page == "Job Match":

    st.subheader("📌 Paste Job Description")
    jd = st.text_area("Job Description", height=220)

    if st.button("Analyze Job Fit"):
        resume_text = st.session_state.get("resume_text", "")
        combined = normalize(resume_text + jd)

        # -------- Role Fit --------
        roles = {
            "Technical Program Manager": ["program", "stakeholder", "roadmap"],
            "RAN Engineer": ["ran", "lte", "5g"],
            "Embedded Lead": ["embedded", "firmware", "rtos"],
            "Cloud Engineer": ["aws", "docker", "kubernetes"],
            "DevOps Engineer": ["ci/cd", "terraform", "pipeline"]
        }

        role_scores = {r: sum(1 for k in ks if k in combined) for r, ks in roles.items()}
        best_roles = sorted(role_scores, key=role_scores.get, reverse=True)[:3]

        confidence = min(100, sum(role_scores.values()) * 10)

        st.success("### ✅ Job Fit Summary")
        st.write("**Recommended Roles:**")
        for r in best_roles:
            st.write(f"- {r}")
        st.write(f"**Confidence Score:** {confidence}%")

        # ---------------- Buy Me a Coffee ----------------
        st.markdown(
            """
            <div style="
                background-color:#f8f9fa;
                padding:18px;
                border-radius:12px;
                border:1px solid #ddd;
                text-align:center;
                margin-top:25px;
                margin-bottom:25px;">
                <h4>☕ Enjoying CareerScope AI?</h4>
                <p style="font-size:15px;">
                    If this tool helped you gain clarity on your role fit or career direction,
                    you can support the project with a coffee.
                </p>
                <a href="https://www.buymeacoffee.com/revanththiruvallur" target="_blank"
                   style="
                    display:inline-block;
                    padding:10px 20px;
                    background-color:#ffdd00;
                    color:#000;
                    font-weight:600;
                    border-radius:8px;
                    text-decoration:none;">
                    Buy me a coffee ☕
                </a>
            </div>
            """,
            unsafe_allow_html=True
        )

        # ---------------- AI Improvements ----------------
        st.subheader("🤖 AI JD-Specific Resume Improvements")
        if st.button("Get AI Improvement Suggestions"):
            with st.spinner("Generating AI insights..."):
                prompt = f"""
                You are a senior hiring manager.
                Compare this resume with the job description and suggest:
                - Missing skills
                - ATS gaps
                - Resume improvements

                RESUME:
                {resume_text}

                JOB DESCRIPTION:
                {jd}
                """
                st.write(ask_ai(prompt))

# ======================================================
# ================= ABOUT ==============================
# ======================================================
else:
    st.markdown("""
    ## About CareerScope AI

    **CareerScope AI** helps professionals understand:
    - Their strongest technical domain
    - Career trajectory & role fit
    - ATS gaps and confidence level
    - Job-specific improvement areas using AI

    Built for engineers, managers, and career switchers.

    🚀 Soft-launched as an indie product.
    """)
