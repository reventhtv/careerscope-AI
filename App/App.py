import streamlit as st
import os
import csv
import random
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
    page_title="CareerScope AI",
    page_icon="🎯",
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
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            img = page.to_image(resolution=150).original
            st.image(img, caption=f"Page {i}", use_column_width=True)

# ================= Experience =================

def detect_experience_level(text):
    if any(k in text for k in ["senior", "lead", "architect", "manager"]):
        return "Experienced"
    if any(k in text for k in ["internship", "intern", "trainee"]):
        return "Intermediate"
    return "Fresher"

# ================= Resume Structure Score =================

def calculate_structure_score(text):
    score = 0
    sections = [
        "summary", "education", "experience", "skills",
        "projects", "certification", "achievement", "internship"
    ]
    for sec in sections:
        if sec in text:
            score += 12
    return min(score, 100)

# ================= Domain Detection + Expertise =================

def detect_domain_and_expertise(text):
    scores = {
        "Telecommunications": 0,
        "Embedded Systems": 0,
        "Cloud Engineering": 0,
        "DevOps / Platform": 0,
        "Cybersecurity": 0,
        "Data Science": 0,
        "Web Development": 0,
    }

    strong = {
        "Telecommunications": ["5g", "lte", "ran", "3gpp", "rf"],
        "Embedded Systems": ["embedded", "firmware", "rtos", "microcontroller"],
        "Cloud Engineering": ["terraform", "cloudformation", "vpc", "iam", "eks"],
        "DevOps / Platform": ["kubernetes", "helm", "ci/cd", "jenkins"],
        "Cybersecurity": ["siem", "soc", "pentest", "iso 27001"],
        "Data Science": ["machine learning", "tensorflow"],
        "Web Development": ["react", "django", "javascript"]
    }

    weak = {
        "Cloud Engineering": ["aws", "azure", "gcp"],
        "DevOps / Platform": ["docker", "linux"],
        "Cybersecurity": ["security"]
    }

    matched = {d: [] for d in scores}

    for domain, keys in strong.items():
        for k in keys:
            if k in text:
                scores[domain] += 3
                matched[domain].append(k)

    for domain, keys in weak.items():
        for k in keys:
            if k in text:
                scores[domain] += 1
                matched[domain].append(k)

    company_boosts = []
    if "ericsson" in text:
        scores["Telecommunications"] += 6
        company_boosts.append("Ericsson → Telecommunications")
    if "verisure" in text:
        scores["Embedded Systems"] += 5
        company_boosts.append("Verisure → Embedded Systems")

    best = max(scores, key=scores.get)
    expertise_score = min(int((scores[best] / (sum(scores.values()) or 1)) * 100), 100)

    return best, expertise_score, scores, matched, company_boosts

# ================= Management =================

def management_confidence(text):
    score = 0
    if "pmp" in text: score += 40
    if "capm" in text: score += 30
    if "program manager" in text: score += 30
    return min(score, 100)

# ================= ATS =================

ATS_KEYWORDS = {
    "Telecommunications": ["o-ran", "link budget", "mac layer"],
    "Embedded Systems": ["bare metal", "interrupts", "spi"],
    "Cloud Engineering": ["autoscaling", "disaster recovery"],
    "DevOps / Platform": ["canary deployment", "infra as code"],
    "Cybersecurity": ["incident response", "risk assessment"]
}

def ats_gap(domain, text):
    return [k for k in ATS_KEYWORDS.get(domain, []) if k not in text]

# ================= Role Fit =================

def suggest_roles(domain, exp, pm):
    base = {
        "Telecommunications": ["RAN Engineer", "Wireless Systems Engineer"],
        "Embedded Systems": ["Embedded Systems Engineer"],
        "Cloud Engineering": ["Cloud Engineer", "SRE"],
        "DevOps / Platform": ["DevOps Engineer"],
        "Cybersecurity": ["Security Engineer"]
    }

    roles = base.get(domain, []).copy()

    if exp == "Experienced":
        roles = [f"Senior {r}" for r in roles]

    if pm >= 60:
        roles.append(f"Technical Program Manager ({domain})")

    return roles

# ================= UI =================

st.title("🎯 CareerScope AI")
st.caption("Career & Role Intelligence Platform")

page = st.sidebar.radio(
    "Navigate",
    ["Resume Overview", "Career Insights", "Growth & Guidance"]
)

pdf = st.sidebar.file_uploader("Upload Resume (PDF)", type=["pdf"])

if pdf:
    os.makedirs("Uploaded_Resumes", exist_ok=True)
    path = f"Uploaded_Resumes/{pdf.name}"
    with open(path, "wb") as f:
        f.write(pdf.getbuffer())

    text = extract_text_from_pdf(path)

    exp = detect_experience_level(text)
    structure_score = calculate_structure_score(text)
    domain, expertise_score, domain_scores, matched_keys, boosts = detect_domain_and_expertise(text)
    pm_conf = management_confidence(text)
    missing = ats_gap(domain, text)

    detected_skills = sorted({
        k for k in [
            "python","c","c++","aws","docker","kubernetes",
            "5g","lte","ran","rtos","terraform","linux"
        ] if k in text
    })

    # -------- PAGE 1 --------
    if page == "Resume Overview":
        render_pdf_preview_all_pages(path)

        st.subheader("🧠 Detected Skills")
        st_tags(label="Skills", value=detected_skills, key="skills")

        st.subheader("🧭 Experience Level")
        st.info(exp)

        st.subheader("📊 Resume Structure Score (ATS Readiness)")
        st.progress(structure_score / 100)
        st.metric("Score", f"{structure_score}%")

    # -------- PAGE 2 --------
    elif page == "Career Insights":
        st.subheader("🎯 Primary Technical Domain")
        st.success(f"{domain}")

        st.subheader("🧠 Domain Expertise Score")
        st.progress(expertise_score / 100)
        st.metric("Expertise", f"{expertise_score}%")

        with st.expander("🔍 Why this domain?"):
            st.write("**Detected Keywords:**", ", ".join(matched_keys[domain]) or "—")
            if boosts:
                st.write("**Company Signals:**")
                for b in boosts:
                    st.write("•", b)
            st.write("**Domain Score Comparison:**")
            for d, s in domain_scores.items():
                st.write(f"{d}: {s}")

        if missing:
            st.subheader("⚠️ ATS Keyword Gaps")
            for k in missing:
                st.write("•", k)

        if pm_conf:
            st.subheader("📌 Management Readiness")
            st.progress(pm_conf / 100)
            st.metric("PM Confidence", f"{pm_conf}%")

        st.subheader("🎯 Best-fit Roles")
        for r in suggest_roles(domain, exp, pm_conf):
            st.write("•", r)

    # -------- PAGE 3 --------
    else:
        st.subheader("📚 Course Recommendations")
        course_map = {
            "Telecommunications": ds_course,
            "Embedded Systems": android_course,
            "Cloud Engineering": web_course,
            "DevOps / Platform": web_course,
            "Cybersecurity": ds_course,
        }
        for i, (name, link) in enumerate(course_map.get(domain, [])[:5], 1):
            st.markdown(f"{i}. [{name}]({link})")

        st.subheader("🤖 AI Career Advisor")
        if st.button("Get AI Guidance"):
            st.write(ask_ai(text))

        st.subheader("🎥 Resume Tips")
        st.video(random.choice(resume_videos))

        st.subheader("🎥 Interview Tips")
        st.video(random.choice(interview_videos))

        st.subheader("⭐ Feedback")
        with st.form("feedback"):
            name = st.text_input("Name (optional)")
            rating = st.slider("Rating", 1, 5, 4)
            comment = st.text_area("Comment")
            if st.form_submit_button("Submit"):
                with open("feedback.csv", "a", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow(
                        [datetime.datetime.now(), name, rating, comment]
                    )
                st.success("Thanks for your feedback 🙌")

else:
    st.info("Upload a resume to get started.")
