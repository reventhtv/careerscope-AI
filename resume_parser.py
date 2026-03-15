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
    import unicodedata
    text = raw_text

    # Normalize Unicode: NFC first to combine composed forms
    text = unicodedata.normalize('NFC', text)

    # Fix known PDF font ligature encodings (Private Use Area + standard ligatures)
    PUA_MAP = {
        '\ue09d': 'ft', '\ue117': 'ft', '\ufb01': 'fi', '\ufb02': 'fl',
        '\ufb03': 'ffi', '\ufb04': 'ffl', '\ufb05': 'st', '\ufb06': 'st',
        '\ue004': 'Th', '\ue005': 'th', '\ue003': 'Th',
        '\u2019': "'", '\u2018': "'", '\u201c': '"', '\u201d': '"',
        '\u2013': '–', '\u2014': '—', '\u00a0': ' ',
    }
    for bad, good in PUA_MAP.items():
        text = text.replace(bad, good)

    # Strip remaining unmapped Private Use Area characters (U+E000–U+F8FF)
    # that pdfplumber can't decode — replace with empty string
    text = re.sub(r'[\ue000-\uf8ff]', '', text)

    # Strip the WHITE SQUARE □ (U+25A1) and REPLACEMENT CHAR which indicate
    # unreadable glyphs — remove rather than keep garbled output
    text = re.sub(r'[\u25a1\ufffd\ufffc]', '', text)

    text = re.sub(r'\bso\s*ware\b',  'software', text, flags=re.IGNORECASE)
    text = re.sub(r'\bSo\s*Ware\b',  'Software', text, flags=re.IGNORECASE)
    text = re.sub(r'\bAus\b(?=\s+\d{4})', 'Aug', text)   # "Aus 2022" → "Aug 2022"

    # ── 1b. Fix bullet-title concatenation ───────────────────────────────
    # Some PDF layouts concatenate a bullet continuation line directly with the
    # next job title, e.g: "test teams.Embedded Software Engineer / Scrum Master"
    # Detect: text ending in ".[Title Case Job Title]" and split onto a new line.
    title_split_re = re.compile(
        r'([a-z,])\.((?:[A-Z][a-zA-Z]+ ){1,5}'
        r'(?:Engineer|Manager|Developer|Master|Consultant|Analyst|Architect|Director|Lead|Specialist)\b)'
    )
    text = title_split_re.sub(r'\1.\n\2', text)

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
    BULLET_RE   = re.compile(r'^[•*\u2013\u2014\u25b8\-]\s+(.+)$')  # •, *, –, —, ▸, -

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
        '_sum_bullets':   [],
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
            is_bullet_start = bool(re.match(r'^[•*\u2013\u2014\u25b8\-]\s+', line))
            if is_bullet_start:
                # Start of a new bullet — strip the bullet char and store
                clean = re.sub(r'^[•*\u2013\u2014\u25b8\-]\s*', '', line).strip()
                result['_sum_bullets'].append(clean)
            elif result['_sum_bullets']:
                # Continuation line — append to last bullet
                result['_sum_bullets'][-1] += ' ' + line.strip()
            else:
                # Plain prose line (no bullet chars in the resume)
                result['_sum_bullets'].append(line.strip())
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
                    'domain':   '',
                    'start':    start,
                    'end':      end,
                    'bullets':  [],
                }
                pending_role = None
                continue

            # (d) Domain/subdomain tag line right after company, before any bullets
            #     e.g. "Test Automation Software · Machine Learning"
            if current_exp is not None and not current_exp['bullets']:
                # Capture as domain tag if it looks like tags (has · or short enough)
                if current_exp.get('domain') == '' and (
                    '·' in line or len(line.split()) <= 6
                ):
                    current_exp['domain'] = line.strip()
                continue   # skip from bullets regardless

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

        # Check for "Institution · YYYY–YYYY" or "Institution · YYYY" inline format
        inline_date_m = re.search(r'\s*[·|]\s*(\d{4})\s*[–\-]?\s*(\d{4})?\s*$', ln)
        if inline_date_m and not is_deg:
            yr2 = inline_date_m.group(2) or inline_date_m.group(1)
            clean_inst = ln[:inline_date_m.start()].strip()
            # If previous edu entry has no institution yet, retroactively assign
            if edu_entries and not edu_entries[-1].get('institution'):
                edu_entries[-1]['institution'] = clean_inst
                edu_entries[-1]['year'] = yr2
                if not edu_entries[-1].get('end'):
                    edu_entries[-1]['end'] = yr2
            else:
                # Otherwise set for next entry
                cur_inst = clean_inst
                cur_yr   = yr2
            continue

        if is_deg:
            deg_text, yr_val = ln, cur_yr
            gpa_inline = ''
            # Extract inline GPA
            gpa_m = re.search(r'\s*[·,]?\s*GPA\s*:?\s*([\d./]+)', ln, re.I)
            if gpa_m:
                gpa_inline = gpa_m.group(1)
                ln_trimmed = ln[:gpa_m.start()].strip()
            else:
                ln_trimmed = ln
            if yr and ln_trimmed.rstrip().endswith(yr.group()):
                yr_val   = yr.group()
                deg_text = ln_trimmed[:ln_trimmed.rfind(yr.group())].strip()
            elif yr:
                yr_val   = yr.group()
                deg_text = ln_trimmed
            parts = re.split(r'\s*[-–]\s*', deg_text, maxsplit=1)
            edu_entries.append({
                'institution':     cur_inst or '',
                'sub_institution': '',
                'degree':          parts[0].strip(),
                'field':           parts[1].strip() if len(parts) > 1 else '',
                'year':            yr_val,
                'gpa':             gpa_inline,
            })
            cur_yr = ''   # reset year after using
        elif yr and len(ln.strip()) <= 8:
            cur_yr = yr.group()    # standalone year line
        elif 'GPA' in ln.upper():
            g = re.search(r'GPA\s*:?\s*([\d.]+)', ln, re.I)
            if g and edu_entries:
                edu_entries[-1]['gpa'] = g.group(1)
        else:
            ln_lower = ln.lower()
            is_main_inst = (
                any(kw in ln_lower for kw in ['university', 'hogskola', 'teknisk'])
                and not any(sub in ln_lower for sub in ['jntu college', 'college of engineering'])
            )
            if (edu_entries
                    and not is_main_inst
                    and not yr
                    and not any(k in ln for k in DEGREE_KW)
                    and not edu_entries[-1].get('sub_institution')):
                edu_entries[-1]['sub_institution'] = ln
            else:
                cur_inst = ln
                cur_yr   = ''

    result['education'] = edu_entries

    # ── 7. Post-process: Skills ──────────────────────────────────────
    skill_blob = ' '.join(skill_lines)

    def _split_skill_items(chunk: str) -> list:
        """Split a skill category chunk on bullet separators and commas."""
        chunk = re.sub(r'\s+', ' ', chunk).strip()
        items = [i.strip() for i in re.split(r'\s*[•·]\s*', chunk) if i.strip()]
        flat = []
        for it in items:
            if ',' in it and len(it.split(',')) <= 12:
                flat.extend(p.strip() for p in it.split(',') if p.strip())
            else:
                flat.append(it)
        return flat

    # Locate each category by finding its label → colon start position
    SKILL_CATS = [
        # Technical Program/Project Management skills
        ('tech_pm',     re.compile(r'Technical\s+Prog(?:ram|ject)\s+Management\s*:', re.I)),
        ('delivery',    re.compile(r'Product\s*&?\s*Delivery\s+Leadership\s*:', re.I)),
        ('embedded',    re.compile(r'Embedded Systems[^:]*:', re.I)),
        ('domains',     re.compile(r'Domains\s*:', re.I)),
        ('programming', re.compile(r'Programming\s*&?\s*Tools?\s*:', re.I)),
        # Exported Classic PDF labels (when user re-uploads their own export)
        ('tech_export', re.compile(r'(?<![A-Za-z])Technical\s*:', re.I)),
        ('soft_export', re.compile(r'Leadership\s*[&]?\s*Delivery\s*:', re.I)),
        ('dom_export',  re.compile(r'Domains\s*:', re.I)),
        # Metrics & Business Impact
        ('metrics',     re.compile(r'Metrics\s*[&]?\s*Business\s+Impact\s*:', re.I)),
        # Cloud, DevOps & Automation (template label for programming skills)
        ('cloud_devops', re.compile(r'Cloud[,\s&]+DevOps[^:]*:', re.I)),
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

    prog_items   = cat_chunks.get('programming', []) + cat_chunks.get('tech_export', []) + cat_chunks.get('cloud_devops', [])
    emb_items    = cat_chunks.get('embedded', [])
    # soft = delivery/leadership + metrics (KPI, ROI) — both map to the soft skills field
    soft_items   = (cat_chunks.get('delivery', []) + cat_chunks.get('soft_export', [])
                    + cat_chunks.get('metrics', []))
    # tools/domains = domain expertise + tech_pm competencies
    domain_items = (cat_chunks.get('domains', []) + cat_chunks.get('dom_export', [])
                    + cat_chunks.get('tech_pm', []))

    # Deduplicated tech skills: programming tools + embedded
    # Exclude sub-category labels (contain ":") — these come from tech_pm bleeding
    seen, tech_out = set(), []
    for item in (prog_items + emb_items):
        k = item.lower().strip()
        if k and k not in seen and len(k) > 1 and ':' not in item:
            seen.add(k)
            tech_out.append(item.strip())

    metrics_items = cat_chunks.get('metrics', [])
    result['skills']['tech']    = ', '.join(tech_out[:20])
    result['skills']['soft']    = ', '.join(soft_items[:16])
    result['skills']['tools']   = ', '.join(domain_items[:20])
    result['skills'].pop('metrics', None)   # not used by frontend

    # Fallback: only if ALL structured patterns failed
    if not result['skills']['tech'] and not result['skills']['soft'] and skill_blob:
        # Split on bullets/commas; exclude category labels (contain ':') and long sentences
        raw_items = [
            i.strip() for i in re.split(r'[\u2022\u00b7,\n]', skill_blob)
            if 2 < len(i.strip()) < 35 and ':' not in i
        ]
        result['skills']['tech'] = ', '.join(raw_items[:15])

    # ── 8. Post-process: Summary — return as list of bullet strings ──────
    # The frontend stores rb.summary as string[], one item per bullet row.
    if result['_sum_bullets']:
        summary_list = [b.strip() for b in result['_sum_bullets'][:6] if b.strip()]
    elif result['summary']:
        # Fallback: plain prose — split on bullet chars or sentence boundaries
        raw = result['summary'].strip()
        parts = [p.strip() for p in re.split(r'[•\n]+', raw) if p.strip()]
        if len(parts) <= 1:
            parts = [s.strip() for s in re.split(r'(?<=[.!?])\s+', raw) if s.strip()]
        summary_list = parts[:6]
    else:
        summary_list = []

    result['summary'] = summary_list           # list of strings
    # Keep a plain-text version for certifications scan below
    summary_text = ' '.join(summary_list)
    del result['_sum_bullets']

    # ── 9. Post-process: Education — add start/end fields ─────────────────
    # The UI now uses start/end rather than a single year field.
    # For education, graduation year → end; start is typically empty unless both years present.
    for edu in result['education']:
        yr = edu.get('year', '')
        if yr and not edu.get('end'):
            edu['end']   = yr          # graduation year goes to end
        if 'start' not in edu:
            edu['start'] = ''
        # Deduplicate: if start == end (e.g. "2016–2016"), keep only end
        if edu.get('start') and edu.get('end') and edu['start'] == edu['end']:
            edu['start'] = ''

    # ── 10. Post-process: Experience bullets — no truncation ─────────────
    # Do NOT cap bullets here. User controls page density via the Spacing
    # control in the builder (Compact / Normal / Spacious).

    # ── 11. Post-process: Certifications — infer from summary if no section found ──
    if not result['certifications']:
        KNOWN_CERTS = {
            'PMP':   ('Project Management Professional', 'PMI Institute'),
            'PgMP':  ('Program Management Professional', 'PMI Institute'),
            'CAPM':  ('Certified Associate in Project Management', 'PMI Institute'),
            'CSM':   ('Certified Scrum Master', 'Scrum Alliance'),
            'CSPO':  ('Certified Scrum Product Owner', 'Scrum Alliance'),
            'CISSP': ('CISSP', 'ISC2'),
        }
        scan = result['personal'].get('title', '') + ' ' + summary_text
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