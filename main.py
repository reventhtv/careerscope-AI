"""
main.py — CareerScope AI v2 · FastAPI Backend
UPDATED: Improved AI prompts for resume quality (22-word bullet limit,
         role-title preservation, ATS-safe output, skills formatting)
"""

import io
import os
import re
import uuid
import json
import time
import asyncio
import logging
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path

import pdfplumber
import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager

# ── Logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("careerscopeai")

# ── Analytics store ────────────────────────────────────────────
_analytics: dict = {
    "total_uploads":       0,
    "total_analyses":      0,
    "total_job_matches":   0,
    "total_ai_suggests":   0,
    "total_pdf_exports":   0,
    "total_linkedin":      0,
    "total_builder_fills": 0,
    "events":              [],
    "daily":               defaultdict(lambda: defaultdict(int)),
    "started_at":          datetime.now(timezone.utc).isoformat(),
}
_MAX_EVENTS = 500

def track(event: str, meta: dict | None = None):
    ts  = datetime.now(timezone.utc).isoformat()
    day = ts[:10]
    entry = {"event": event, "ts": ts, **(meta or {})}
    _analytics["events"].append(entry)
    if len(_analytics["events"]) > _MAX_EVENTS:
        _analytics["events"].pop(0)
    _analytics["daily"][day][event] += 1
    key_map = {
        "upload":         "total_uploads",
        "ai_analysis":    "total_analyses",
        "job_match":      "total_job_matches",
        "ai_suggest":     "total_ai_suggests",
        "pdf_export":     "total_pdf_exports",
        "linkedin":       "total_linkedin",
        "builder_fill":   "total_builder_fills",
    }
    if event in key_map:
        _analytics[key_map[event]] += 1
    log.info("EVENT | %s | %s", event, json.dumps(meta or {}))

# ── Keepalive ──────────────────────────────────────────────────
SELF_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

async def _keepalive_loop():
    await asyncio.sleep(30)
    while True:
        try:
            url = (SELF_URL.rstrip("/") + "/health") if SELF_URL else None
            if url:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.get(url)
                log.info("KEEPALIVE | pinged %s", url)
        except Exception as exc:
            log.warning("KEEPALIVE | failed: %s", exc)
        await asyncio.sleep(600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_keepalive_loop())
    log.info("STARTUP | CareerScope AI ready | keepalive=%s", bool(SELF_URL))
    yield
    task.cancel()

app = FastAPI(title="CareerScope AI", lifespan=lifespan)

_sessions: dict[str, dict] = {}
_active_session: list[str] = []

BASE_DIR = Path(__file__).parent.resolve()


def _clear_session(sid: str) -> None:
    _sessions.pop(sid, None)
    if sid in _active_session:
        _active_session.remove(sid)

def _extract_json(raw: str) -> dict | list:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text.strip())
        try:
            return json.loads(text.strip())
        except Exception:
            pass
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find('{')
    end   = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end+1])
        except Exception:
            pass
    start = text.find('[')
    end   = text.rfind(']')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end+1])
        except Exception:
            pass
    raise ValueError(f"No valid JSON found in response: {text[:200]}")


# ── PDF helpers ────────────────────────────────────────────────

def extract_text_from_pdf_bytes(data: bytes) -> str:
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                width = page.width
                try:
                    left_crop  = page.crop((0,          0, width * 0.30, page.height))
                    right_crop = page.crop((width * 0.30, 0, width,       page.height))
                    left_text  = left_crop.extract_text()  or ""
                    right_text = right_crop.extract_text() or ""
                    has_sections = any(s in right_text.upper()
                                       for s in ["EXPERIENCE", "EDUCATION", "SUMMARY"])
                    is_two_col = (len(right_text) > len(left_text) * 2.5) and has_sections
                    if is_two_col:
                        text += right_text + "\n" + left_text
                    else:
                        text += page_text
                except Exception:
                    text += page_text
    except Exception as exc:
        raise ValueError(f"Could not parse PDF: {exc}") from exc
    return text.strip()


# ── Analysis helpers ───────────────────────────────────────────

def calculate_ats_breakdown(text: str) -> dict:
    t = text.lower()
    has_email = bool(re.search(r"\S+@\S+\.\S+", text))
    has_phone = bool(re.search(r"\+?\d[\d\s\-]{8,}", text))
    has_linkedin = "linkedin" in t
    contact_score = int(((has_email + has_phone + has_linkedin) / 3) * 100)
    keyword_sections = sum([
        "skills" in t, "experience" in t, "education" in t,
        "summary" in t or "objective" in t or "profile" in t,
        "projects" in t or "achievements" in t or "accomplishments" in t,
    ])
    keywords_score = int((keyword_sections / 5) * 100)
    numbers = re.findall(r"\b\d+[%xX]?\b", text)
    quant_score = min(100, len(numbers) * 10)
    sections = sum([
        "education" in t, "experience" in t or "work" in t,
        "skills" in t, "summary" in t or "profile" in t or "objective" in t,
        "projects" in t or "certifications" in t or "achievements" in t,
    ])
    structure_score = int((sections / 5) * 100)
    action_verbs = [
        "led","built","designed","developed","managed","delivered",
        "improved","increased","reduced","launched","created","implemented",
        "optimized","architected","spearheaded","drove","achieved","automated",
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


# ── Routes ──────────────────────────────────────────────────────

@app.get("/health")
async def health():
    track("ping")
    from ai_client import ai_status
    return {
        "status": "ok",
        "ts": datetime.now(timezone.utc).isoformat(),
        "ai": ai_status(),
    }


@app.get("/ping")
async def ping():
    return {"pong": True}


@app.get("/api/analytics")
async def analytics_summary():
    daily_plain = {k: dict(v) for k, v in _analytics["daily"].items()}
    return {
        "started_at":          _analytics["started_at"],
        "total_uploads":       _analytics["total_uploads"],
        "total_analyses":      _analytics["total_analyses"],
        "total_job_matches":   _analytics["total_job_matches"],
        "total_ai_suggests":   _analytics["total_ai_suggests"],
        "total_pdf_exports":   _analytics["total_pdf_exports"],
        "total_linkedin":      _analytics["total_linkedin"],
        "total_builder_fills": _analytics["total_builder_fills"],
        "daily":               daily_plain,
        "recent_events":       _analytics["events"][-50:],
    }


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
async def upload_resume(
    file: UploadFile = File(...),
    prev_session_id: str = Form(default=""),
):
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

    if prev_session_id:
        _clear_session(prev_session_id)
    for old_sid in list(_active_session):
        _clear_session(old_sid)

    sid = str(uuid.uuid4())
    _sessions[sid] = {"text": text, "filename": file.filename}
    _active_session.append(sid)
    track("upload", {"filename": file.filename, "chars": len(text)})
    return {"session_id": sid, "filename": file.filename}


@app.delete("/api/session/{sid}")
async def delete_session(sid: str):
    _clear_session(sid)
    return {"deleted": sid}


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
    track("job_match", {"sid": sid, "score": score})
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
BULLET REWRITE RULES: Each rewritten bullet must be ≤22 words, start with an action verb, include a metric.

RESUME:
{text[:3000]}

JOB DESCRIPTION:
{jd[:2000]}"""

    raw = ask_ai(prompt)
    try:
        result = _extract_json(raw)
        track("ai_suggest", {"sid": sid})
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
    result = ask_ai(prompt)
    track("ai_analysis", {"sid": sid})
    return {"analysis": result}


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
        result = _extract_json(raw)
        track("linkedin", {"sid": sid})
        return result
    except Exception:
        return {"raw": raw, "parse_error": True}


@app.get("/api/extract-resume/{sid}")
async def extract_resume(sid: str):
    if sid not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found — please re-upload your resume.")

    text = _sessions[sid].get("text", "")
    if not text or len(text.strip()) < 50:
        raise HTTPException(status_code=400, detail="No resume text found in session.")

    try:
        from resume_parser import parse_resume
        data = parse_resume(text)
        track("builder_fill", {"sid": sid, "parser": "deterministic"})
        return data
    except Exception as exc:
        import traceback
        traceback.print_exc()
        track("builder_fill_fallback", {"sid": sid, "error": str(exc)[:100]})

    try:
        from ai_client import ask_ai
        prompt = (
            "Extract resume information into valid JSON only — no markdown, no explanation.\n"
            "Structure:\n"
            "{\n"
            '  "personal": {"name":"","title":"","email":"","phone":"","location":"","linkedin":"","portfolio":"","website":""},\n'
            '  "summary": "2 sentences, max 60 words",\n'
            '  "experience": [{"role":"","company":"","location":"","start":"Mon YYYY","end":"Mon YYYY or Present","bullets":["bullet 1"]}],\n'
            '  "education": [{"institution":"","degree":"","field":"","year":"","gpa":""}],\n'
            '  "skills": {"tech":"comma-separated","soft":"comma-separated","tools":"comma-separated"},\n'
            '  "projects": [],\n'
            '  "certifications": [{"name":"","issuer":"","year":""}]\n'
            "}\n\n"
            "CRITICAL: preserve the candidate's name EXACTLY as written — do not reformat, abbreviate, or change capitalisation.\n"
            f"RESUME TEXT:\n{text[:5000]}"
        )
        raw = ask_ai(prompt)
        data = _extract_json(raw)
        return data
    except Exception:
        return {"parse_error": True, "message": "Could not parse resume — please fill in manually."}


@app.post("/api/ai-resume-assist")
async def ai_resume_assist(payload: dict):
    """
    AI assistant for the Resume Builder.
    IMPROVED PROMPTS:
    - Enforce ≤22 word bullet limit
    - Never include role title inside bullets
    - Preserve name exactly (no reformatting)
    - Clean ATS-safe output (no emoji, no broken parens)
    """
    from ai_client import ask_ai

    action       = payload.get("action", "")
    context      = payload.get("context", "")
    section_type = payload.get("section_type", "")
    extra        = payload.get("extra", "")

    if not action:
        raise HTTPException(status_code=400, detail="action is required")

    # ── improve_text ──────────────────────────────────────────────
    if action == "improve_text":
        if section_type == "summary":
            prompt = f"""You are an expert resume writer. Rewrite this professional summary as exactly 4-5 sharp bullet points.

Original text:
{context}

STRICT RULES:
- Output ONLY bullet lines, one per line, each starting with •
- Each bullet = one distinct credential, domain expertise, or achievement
- Each bullet MUST be ≤22 words — cut ruthlessly, keep only the strongest words
- Start with a bold keyword or credential (e.g. "PMP/CAPM certified", "8+ years", "Proven in")
- NO paragraph prose
- NO generic filler: "responsible for", "worked on", "helped with", "passionate about"
- DO NOT invent facts — only use information present in the original text
- Exactly 4 or 5 bullets, never more

Return ONLY the bullet lines starting with •, nothing else."""
        else:
            prompt = f"""You are an expert resume writer. Rewrite the following {section_type or 'resume'} text to be more impactful.

Original:
{context}

RULES:
- More results-focused and concise (same length or shorter)
- Professional and ATS-friendly (no emoji, no symbols except • for bullets)
- Each bullet ≤22 words if bullet format
- Start bullets with strong past-tense action verbs
- Remove passive voice

Return ONLY the improved text, no explanation, no quotes."""
        result = ask_ai(prompt)
        return {"improved": result.strip()}

    # ── generate_section ─────────────────────────────────────────
    if action == "generate_section":
        if section_type == "summary":
            prompt = f"""Write a professional resume summary as exactly 4 bullet points for this person:
{context}

Key skills / domain: {extra or 'not specified'}

STRICT RULES:
- Output ONLY 4 bullet lines, one per line, each starting with •
- Bullet 1: Title + certification + years of experience (the hook) — ≤20 words
- Bullet 2: Core technical domain and depth — ≤20 words
- Bullet 3: Program/project management strength or methodology — ≤20 words
- Bullet 4: A unique differentiator, GenAI capability, or key achievement — ≤20 words
- NO paragraph prose — bullets only
- NO generic phrases

Return ONLY the 4 bullet lines, nothing else."""
            result = ask_ai(prompt)
            return {"content": result.strip()}

        elif section_type == "skills":
            prompt = f"""Based on this professional profile, suggest 12-15 technical skills as a clean comma-separated list:
{context}

RULES:
- Return ONLY comma-separated skill names
- No descriptions, no bullets, no parentheses, no emoji
- ATS-safe: plain text only

Return ONLY the comma-separated list."""
            result = ask_ai(prompt)
            return {"content": result.strip()}

        elif section_type == "achievements":
            prompt = f"""Suggest 4-5 professional achievement bullets for this profile:
{context}

STRICT RULES:
- Each achievement MUST be ≤20 words
- Start with a strong action verb or result noun
- Include a specific metric where plausible
- No emoji, no parentheses artifacts, ATS-safe
- Return ONLY bullet lines starting with •"""
            result = ask_ai(prompt)
            return {"content": result.strip()}

        else:
            return {"content": "", "bullets": []}

    # ── suggest_bullets ──────────────────────────────────────────
    if action == "suggest_bullets":
        role    = payload.get("role", context)
        company = payload.get("company", "")
        prompt = f"""Write 5 strong resume bullet points for:
Role: {role}
Company: {company}
{('Additional context: ' + extra) if extra else ''}

STRICT RULES — these are non-negotiable:
- Each bullet MUST be ≤22 words — count every word
- Start with a PAST-TENSE action verb (Led, Built, Designed, Implemented, Optimized, Delivered, etc.)
- Include a specific metric or outcome where plausible (%, time saved, team size, cost, revenue)
- ATS-safe: no emoji, no symbols except plain text
- Do NOT include the job title "{role}" or company name "{company}" inside any bullet text
- Do NOT start bullets with "•" or "-" — return clean text only, the caller adds the bullet

Return ONLY valid JSON: {{"bullets": ["bullet 1", "bullet 2", "bullet 3", "bullet 4", "bullet 5"]}}"""
        raw = ask_ai(prompt)
        try:
            d = _extract_json(raw)
            # Post-process: strip any bullet chars the AI added anyway
            bullets = [b.lstrip('•-* ').strip() for b in d.get("bullets", [])]
            return {"bullets": bullets}
        except Exception:
            return {"bullets": []}

    # ── tailor_resume ─────────────────────────────────────────────
    if action == "tailor_resume":
        if not extra:
            raise HTTPException(status_code=400, detail="extra (job description) is required for tailor_resume")

        is_summary = section_type == "summary" or context.strip().startswith("•")

        if is_summary:
            prompt = f"""You are an expert resume writer. Tailor this professional summary to match the job description below.

Current summary (bullet format):
{context}

Job Description:
{extra[:2000]}

STRICT RULES:
- Output ONLY bullet lines, one per line, each starting with •
- Keep the same factual content — DO NOT invent new experiences or credentials
- Naturally weave in 2-3 relevant keywords from the JD into the existing bullets
- Each bullet MUST be ≤22 words
- Exactly 4 or 5 bullets, never more
- No paragraph prose

Return ONLY valid JSON:
{{"tailored": "• bullet 1\\n• bullet 2\\n• bullet 3\\n• bullet 4", "keywords_added": ["keyword1", "keyword2"]}}"""
        else:
            prompt = f"""Tailor this resume {section_type or 'section'} to better match the job description.

Current text:
{context}

Job Description:
{extra[:2000]}

RULES:
- Keep the same factual content (don't invent new experiences)
- Naturally incorporate relevant keywords from the JD
- Each bullet ≤22 words if bullet format
- ATS-safe output (no emoji, no broken parentheses)

Return ONLY valid JSON:
{{"tailored": "the rewritten text here", "keywords_added": ["keyword1", "keyword2"]}}"""

        raw = ask_ai(prompt)
        try:
            d = _extract_json(raw)
            return {"tailored": d.get("tailored", context), "keywords_added": d.get("keywords_added", [])}
        except Exception:
            return {"tailored": context, "keywords_added": []}

    # ── generate_cover_letter ─────────────────────────────────────
    if action == "generate_cover_letter":
        result = ask_ai(context)  # context already contains the full structured prompt
        return {"content": result.strip()}

    raise HTTPException(status_code=400, detail=f"Unknown action: {action}")


@app.post("/api/fill-bullets")
async def fill_bullets(payload: dict):
    from ai_client import ask_ai

    role     = payload.get("role", "")
    company  = payload.get("company", "")
    start    = payload.get("start", "")
    end      = payload.get("end", "")
    existing = payload.get("existing_bullets", [])

    if not role:
        raise HTTPException(status_code=400, detail="role is required")

    if len(existing) >= 5:
        return {"bullets": existing[:5]}

    needed = 5 - len(existing)
    existing_text = "\n".join(f"- {b}" for b in existing) if existing else "None yet"

    prompt = f"""You are an expert resume writer.

Job: {role} at {company} ({start} – {end})

Existing bullets (already written — do NOT repeat or paraphrase these):
{existing_text}

Write exactly {needed} NEW, UNIQUE bullet point(s) for this role.

STRICT RULES:
- Each bullet MUST be ≤22 words — count every word
- Start with a strong PAST-TENSE action verb
- Be specific to the role/company context
- Include a metric or quantifiable result where plausible (%, time, team size)
- Do NOT include the job title "{role}" or company "{company}" inside bullet text
- Do NOT start bullets with "•" or "-" — return clean text only
- Do NOT duplicate any existing bullet above

Return ONLY valid JSON, no markdown:
{{"new_bullets": ["bullet 1", "bullet 2", ...]}}

Generate exactly {needed} bullet(s)."""

    raw = ask_ai(prompt)
    try:
        d = _extract_json(raw)
        new_b = [b.lstrip('•-* ').strip() for b in d.get("new_bullets", [])]
        combined = existing + new_b
        return {"bullets": combined[:5]}
    except Exception:
        return {"bullets": existing}


@app.post("/api/track-export/{sid}")
async def track_export(sid: str):
    track("pdf_export", {"sid": sid})
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)