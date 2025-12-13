import streamlit as st
import os
import re
import csv
import datetime
import pdfplumber
from streamlit_tags import st_tags

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
    for sec in [
        "summary", "education", "experience", "skills",
        "projects", "certification", "achievement", "internship"
    ]:
        if sec in text:
            score += 12
    return min(score, 100)

# ================= Domain Detection (v2.0) =================

def detect_domain_with_confidence(text):
    scores = {
        "Embedded Systems": 0,
        "Telecommunications": 0,
        "Cloud Engineering": 0,
        "DevOps / Platform": 0,
        "Cybersecurity": 0,
        "Data Science": 0,
        "Web Development": 0,
    }

    domain_keywords = {
        "Embedded Systems": (["embedded", "firmware", "rtos", "microcontroller", "c", "c++", "iot"], 3),
        "Telecommunications": (["telecom", "lte", "5g", "rf", "ran", "3gpp", "wireless"], 3),

        "Cloud Engineering": (
            ["terraform", "cloudformation", "vpc", "iam", "eks", "gke", "high availability", "multi-region"], 3
        ),
        "DevOps / Platform": (
            ["kubernetes", "helm", "ci/cd", "jenkins", "github actions", "sre", "prometheus"], 3
        ),
        "Cybersecurity": (
            ["siem", "soc", "ids", "ips", "pentest", "threat modeling", "iso 27001"], 3
        ),

        "Data Science": (["machine learning", "tensorflow", "pytorch"], 2),
        "Web Development": (["react", "django", "javascript"], 2),
    }

    weak_signals = {
        "Cloud Engineering": ["aws", "azure", "gcp"],
        "DevOps / Platform": ["docker", "linux"],
        "Cybersecurity": ["security", "compliance"]
    }

    for domain, (keys, weight) in domain_keywords.items():
        for k in keys:
            if k in text:
                scores[domain] += weight

    for domain, keys in weak_signals.items():
        for k in keys:
            if k in text:
                scores[domain] += 1

    # Company boosts
    if "ericsson" in text:
        scores["Telecommunications"] += 6
    if "verisure" in text:
        scores["Embedded Systems"] += 5

    best = max(scores, key=scores.get)
    total = sum(scores.values()) or 1
    confidence = int((scores[best] / total) * 100)

    return best, confidence

# ================= Management =================

def management_confidence(text):
    score = 0
    if "pmp" in text: score += 40
    if "capm" in text: score += 30
    if any(k in text for k in ["program manager", "project manager", "roadmap", "delivery"]):
        score += 30
    return min(score, 100)

# ================= ATS Gap =================

ATS_KEYWORDS = {
    "Telecommunications": ["3gpp", "o-ran", "link budget", "ran", "mac layer"],
    "Embedded Systems": ["bare metal", "interrupts", "dma", "spi", "i2c"],
    "Cloud Engineering": ["autoscaling", "load balancer", "disaster recovery", "cost optimization"],
    "DevOps / Platform": ["blue green deployment", "canary release", "infra as code"],
    "Cybersecurity": ["incident response", "risk assessment", "threat intelligence"],
}

def ats_gap(domain, text):
    return [k for k in ATS_KEYWORDS.get(domain, []) if k not in text]

# ================= Role Fit (v2.0) =================

def suggest_roles(domain, exp_level, pm_conf):
    roles = []

    role_map = {
        "Telecommunications": ["RAN Engineer", "Wireless Systems Engineer"],
        "Embedded Systems": ["Embedded Systems Engineer", "Firmware Engineer"],
        "Cloud Engineering": ["Cloud Engineer", "Site Reliability Engineer"],
        "DevOps / Platform": ["DevOps Engineer", "Platform Engineer"],
        "Cybersecurity": ["Security Engineer", "SOC Analyst"],
    }

    roles.extend(role_map.get(domain, []))

    if exp_level == "Experienced":
        roles = [f"Senior {r}" for r in roles]

    if pm_conf >= 60:
        roles.append(f"Technical Program Manager ({domain})")

    return list(dict.fromkeys(roles))

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

st.title("🎯 CareerScope AI")
st.caption("Career & Role Intelligence Platform")

choice = st.sidebar.selectbox("Navigate", ["Career Analysis", "About"])

if choice == "Career Analysis":

    pdf = st.file_uploader("Upload your resume (PDF)", type=["pdf"])

    if pdf:
        os.makedirs("Uploaded_Resumes", exist_ok=True)
        path = f"Uploaded_Resumes/{pdf.name}"
        with open(path, "wb") as f:
            f.write(pdf.getbuffer())

        render_pdf_preview_all_pages(path)

        text = extract_text_from_pdf(path)
        pages = text.count("\f") + 1

        st.header("Career Insights")

        exp = detect_experience_level(text, pages)
        st.subheader("🧭 Experience Level")
        st.info(exp)

        st.subheader("📊 Resume Strength Score")
        st.progress(calculate_resume_score(text) / 100)

        domain, conf = detect_domain_with_confidence(text)
        st.subheader("🎯 Primary Technical Domain")
        st.success(f"{domain} ({conf}% confidence)")

        missing = ats_gap(domain, text)
        if missing:
            st.subheader("⚠️ ATS Keyword Gaps")
            for k in missing:
                st.write("•", k)

        pm_conf = management_confidence(text)
        if pm_conf:
            st.subheader("📌 Management Readiness")
            st.progress(pm_conf / 100)
            st.metric("PM Confidence", f"{pm_conf}%")

        st.subheader("🎯 Best-fit Roles")
        for r in suggest_roles(domain, exp, pm_conf):
            st.write("•", r)

        st.markdown("---")
        st.subheader("🤖 AI Career Advisor")
        if st.button("Get AI Guidance"):
            st.write(ask_ai(text))

        st.subheader("⭐ Feedback")
        with st.form("feedback"):
            name = st.text_input("Name (optional)")
            rating = st.slider("Rating", 1, 5, 4)
            comment = st.text_area("Comment")
            if st.form_submit_button("Submit"):
                save_feedback(name, rating, comment)
                st.success("Thanks for helping improve CareerScope AI 🙌")

else:
    st.markdown("""
    ## CareerScope AI (v2.0)

    - Embedded, Telecom, Cloud, DevOps & Cyber domains
    - ATS gap analysis
    - Role-fit suggestions
    - PMP / CAPM readiness
    - Explainable confidence scores

    Built with ❤️ using Streamlit.
    """)

