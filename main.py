"""
main.py — CareerScope AI · FastAPI Backend
Serves the single-page frontend and all API endpoints.
Deploy on Render: uvicorn main:app --host 0.0.0.0 --port $PORT
"""

import io
import os
import re
import uuid
from pathlib import Path

import pdfplumber
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

app = FastAPI(title="CareerScope AI")

# ── In-memory session store ──────────────────────────────────
_sessions: dict[str, dict] = {}

BASE_DIR = Path(__file__).parent


# ── PDF helpers ──────────────────────────────────────────────

def extract_text_from_pdf_bytes(data: bytes) -> str:
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""
    except Exception as exc:
        raise ValueError(f"Could not parse PDF: {exc}") from exc
    return text.strip()


# ── Analysis helpers ─────────────────────────────────────────

def calculate_ats_score(text: str) -> int:
    checks = [
        bool(re.search(r"\S+@\S+\.\S+", text)),           # email
        bool(re.search(r"\+?\d[\d\s\-]{8,}", text)),       # phone
        "education" in text.lower(),
        "experience" in text.lower(),
        "skills" in text.lower(),
    ]
    return int(sum(checks) / len(checks) * 100)


def experience_level(text: str) -> str:
    years = re.findall(r"\b(\d+)\+?\s+years?\b", text.lower())
    max_yrs = max((int(y) for y in years), default=0)
    if max_yrs >= 8:
        return "Experienced"
    if max_yrs >= 3:
        return "Mid-level"
    return "Entry-level"


DOMAINS: dict[str, list[str]] = {
    "Telecommunications": ["lte", "5g", "ran", "telecom", "ericsson", "antenna", "rf", "gnb"],
    "Embedded Systems":   ["embedded", "firmware", "rtos", "cortex", "microcontroller", "fpga", "vhdl"],
    "DevOps / Platform":  ["docker", "kubernetes", "terraform", "cloud", "ci/cd", "devops", "helm", "ansible"],
    "Data Science":       ["machine learning", "tensorflow", "pytorch", "data science", "nlp", "pandas", "sklearn"],
    "Web Development":    ["react", "angular", "django", "nodejs", "javascript", "typescript", "flask", "vue"],
    "Mobile Development": ["android", "ios", "swift", "kotlin", "flutter", "react native"],
}


def detect_domain(text: str) -> tuple[str, int]:
    t = text.lower()
    scores = {domain: sum(1 for kw in kws if kw in t) for domain, kws in DOMAINS.items()}
    best = max(scores, key=scores.get)
    total = sum(scores.values())
    if total == 0:
        return "General / Other", 0
    return best, int(scores[best] / total * 100)


STOP_WORDS = {
    "the","and","for","are","was","with","you","that","have","this",
    "will","your","from","they","been","has","more","also","not","but",
    "our","all","can","any","one","its","who","use","their","into","each",
    "most","some","what","such","new","work","able","good","well","must",
    "may","had","been","over","than","just","other","about","should","would",
}


# ── Routes ───────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = BASE_DIR / "templates" / "index.html"
    return html_path.read_text(encoding="utf-8")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/upload")
async def upload_resume(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB).")
    try:
        text = extract_text_from_pdf_bytes(data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not text:
        raise HTTPException(status_code=422, detail="PDF appears to be empty or image-only. Please use a text-based PDF.")
    sid = str(uuid.uuid4())
    _sessions[sid] = {"text": text, "filename": file.filename}
    return {"session_id": sid, "filename": file.filename}


@app.get("/api/insights/{sid}")
async def get_insights(sid: str):
    if sid not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found — please re-upload your resume.")
    text = _sessions[sid]["text"]
    domain, confidence = detect_domain(text)
    email_m = re.search(r"\S+@\S+\.\S+", text)
    phone_m = re.search(r"\+?\d[\d\s\-]{8,}", text)
    return {
        "ats_score":         calculate_ats_score(text),
        "experience_level":  experience_level(text),
        "domain":            domain,
        "domain_confidence": confidence,
        "email":             email_m.group() if email_m else None,
        "phone":             (phone_m.group()[:20].strip() if phone_m else None),
        "text_length":       len(text),
    }


@app.post("/api/job-match/{sid}")
async def job_match(sid: str, jd: str = Form(...)):
    if sid not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    text = _sessions[sid]["text"]
    resume_words = {w for w in re.findall(r"\b[a-zA-Z]{3,}\b", text.lower()) if w not in STOP_WORDS}
    jd_words     = {w for w in re.findall(r"\b[a-zA-Z]{3,}\b", jd.lower())   if w not in STOP_WORDS}
    matched = sorted(resume_words & jd_words)
    missing = sorted(jd_words - resume_words)
    score   = min(100, int(len(matched) / max(1, len(jd_words)) * 100))
    return {
        "fit_score":        score,
        "matched_keywords": matched[:40],
        "missing_keywords": missing[:40],
    }


@app.post("/api/ai-suggest/{sid}")
async def ai_suggest(sid: str, jd: str = Form(...)):
    if sid not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    from ai_client import ask_ai
    text = _sessions[sid]["text"]
    prompt = f"""You are an expert resume coach and hiring strategist.

Analyze this resume against the job description and provide:

### 1. Top 3 Resume Improvements
Specific, actionable changes to tailor this resume for this exact role.

### 2. Skills Gap Analysis
Key skills, tools, or qualifications the JD requires that are missing or underrepresented in the resume.

### 3. Bullet Point Rewrites
Pick 2–3 existing resume bullet points and rewrite them to better align with the JD's language and priorities.

### 4. Candidacy Assessment
Rate the overall fit as **Strong**, **Moderate**, or **Weak**. Justify in 2 concise sentences.

Keep everything professional, specific, and immediately actionable.

---
RESUME:
{text[:3000]}

---
JOB DESCRIPTION:
{jd[:2000]}
"""
    return {"suggestion": ask_ai(prompt)}


@app.get("/api/ai-analyze/{sid}")
async def ai_analyze(sid: str):
    if sid not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    from ai_client import ask_ai
    text = _sessions[sid]["text"]
    prompt = f"""You are a senior career strategist and executive resume advisor.

Analyze this resume and provide a structured briefing:

### Overall Quality Score
Rate /10 with a single sentence justification.

### Top 3 Strengths
What this resume does well — be specific, not generic.

### Top 3 Improvement Areas
Prioritized weaknesses with concrete fixes for each.

### Career Trajectory
Where this person currently sits and two realistic next moves (6–18 months, 3–5 years).

### Ideal Roles & Target Companies
List 3–4 specific job titles and types of organizations that would be strong matches.

### One Bold Move
One unconventional suggestion — a certification, side project, pivot, or networking strategy — that could significantly accelerate their career.

Be candid, strategic, and specific. Avoid generic platitudes.

---
RESUME:
{text[:4000]}
"""
    return {"analysis": ask_ai(prompt)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)