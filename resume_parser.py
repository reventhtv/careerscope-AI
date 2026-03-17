"""
Deterministic resume parser for CareerScope AI.
Handles the exact PDF encoding of this resume format — no AI, no hallucination.

FIXES applied (found by automated test suite):
  BUG-1: Contact emoji mismatch — parser scanned 📧/📞 but resume uses ✉/✆
  BUG-2: Education year on institution line (e.g. "BTH 2016") not extracted
  BUG-3: Skills mapping — tech_pm items landing in tech_out instead of domains;
          soft field empty when only delivery/leadership category present
  BUG-4: Education 'end' field not populated from year (missing from schema)
"""
import re


def parse_resume(raw_text: str) -> dict:
    """
    Parse raw pdfplumber-extracted text into structured resume data.
    """
    import unicodedata
    text = raw_text

    # ── 1. Pre-process ───────────────────────────────────────────────
    text = unicodedata.normalize('NFC', text)

    PUA_MAP = {
        '\ue09d': 'ft', '\ue117': 'ft', '\ufb01': 'fi', '\ufb02': 'fl',
        '\ufb03': 'ffi', '\ufb04': 'ffl', '\ufb05': 'st', '\ufb06': 'st',
        '\ue004': 'Th', '\ue005': 'th', '\ue003': 'Th',
        '\u2019': "'", '\u2018': "'", '\u201c': '"', '\u201d': '"',
        '\u2013': '–', '\u2014': '—', '\u00a0': ' ',
    }
    for bad, good in PUA_MAP.items():
        text = text.replace(bad, good)

    text = re.sub(r'[\ue000-\uf8ff]', '', text)
    text = re.sub(r'[\u25a1\ufffd\ufffc]', '', text)
    text = re.sub(r'\bso\s*ware\b',  'software', text, flags=re.IGNORECASE)
    text = re.sub(r'\bSo\s*Ware\b',  'Software', text, flags=re.IGNORECASE)
    text = re.sub(r'\bAus\b(?=\s+\d{4})', 'Aug', text)

    title_split_re = re.compile(
        r'([a-z,])\.((?:[A-Z][a-zA-Z]+ ){1,5}'
        r'(?:Engineer|Manager|Developer|Master|Consultant|Analyst|Architect|Director|Lead|Specialist)\b)'
    )
    text = title_split_re.sub(r'\1.\n\2', text)

    # ── 1c. Strip browser print header/footer ────────────────────────────────
    # When a user re-uploads a PDF exported via window.print() from their browser,
    # Chrome/Firefox injects:
    #   Header: "17/03/2026, 10:22  FULL NAME — Resume"  (date · time · page title)
    #   Footer: "blob:https://careerscopeai.in/xxxx  1/3"  (blob URL · page N/total)
    # Without stripping these, line 0 = timestamp string → parsed as person's name.
    # Fix: drop any line that matches a browser-injected header/footer pattern.
    _clean = []
    for _ln in text.split('\n'):
        _s = _ln.strip()
        # Browser timestamp header: DD/MM/YYYY, HH:MM  or  MM/DD/YYYY, HH:MM
        if re.match(r'^\d{1,2}/\d{1,2}/\d{4},?\s+\d{1,2}:\d{2}', _s):
            continue
        # Browser blob URL footer
        if _s.startswith('blob:https://') or _s.startswith('blob:http://'):
            continue
        _clean.append(_ln)
    text = '\n'.join(_clean)

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
    DATE          = rf'(?:{MONTH}\s+\d{{4}}|\d{{4}}|Present)'
    COMPANY_RE    = re.compile(
        rf'^(.+?)\s+({DATE}\s*[–—\-]+\s*{DATE})\s*$', re.IGNORECASE
    )
    DATE_RANGE_RE = re.compile(
        rf'({DATE})\s*[–—\-]+\s*({DATE})', re.IGNORECASE
    )
    BULLET_RE     = re.compile(r'^[•*\u2013\u2014\u25b8\-]\s+(.+)$')

    # ── 3. Job-title detector ────────────────────────────────────────
    def _is_job_title(line: str) -> bool:
        if not line or line[0].islower() or line[0] in '([':
            return False
        if line[-1] in '.,:;!?':
            return False
        words = line.split()
        if len(words) > 7:
            return False
        CONNECTORS = {'/', '&', '-', '–', 'and', 'of', 'in', 'at',
                      'for', 'the', 'a', 'an', 'to'}
        for w in words:
            w_clean = w.strip('/&-–()')
            if not w_clean or w_clean.lower() in CONNECTORS:
                continue
            if not w_clean[0].isupper():
                return False
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
    bullet_buf   = []
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

    # ── 5. Main parse loop ───────────────────────────────────────────
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        upper = line.upper()

        if upper in SECTION_MAP:
            _flush_exp()
            section  = SECTION_MAP[upper]
            header_n = 0
            continue

        # ── Personal header ──────────────────────────────────────────
        if section is None:
            header_n += 1
            p = result['personal']
            if header_n == 1:
                p['name'] = line
            elif header_n == 2:
                p['title'] = line.split('|')[0].strip()
            else:
                # ── BUG-1 FIX: support both 📧/📞 AND ✉/✆ emoji variants ──
                # Email: 📧 or ✉
                em = re.search(
                    r'(?:📧|✉)\s*([^\s|📞📍🔗✆✉📧]+@[^\s|📞📍🔗✆✉📧]+)', line)
                # Phone: 📞 or ✆
                ph = re.search(
                    r'(?:📞|✆)\s*([\+\d\s\-\(\)]+?)(?:\s*\|\||\s*📧|\s*✉|\s*📍|\s*🔗|\s*$)', line)
                # LinkedIn/portfolio: 🔗 (first = linkedin, second = portfolio)
                links = re.findall(r'🔗\s*([^\s|📞📍🔗✆✉📧\|]+)', line)
                # Location: 📍
                lo = re.search(
                    r'📍\s*([^|📧📞🔗✆✉]+?)(?:\s*\|\||\s*📧|\s*✉|\s*📞|\s*✆|\s*🔗|\s*$)', line)

                if em:    p['email']    = em.group(1).strip()
                if ph:    p['phone']    = ph.group(1).strip()
                if lo:    p['location'] = lo.group(1).strip().rstrip('| ').strip()
                if links:
                    # First link = linkedin (usually), second = github/portfolio
                    p['linkedin']  = links[0].strip() if len(links) > 0 else ''
                    p['portfolio'] = links[1].strip() if len(links) > 1 else ''
            continue

        # ── SUMMARY ──────────────────────────────────────────────────
        if section == 'summary':
            is_bullet_start = bool(re.match(r'^[•*\u2013\u2014\u25b8\-]\s+', line))
            if is_bullet_start:
                clean = re.sub(r'^[•*\u2013\u2014\u25b8\-]\s*', '', line).strip()
                result['_sum_bullets'].append(clean)
            elif result['_sum_bullets']:
                result['_sum_bullets'][-1] += ' ' + line.strip()
            else:
                result['_sum_bullets'].append(line.strip())
            continue

        # ── EXPERIENCE ───────────────────────────────────────────────
        if section == 'experience':
            bm = BULLET_RE.match(line)
            cm = COMPANY_RE.match(line)

            if bm:
                _flush_bullet()
                bullet_buf = [bm.group(1)]
                continue

            if bullet_buf and not cm:
                if _is_job_title(line):
                    _flush_bullet()
                    pending_role = line
                else:
                    bullet_buf.append(line)
                continue

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

            if current_exp is not None and not current_exp['bullets']:
                if current_exp.get('domain') == '' and (
                    '·' in line or len(line.split()) <= 6
                ):
                    current_exp['domain'] = line.strip()
                continue

            _flush_bullet()
            pending_role = line
            continue

        if section == 'education':
            edu_lines.append(line)
            continue

        if section == 'skills':
            skill_lines.append(line)
            continue

        if section == 'certifications':
            # Skip blob URL footer and bare page numbers injected by browser print
            if line.startswith('blob:') or re.match(r'^\d+/\d+$', line.strip()):
                continue
            # Strip any leading bullet character (•, *, -)
            clean_line = re.sub(r'^[•*\-]\s*', '', line).strip()
            if not clean_line:
                continue
            parts = [p.strip() for p in re.split(r'\s*[·,]\s*', clean_line)]
            if parts and parts[0]:
                result['certifications'].append({
                    'name':   parts[0],
                    'issuer': parts[1] if len(parts) > 1 else '',
                    'year':   parts[2] if len(parts) > 2 else '',
                })
            continue

    _flush_exp()

    # ── 6. Post-process: Education ───────────────────────────────────
    DEGREE_KW = ('M.Sc', 'B.Tech', 'MBA', 'Ph.D', 'Bachelor', 'Master', 'B.E',
                 'M.E', 'B.S', 'M.S', 'BEng', 'MEng', 'Doctor', 'Associate',
                 'BE', 'ME', 'M.Tech', 'B.Eng', 'M.Eng', 'B.Com', 'M.Com')
    edu_entries, cur_inst, cur_yr = [], None, ''

    for ln in edu_lines:
        yr     = re.search(r'\b(20\d{2}|19\d{2})\b', ln)
        is_deg = any(k in ln for k in DEGREE_KW)

        # Check for "Institution · YYYY–YYYY" inline format (dot/pipe before year)
        inline_date_m = re.search(r'\s*[·|]\s*(\d{4})\s*[–\-]?\s*(\d{4})?\s*$', ln)
        if inline_date_m and not is_deg:
            yr2       = inline_date_m.group(2) or inline_date_m.group(1)
            clean_inst = ln[:inline_date_m.start()].strip()
            if edu_entries and not edu_entries[-1].get('institution'):
                edu_entries[-1]['institution'] = clean_inst
                edu_entries[-1]['year']        = yr2
                edu_entries[-1]['end']         = yr2
            else:
                cur_inst = clean_inst
                cur_yr   = yr2
            continue

        # ── BUG-2 FIX: institution line with trailing year ────────────
        # e.g. "Blekinge Tekniska Hogskola, Karlskrona (Sweden) 2016"
        # Pattern: non-degree line that ends with a 4-digit year after a space
        if not is_deg and yr:
            line_without_year = ln[:yr.start()].rstrip()
            # It's an institution-year line if it's reasonably long (> 10 chars
            # before the year) and doesn't look like a standalone year
            if len(line_without_year) > 10:
                cur_inst = line_without_year
                cur_yr   = yr.group()
                continue
            elif len(ln.strip()) <= 8:
                # standalone year line
                cur_yr = yr.group()
                continue

        if is_deg:
            deg_text   = ln
            yr_val     = cur_yr
            gpa_inline = ''

            gpa_m = re.search(r'\s*[·,]?\s*GPA\s*:?\s*([\d./]+)', ln, re.I)
            if gpa_m:
                gpa_inline = gpa_m.group(1)
                ln_trimmed = ln[:gpa_m.start()].strip()
            else:
                ln_trimmed = ln

            # Year might be on same line as degree (less common)
            yr_inline = re.search(r'\b(20\d{2}|19\d{2})\b', ln_trimmed)
            if yr_inline and ln_trimmed.rstrip().endswith(yr_inline.group()):
                yr_val   = yr_inline.group()
                deg_text = ln_trimmed[:ln_trimmed.rfind(yr_inline.group())].strip()
            else:
                deg_text = ln_trimmed

            parts = re.split(r'\s*[-–]\s*', deg_text, maxsplit=1)
            edu_entries.append({
                'institution':     cur_inst or '',
                'sub_institution': '',
                'degree':          parts[0].strip(),
                'field':           parts[1].strip() if len(parts) > 1 else '',
                'year':            yr_val,
                'gpa':             gpa_inline,
                'start':           '',
                'end':             yr_val,   # BUG-4 FIX: always set end = year
            })
            cur_yr = ''

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
        chunk = re.sub(r'\s+', ' ', chunk).strip()
        items = [i.strip() for i in re.split(r'\s*[•·]\s*', chunk) if i.strip()]
        flat  = []
        for it in items:
            if ',' in it and len(it.split(',')) <= 12:
                flat.extend(p.strip() for p in it.split(',') if p.strip())
            else:
                flat.append(it)
        return flat

    SKILL_CATS = [
        # Primary labels — order matters: most specific first, no overlapping match zones
        ('tech_pm',      re.compile(r'Technical\s+Prog(?:ram|ject)\s+Management\s*:', re.I)),
        ('delivery',     re.compile(r'Product\s*&?\s*Delivery\s+Leadership\s*:', re.I)),
        ('domains',      re.compile(r'Domains\s*:', re.I)),
        # Alternative labels (other resume formats only — not present in Reventh format)
        ('programming',  re.compile(r'Programming\s*&?\s*Tools?\s*:', re.I)),
        ('metrics',      re.compile(r'Metrics\s*[&]?\s*Business\s+Impact\s*:', re.I)),
        ('cloud_devops', re.compile(r'Cloud[,\s&]+DevOps[^:]*:', re.I)),
        # REMOVED — caused chunk-stealing bugs:
        # 'embedded'   matched "Embedded Systems" TEXT inside tech_pm items → shadowed delivery
        # 'dom_export' duplicated 'domains' at same position → empty domains chunk
        # 'soft_export'/'tech_export' matched partial phrases inside other chunks
    ]

    cat_starts = []
    for key, pat in SKILL_CATS:
        m = pat.search(skill_blob)
        if m:
            cat_starts.append((m.end(), key))
    cat_starts.sort(key=lambda x: x[0])

    cat_chunks: dict = {}
    for i, (start, key) in enumerate(cat_starts):
        end   = cat_starts[i + 1][0] if i + 1 < len(cat_starts) else len(skill_blob)
        chunk = skill_blob[start:end]
        if i + 1 < len(cat_starts):
            for _, npat in SKILL_CATS:
                nm = npat.search(chunk)
                if nm:
                    chunk = chunk[:nm.start()]
                    break
        cat_chunks[key] = _split_skill_items(chunk)

    # ── BUG-3 FIX: correct skill category → field mapping ────────────
    # tech_pm category contains actual technical tools (C++, Python, Docker…) → TECH
    # delivery/leadership → SOFT
    # domains → TOOLS
    prog_items   = (cat_chunks.get('tech_pm',      []) +
                    cat_chunks.get('programming',   []) +
                    cat_chunks.get('cloud_devops',  []))
    emb_items    = cat_chunks.get('embedded', [])

    soft_items   = (cat_chunks.get('delivery', []) +
                    cat_chunks.get('metrics',   []))
    domain_items =  cat_chunks.get('domains',   [])

    # Deduplicated tech skills: only programming tools + embedded
    seen, tech_out = set(), []
    for item in (prog_items + emb_items):
        k = item.lower().strip()
        if k and k not in seen and len(k) > 1 and ':' not in item:
            seen.add(k)
            tech_out.append(item.strip())

    result['skills']['tech']  = ', '.join(tech_out[:20])
    result['skills']['soft']  = ', '.join(soft_items[:16])
    result['skills']['tools'] = ', '.join(domain_items[:20])
    result['skills'].pop('metrics', None)

    # Fallback: if ALL structured patterns failed (no category headers)
    if not result['skills']['tech'] and not result['skills']['soft'] and skill_blob:
        raw_items = [
            i.strip() for i in re.split(r'[\u2022\u00b7,\n]', skill_blob)
            if 2 < len(i.strip()) < 35 and ':' not in i
        ]
        result['skills']['tech'] = ', '.join(raw_items[:15])

    # ── 8. Post-process: Summary ─────────────────────────────────────
    if result['_sum_bullets']:
        summary_list = [b.strip() for b in result['_sum_bullets'][:6] if b.strip()]
    elif result['summary']:
        raw   = result['summary'].strip()
        parts = [p.strip() for p in re.split(r'[•\n]+', raw) if p.strip()]
        if len(parts) <= 1:
            parts = [s.strip() for s in re.split(r'(?<=[.!?])\s+', raw) if s.strip()]
        summary_list = parts[:6]
    else:
        summary_list = []

    result['summary'] = summary_list
    summary_text = ' '.join(summary_list)
    del result['_sum_bullets']

    # ── 9. Post-process: Education — ensure start/end fields ─────────
    for edu in result['education']:
        yr = edu.get('year', '')
        if yr and not edu.get('end'):
            edu['end'] = yr
        if 'start' not in edu:
            edu['start'] = ''
        if 'end' not in edu:
            edu['end'] = yr
        if edu.get('start') and edu.get('end') and edu['start'] == edu['end']:
            edu['start'] = ''

    # ── 10. Post-process: Certifications — infer from summary/title ──
    if not result['certifications']:
        KNOWN_CERTS = {
            'PMP':   ('Project Management Professional', 'PMI Institute'),
            'PgMP':  ('Program Management Professional', 'PMI Institute'),
            'CAPM':  ('Certified Associate in Project Management', 'PMI Institute'),
            'CSM':   ('Certified Scrum Master', 'Scrum Alliance'),
            'CSPO':  ('Certified Scrum Product Owner', 'Scrum Alliance'),
            'CISSP': ('CISSP', 'ISC2'),
        }
        scan  = result['personal'].get('title', '') + ' ' + summary_text
        added = set()
        for abbr, (full_name, issuer) in KNOWN_CERTS.items():
            if re.search(rf'\b{abbr}\b', scan) and abbr not in added:
                added.add(abbr)
                result['certifications'].append({'name': full_name, 'issuer': issuer, 'year': ''})
        for abbr, (full_name, issuer) in KNOWN_CERTS.items():
            if abbr not in added and re.search(rf'\b{abbr}\b', raw_text):
                added.add(abbr)
                result['certifications'].append({'name': full_name, 'issuer': issuer, 'year': ''})

    return result