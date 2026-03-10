"""
main.py — CareerScope AI v2 · FastAPI Backend
"""

import io
import os
import re
import uuid
import json
from pathlib import Path

import pdfplumber
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

app = FastAPI(title="CareerScope AI")

_sessions: dict[str, dict] = {}

BASE_DIR = Path(__file__).parent.resolve()


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

def calculate_ats_breakdown(text: str) -> dict:
    t = text.lower()

    # Contact
    has_email = bool(re.search(r"\S+@\S+\.\S+", text))
    has_phone = bool(re.search(r"\+?\d[\d\s\-]{8,}", text))
    has_linkedin = "linkedin" in t
    contact_score = int(((has_email + has_phone + has_linkedin) / 3) * 100)

    # Keywords density
    keyword_sections = sum([
        "skills" in t, "experience" in t, "education" in t,
        "summary" in t or "objective" in t or "profile" in t,
        "projects" in t or "achievements" in t or "accomplishments" in t,
    ])
    keywords_score = int((keyword_sections / 5) * 100)

    # Quantified achievements
    numbers = re.findall(r"\b\d+[%xX]?\b", text)
    quant_score = min(100, len(numbers) * 10)

    # Structure
    sections = sum([
        "education" in t, "experience" in t or "work" in t,
        "skills" in t, "summary" in t or "profile" in t or "objective" in t,
        "projects" in t or "certifications" in t or "achievements" in t,
    ])
    structure_score = int((sections / 5) * 100)

    # Action verbs
    action_verbs = [
        "led", "built", "designed", "developed", "managed", "delivered",
        "improved", "increased", "reduced", "launched", "created", "implemented",
        "optimized", "architected", "spearheaded", "drove", "achieved", "automated",
    ]
    verb_count = sum(1 for v in action_verbs if v in t)
    verbs_score = min(100, verb_count * 12)

    overall = int((contact_score + keywords_score + quant_score + structure_score + verbs_score) / 5)

    return {
        "overall": overall,
        "contact": contact_score,
        "keywords": keywords_score,
        "quantified": quant_score,
        "structure": structure_score,
        "action_verbs": verbs_score,
    }


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

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def root():
    for candidate in [
        BASE_DIR / "templates" / "index.html",
        Path("/opt/render/project/src/templates/index.html"),
    ]:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    raise HTTPException(status_code=500, detail=f"Template not found. BASE_DIR={BASE_DIR}")


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
        raise HTTPException(status_code=422, detail="PDF appears to be empty or image-only.")
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
    ats = calculate_ats_breakdown(text)
    return {
        "ats_score":         ats["overall"],
        "ats_breakdown":     ats,
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

    prompt = f"""You are an expert resume coach. Analyze this resume against the job description.

Return ONLY valid JSON, no markdown, no explanation, exactly this structure:
{{
  "improvements": [
    {{"priority": 1, "title": "...", "action": "..."}},
    {{"priority": 2, "title": "...", "action": "..."}},
    {{"priority": 3, "title": "...", "action": "..."}}
  ],
  "skill_gaps": [
    {{"skill": "...", "level": "missing|partial|strong", "gap": "critical|moderate|none", "course": "..."}},
    ...
  ],
  "bullet_rewrites": [
    {{"original": "...", "rewritten": "...", "reason": "..."}},
    {{"original": "...", "rewritten": "...", "reason": "..."}},
    {{"original": "...", "rewritten": "...", "reason": "..."}}
  ],
  "candidacy": {{
    "rating": "Strong|Moderate|Weak",
    "justification": "..."
  }}
}}

Extract real bullet points from the resume for bullet_rewrites.
For skill_gaps, list 6-8 skills the JD requires.
Keep all text concise and actionable.

RESUME:
{text[:3000]}

JOB DESCRIPTION:
{jd[:2000]}"""

    raw = ask_ai(prompt)

    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```[a-z]*\n?", "", clean)
            clean = re.sub(r"\n?```$", "", clean)
        result = json.loads(clean)
        return result
    except Exception:
        return {"raw": raw, "parse_error": True}


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
One unconventional suggestion that could significantly accelerate their career.

Be candid, strategic, and specific. Avoid generic platitudes.

---
RESUME:
{text[:4000]}
"""
    return {"analysis": ask_ai(prompt)}


@app.get("/api/linkedin/{sid}")
async def linkedin_headline(sid: str):
    if sid not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    from ai_client import ask_ai
    text = _sessions[sid]["text"]
    prompt = f"""You are a LinkedIn personal branding expert.

Based on this resume, generate 3 LinkedIn headline options.

Return ONLY valid JSON, no markdown:
{{
  "headlines": [
    {{"headline": "...", "style": "Achievement-focused", "why": "..."}},
    {{"headline": "...", "style": "Role + Value prop", "why": "..."}},
    {{"headline": "...", "style": "Bold/Unconventional", "why": "..."}}
  ]
}}

Each headline must be under 220 characters, punchy, and keyword-rich.

RESUME:
{text[:2000]}"""

    raw = ask_ai(prompt)
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```[a-z]*\n?", "", clean)
            clean = re.sub(r"\n?```$", "", clean)
        return json.loads(clean)
    except Exception:
        return {"raw": raw, "parse_error": True}


@app.get("/api/extract-resume/{sid}")
async def extract_resume(sid: str):
    """
    Extract structured data from uploaded resume text using AI.
    Returns JSON matching the resume builder data model.
    """
    if sid not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    from ai_client import ask_ai
    text = _sessions[sid]["text"]

    prompt = f"""You are a resume parser. Extract ALL information from this resume into structured JSON.

Return ONLY valid JSON, no markdown, exactly this structure:
{{
  "personal": {{
    "name": "full name",
    "title": "current job title or headline",
    "email": "email address",
    "phone": "phone number",
    "location": "city, state/country",
    "linkedin": "linkedin url or username",
    "portfolio": "github or portfolio url",
    "website": "personal website if any"
  }},
  "summary": "professional summary or objective paragraph",
  "experience": [
    {{
      "role": "job title",
      "company": "company name",
      "location": "city",
      "start": "Mon YYYY",
      "end": "Mon YYYY or Present",
      "bullets": ["bullet 1", "bullet 2", "bullet 3"]
    }}
  ],
  "education": [
    {{
      "institution": "university name",
      "degree": "degree type e.g. B.Tech",
      "field": "field of study",
      "year": "graduation year",
      "gpa": "GPA if mentioned"
    }}
  ],
  "skills": {{
    "tech": "comma-separated technical skills",
    "soft": "comma-separated soft skills and leadership skills",
    "tools": "comma-separated tools and platforms"
  }},
  "projects": [
    {{
      "name": "project name",
      "url": "project url if any",
      "tech": "tech stack",
      "bullets": ["highlight 1", "highlight 2"]
    }}
  ],
  "certifications": [
    {{
      "name": "certification name",
      "issuer": "issuing organization",
      "year": "year"
    }}
  ]
}}

Rules:
- Extract ALL positions from experience, not just the most recent
- Extract ALL education entries
- Extract ALL projects mentioned
- Keep bullet points as-is from the resume
- If a field is not found, use empty string "" or empty array []
- For skills: separate technical (programming, frameworks, protocols) from soft (leadership, communication) from tools (software, platforms)
- Dates should be formatted as "Mon YYYY" e.g. "Jan 2022"

RESUME TEXT:
{text[:5000]}"""

    raw = ask_ai(prompt)
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```[a-z]*\n?", "", clean)
            clean = re.sub(r"\n?```$", "", clean)
        return json.loads(clean)
    except Exception:
        return {"parse_error": True, "raw": raw[:500]}


@app.post("/api/ai-resume-assist")
async def ai_resume_assist(payload: dict):
    """
    Generic AI assist for resume builder.
    payload = { action, context, section_type, extra }
    actions: suggest_bullets | improve_text | generate_section | tailor_resume
    """
    from ai_client import ask_ai

    action       = payload.get("action", "")
    context      = payload.get("context", "")
    section_type = payload.get("section_type", "")
    extra        = payload.get("extra", "")

    if action == "suggest_bullets":
        prompt = f"""You are an expert resume writer.
Generate exactly 3 strong, quantified resume bullet points for:
Role: {context}
Company/Context: {extra}

Return ONLY valid JSON, no markdown:
{{"bullets": ["bullet 1", "bullet 2", "bullet 3"]}}

Rules:
- Start each with a strong action verb
- Include metrics/numbers where plausible (%, $, time saved, team size)
- Keep each under 20 words
- Be specific and impactful"""

    elif action == "improve_text":
        prompt = f"""You are an expert resume writer.
Improve this resume text for section: {section_type}

Original: {context}

Return ONLY valid JSON, no markdown:
{{"improved": "your improved version here", "reason": "brief explanation"}}

Rules:
- Make it more impactful, specific, and ATS-friendly
- Use strong action verbs
- Add quantification if possible
- Keep similar length"""

    elif action == "generate_section":
        prompt = f"""You are an expert resume writer.
Generate a complete {section_type} section for a resume.

Context provided by user: {context}
Additional info: {extra}

Return ONLY valid JSON, no markdown:
{{"content": "generated section content here"}}

Rules:
- Make it professional and ATS-optimized
- Be specific to the context given
- For summary: 3-4 impactful sentences
- For skills: comma-separated grouped by category"""

    elif action == "tailor_resume":
        prompt = f"""You are an expert resume coach.
Rewrite this resume summary/content to better match this job description.

Current Resume Content:
{context}

Job Description:
{extra}

Return ONLY valid JSON, no markdown:
{{"tailored": "rewritten content here", "keywords_added": ["kw1", "kw2", "kw3"]}}

Rules:
- Naturally incorporate JD keywords
- Maintain authenticity - don't add skills they don't have
- Make it more targeted and relevant"""

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

    raw = ask_ai(prompt)
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```[a-z]*\n?", "", clean)
            clean = re.sub(r"\n?```$", "", clean)
        return json.loads(clean)
    except Exception:
        return {"raw": raw, "parse_error": True}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)