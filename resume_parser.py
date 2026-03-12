"""
Deterministic resume parser for CareerScope AI.
Handles the exact PDF encoding of this resume format — no AI, no hallucination.
Replace /api/extract-resume's AI call with parse_resume(text).
"""
import re


def parse_resume(raw_text: str) -> dict:
    """
    Parse raw pdfplumber-extracted text into structured resume data.

    Handles:
      - Font ligature encoding (\ue09d, \ue117 → 'ft')  e.g. 'soware' → 'software'
      - PDF typo "Aus 2022" → "Aug 2022"
      - Multi-line wrapped bullets (continuation detection)
      - Job title / domain-tag / continuation disambiguation
      - Emoji contact markers (📍 📧 📞 🔗)
      - Multi-page PDFs (pdfplumber page text joined with \n)
    """

    # ── 1. Pre-process: fix ligature encoding & known typos ──────────
    text = raw_text
    text = text.replace('\ue09d', 'ft').replace('\ue117', 'ft')
    text = re.sub(r'\bso\s*ware\b',  'software', text, flags=re.IGNORECASE)
    text = re.sub(r'\bSo\s*Ware\b',  'Software', text, flags=re.IGNORECASE)
    text = re.sub(r'\bAus\b(?=\s+\d{4})', 'Aug', text)   # "Aus 2022" → "Aug 2022"

    lines = [l.rstrip() for l in text.split('\n')]

    # ── 2. Regex constants ───────────────────────────────────────────
    SECTION_MAP = {
        'SUMMARY': 'summary',
        'PROFESSIONAL SUMMARY': 'summary',
        'OBJECTIVE': 'summary',
        'PROFESSIONAL EXPERIENCE': 'experience',
        'EXPERIENCE': 'experience',
        'WORK EXPERIENCE': 'experience',
        'EDUCATION': 'education',
        'SKILLS': 'skills',
        'CERTIFICATIONS': 'certifications',
        'PROJECTS': 'projects',
    }

    MONTH = (
        r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May'
        r'|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?'
        r'|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
    )
    DATE        = rf'(?:{MONTH}\s+\d{{4}}|\d{{4}}|Present)'
    COMPANY_RE  = re.compile(
        rf'^(.+?)\s+({DATE}\s*[–—\-]+\s*{DATE})\s*$', re.IGNORECASE
    )
    DATE_RANGE_RE = re.compile(
        rf'({DATE})\s*[–—\-]+\s*({DATE})', re.IGNORECASE
    )
    BULLET_RE   = re.compile(r'^[•*]\s+(.+)$')

    # ── 3. Job-title detector ────────────────────────────────────────
    def _is_job_title(line: str) -> bool:
        """
        True if line looks like a job title (not a bullet continuation).
        Uses structure: short, title-cased, no trailing sentence punctuation.
        """
        if not line or line[0].islower() or line[0] in '([':
            return False
        if line[-1] in '.,:;!?':          # sentence-ending → not a title
            return False
        words = line.split()
        if len(words) > 7:                # titles are short
            return False
        CONNECTORS = {'/', '&', '-', '–', 'and', 'of', 'in', 'at',
                      'for', 'the', 'a', 'an', 'to'}
        for w in words:
            w_clean = w.strip('/&-–()')
            if not w_clean or w_clean.lower() in CONNECTORS:
                continue
            if not w_clean[0].isupper():
                return False
        # Reject if clearly a sentence fragment (long clause with conjunctions)
        if len(words) > 5 and re.search(
            r'\b(the|a|an|is|was|are|were|has|have|had|and|but|or|with|for|to|in|on|at|from|by|of)\b',
            line, re.I
        ):
            return False
        return True

    # ── 4. State ─────────────────────────────────────────────────────
    result = {
        'personal': {
            'name': '', 'title': '', 'email': '', 'phone': '',
            'location': '', 'linkedin': '', 'portfolio': '', 'website': '',
        },
        'summary':        '',
        'experience':     [],
        'education':      [],
        'skills':         {'tech': '', 'soft': '', 'tools': ''},
        'projects':       [],
        'certifications': [],
    }

    section      = None
    current_exp  = None
    pending_role = None
    bullet_buf   = []    # accumulates one multi-line bullet
    edu_lines    = []
    skill_lines  = []
    header_n     = 0

    def _flush_bullet():
        nonlocal bullet_buf
        if bullet_buf and current_exp is not None:
            full = ' '.join(bullet_buf).strip()
            if full:
                current_exp['bullets'].append(full)
        bullet_buf = []

    def _flush_exp():
        nonlocal current_exp
        _flush_bullet()
        if current_exp and current_exp.get('role') and current_exp.get('company'):
            result['experience'].append(current_exp)
        current_exp = None
        # NOTE: do NOT clear pending_role here — company handler uses it after calling _flush_exp

    # ── 5. Main parse loop ───────────────────────────────────────────
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        upper = line.upper()

        # Section header?
        if upper in SECTION_MAP:
            _flush_exp()
            section  = SECTION_MAP[upper]
            header_n = 0
            continue

        # ── Personal header (before first section) ──────────────────
        if section is None:
            header_n += 1
            p = result['personal']
            if header_n == 1:
                p['name'] = line
            elif header_n == 2:
                p['title'] = line.split('|')[0].strip()
            else:
                em = re.search(r'📧\s*([^\s|📞📍🔗]+@[^\s|📞📍🔗]+)', line)
                ph = re.search(
                    r'📞\s*([\+\d\s\-\(\)]+?)(?:\s*\|\||\s*📧|\s*📍|\s*🔗|\s*$)', line)
                li = re.search(r'🔗\s*(https?://\S+|LinkedIn\S*)', line, re.I)
                lo = re.search(
                    r'📍\s*([^|📧📞🔗]+?)(?:\s*\|\||\s*📧|\s*📞|\s*🔗|\s*$)', line)
                if em: p['email']    = em.group(1).strip()
                if ph: p['phone']    = ph.group(1).strip()
                if li: p['linkedin'] = li.group(1).strip()
                if lo: p['location'] = lo.group(1).strip().rstrip('| ').strip()
            continue

        # ── SUMMARY ─────────────────────────────────────────────────
        if section == 'summary':
            clean = re.sub(r'^[•*]\s*', '', line)
            result['summary'] += (' ' if result['summary'] else '') + clean
            continue

        # ── EXPERIENCE ──────────────────────────────────────────────
        if section == 'experience':
            bm = BULLET_RE.match(line)
            cm = COMPANY_RE.match(line)

            # (a) New bullet line
            if bm:
                _flush_bullet()
                bullet_buf = [bm.group(1)]
                continue

            # (b) While inside a bullet, check before treating as continuation:
            #     if line looks like a job title → flush bullet and treat as title
            if bullet_buf and not cm:
                if _is_job_title(line):
                    # This is the next job title embedded at end of bullet wrap
                    _flush_bullet()
                    pending_role = line
                else:
                    # Genuine continuation of the current bullet
                    bullet_buf.append(line)
                continue

            # (c) Company line — saves current exp, starts a new one
            if cm:
                company_part = cm.group(1).strip()
                date_str     = cm.group(2).strip()
                dr = DATE_RANGE_RE.search(date_str)
                start = dr.group(1) if dr else ''
                end   = dr.group(2) if dr else ''

                co_m = re.match(r'^(.+?),\s*(.+)$', company_part)
                company  = co_m.group(1).strip() if co_m else company_part
                location = co_m.group(2).strip() if co_m else ''

                _flush_exp()
                current_exp = {
                    'role':     pending_role or '',
                    'company':  company,
                    'location': location,
                    'start':    start,
                    'end':      end,
                    'bullets':  [],
                }
                pending_role = None
                continue

            # (d) Domain/subdomain tag line right after company, before any bullets
            #     e.g. "Test Automation Software · Machine Learning"
            if current_exp is not None and not current_exp['bullets']:
                continue   # skip domain tag silently

            # (e) Job title line (bullet_buf is empty here)
            _flush_bullet()
            pending_role = line
            continue

        # ── EDUCATION ───────────────────────────────────────────────
        if section == 'education':
            edu_lines.append(line)
            continue

        # ── SKILLS ──────────────────────────────────────────────────
        if section == 'skills':
            skill_lines.append(line)
            continue

        # ── CERTIFICATIONS ──────────────────────────────────────────
        if section == 'certifications':
            parts = [p.strip() for p in re.split(r'\s*[·,]\s*', line)]
            if parts and parts[0]:
                result['certifications'].append({
                    'name':   parts[0],
                    'issuer': parts[1] if len(parts) > 1 else '',
                    'year':   parts[2] if len(parts) > 2 else '',
                })
            continue

    _flush_exp()   # final flush

    # ── 6. Post-process: Education ───────────────────────────────────
    DEGREE_KW = ('M.Sc', 'B.Tech', 'MBA', 'Ph.D', 'Bachelor', 'Master', 'B.E',
                 'M.E', 'B.S', 'M.S', 'BEng', 'MEng', 'Doctor', 'Associate',
                 'BE', 'ME', 'M.Tech', 'B.Eng', 'M.Eng', 'B.Com', 'M.Com')
    edu_entries, cur_inst, cur_yr = [], None, ''

    for ln in edu_lines:
        yr    = re.search(r'\b(20\d{2}|19\d{2})\b', ln)
        is_deg = any(k in ln for k in DEGREE_KW)

        if is_deg:
            deg_text, yr_val = ln, cur_yr
            if yr and ln.rstrip().endswith(yr.group()):
                yr_val   = yr.group()
                deg_text = ln[:ln.rfind(yr.group())].strip()
            elif yr:
                yr_val   = yr.group()
            parts = re.split(r'\s*[-–]\s*', deg_text, maxsplit=1)
            edu_entries.append({
                'institution': cur_inst or '',
                'degree':      parts[0].strip(),
                'field':       parts[1].strip() if len(parts) > 1 else '',
                'year':        yr_val,
                'gpa':         '',
            })
            cur_yr = ''   # reset year after using
        elif yr and len(ln.strip()) <= 8:
            cur_yr = yr.group()    # standalone year line
        elif 'GPA' in ln.upper():
            g = re.search(r'GPA\s*:?\s*([\d.]+)', ln, re.I)
            if g and edu_entries:
                edu_entries[-1]['gpa'] = g.group(1)
        else:
            cur_inst = ln    # institution line
            cur_yr   = ''    # reset year when we get new institution

    result['education'] = edu_entries

    # ── 7. Post-process: Skills ──────────────────────────────────────
    skill_blob = ' '.join(skill_lines)

    def _split_skill_items(chunk: str) -> list:
        """Split a skill category chunk on bullet separators and commas."""
        chunk = re.sub(r'\s+', ' ', chunk).strip()
        items = [i.strip() for i in re.split(r'\s*[•·]\s*', chunk) if i.strip()]
        flat = []
        for it in items:
            if ',' in it and len(it.split(',')) <= 6:
                flat.extend(p.strip() for p in it.split(',') if p.strip())
            else:
                flat.append(it)
        return flat

    # Locate each category by finding its label → colon start position
    SKILL_CATS = [
        ('tech_pm',     re.compile(r'Technical Project Management\s*:', re.I)),
        ('delivery',    re.compile(r'Product\s*&?\s*Delivery\s+Leadership\s*:', re.I)),
        ('embedded',    re.compile(r'Embedded Systems[^:]*:', re.I)),
        ('domains',     re.compile(r'Domains\s*:', re.I)),
        ('programming', re.compile(r'Programming\s*&?\s*Tools?\s*:', re.I)),
    ]
    cat_starts = []
    for key, pat in SKILL_CATS:
        m = pat.search(skill_blob)
        if m:
            cat_starts.append((m.end(), key))  # start after the colon
    cat_starts.sort(key=lambda x: x[0])

    cat_chunks: dict = {}
    for i, (start, key) in enumerate(cat_starts):
        end = cat_starts[i + 1][0] if i + 1 < len(cat_starts) else len(skill_blob)
        # Trim back to before the next category's label text
        chunk = skill_blob[start:end]
        # Remove the next label heading from the tail
        if i + 1 < len(cat_starts):
            next_key = cat_starts[i + 1][1]
            for _, npat in SKILL_CATS:
                nm = npat.search(chunk)
                if nm:
                    chunk = chunk[:nm.start()]
                    break
        cat_chunks[key] = _split_skill_items(chunk)

    prog_items   = cat_chunks.get('programming', [])
    emb_items    = cat_chunks.get('embedded', [])
    soft_items   = cat_chunks.get('delivery', [])
    domain_items = cat_chunks.get('domains', [])

    # Deduplicated tech skills: programming tools + embedded
    seen, tech_out = set(), []
    for item in (prog_items + emb_items):
        k = item.lower().strip()
        if k and k not in seen and len(k) > 1:
            seen.add(k)
            tech_out.append(item.strip())

    result['skills']['tech']  = ', '.join(tech_out[:20])
    result['skills']['soft']  = ', '.join(soft_items[:12])
    result['skills']['tools'] = ', '.join(domain_items[:8])

    # Fallback
    if not result['skills']['tech'] and skill_blob:
        result['skills']['tech'] = re.sub(r'\s+', ' ', skill_blob)[:300]

    # ── 8. Post-process: Summary — cap at 2 sentences ────────────────
    sents = re.split(r'(?<=[.!?])\s+', result['summary'].strip())
    result['summary'] = ' '.join(sents[:2]).strip()


    # ── 9. Post-process: Certifications — infer from summary if no section found ──
    if not result['certifications']:
        KNOWN_CERTS = {
            'PMP':   ('Project Management Professional', 'PMI Institute'),
            'PgMP':  ('Program Management Professional', 'PMI Institute'),
            'CAPM':  ('Certified Associate in Project Management', 'PMI Institute'),
            'CSM':   ('Certified Scrum Master', 'Scrum Alliance'),
            'CSPO':  ('Certified Scrum Product Owner', 'Scrum Alliance'),
            'CISSP': ('CISSP', 'ISC2'),
        }
        scan = result['personal'].get('title', '') + ' ' + result['summary']
        added = set()
        for abbr, (full_name, issuer) in KNOWN_CERTS.items():
            if re.search(rf'\b{abbr}\b', scan) and abbr not in added:
                added.add(abbr)
                result['certifications'].append({'name': full_name, 'issuer': issuer, 'year': ''})
        # Also scan raw_text directly for any we might have missed
        for abbr, (full_name, issuer) in KNOWN_CERTS.items():
            if abbr not in added and re.search(rf'\b{abbr}\b', raw_text):
                added.add(abbr)
                result['certifications'].append({'name': full_name, 'issuer': issuer, 'year': ''})

    return result