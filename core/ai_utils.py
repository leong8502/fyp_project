"""
ai_utils.py — Jaccard similarity + weighted scoring for freelancer-job matching.

Algorithm weights:
  40%  Skills Jaccard   (merged: freelancer profile skills ∪ query-typed skills vs project skills)
  20%  Language match   (freelancer profile languages vs project preferred language — profile only)
  20%  Experience years (numerical: min(effective_exp / project_exp, 1))
  10%  Work title match (Jaccard of past job titles vs project title keywords)
  10%  Availability     (exact availability match vs project experience_level heuristic)

Score is 0–100 (float, rounded to 1 dp).

RELEVANCE GATE (applied when a query is provided):
  If none of the query skill tokens appear in the project title, description, or required_skills,
  the project is suppressed (score set to 0) so unrelated results don't appear.
"""

import re
from itertools import islice


# ---------------------------------------------------------------------------
# Tech synonym / alias dictionary
# ---------------------------------------------------------------------------

# Maps a normalised query term → set of equivalent tokens to search in project text.
_TECH_SYNONYMS: dict = {
    # Full-stack variations
    'fullstack':    {'full-stack', 'full stack', 'frontend', 'backend', 'python', 'react', 'node', 'django', 'javascript'},
    'full-stack':   {'fullstack', 'full stack', 'frontend', 'backend', 'python', 'react', 'node'},
    'full stack':   {'fullstack', 'full-stack', 'frontend', 'backend'},
    # Front-end / back-end
    'frontend':     {'front-end', 'front end', 'react', 'vue', 'angular', 'javascript', 'html', 'css'},
    'front-end':    {'frontend', 'front end', 'react', 'vue', 'angular', 'javascript'},
    'backend':      {'back-end', 'back end', 'server', 'api', 'django', 'flask', 'node', 'express'},
    'back-end':     {'backend', 'back end', 'server', 'api'},
    # ML / AI / Data
    'ml':           {'machine learning', 'deep learning', 'ai', 'artificial intelligence', 'tensorflow', 'pytorch'},
    'ai':           {'artificial intelligence', 'machine learning', 'ml', 'deep learning'},
    'datascience':  {'data science', 'data scientist', 'machine learning', 'analytics', 'pandas', 'python'},
    'data science': {'datascience', 'data scientist', 'machine learning', 'analytics'},
    # Mobile
    'mobile':       {'android', 'ios', 'flutter', 'react native', 'swift', 'kotlin'},
    # E-commerce
    'ecommerce':    {'e-commerce', 'e commerce', 'shopify', 'woocommerce', 'payment', 'cart'},
    'e-commerce':   {'ecommerce', 'e commerce', 'shopify', 'woocommerce', 'payment'},
    # DevOps / Cloud
    'devops':       {'dev-ops', 'ci/cd', 'docker', 'kubernetes', 'aws', 'cloud'},
    'cloud':        {'aws', 'azure', 'gcp', 'google cloud', 'docker', 'kubernetes'},
    # Design
    'design':       {'ui', 'ux', 'figma', 'adobe', 'photoshop', 'graphic', 'ui/ux'},
    'ui':           {'ux', 'figma', 'design', 'user interface', 'frontend', 'css'},
    'ux':           {'ui', 'figma', 'design', 'user experience', 'wireframe'},
    # Abbreviations
    'js':           {'javascript'},
    'ts':           {'typescript'},
    'py':           {'python'},
    'db':           {'database', 'sql', 'mysql', 'postgresql', 'mongodb'},
    'seo':          {'search engine', 'digital marketing', 'google ads', 'content'},
}


def _expand_with_synonyms(tokens: list) -> list:
    """Expand query tokens with synonym sets for broader project text matching."""
    expanded: set = set()
    for t in tokens:
        expanded.add(t)
        if t in _TECH_SYNONYMS:
            expanded.update(_TECH_SYNONYMS[t])
    return list(expanded)


def _gemini_parse_query(raw_query: str):
    """
    Uses Gemini to parse a natural-language search query into structured fields.
    Returns dict or None if Gemini unavailable.
    """
    try:
        import os, json
        import google.generativeai as genai
        try:
            from django.conf import settings as _s
            api_key = getattr(_s, 'FREELANCER_GEMINI_API_KEY', '') or os.environ.get('FREELANCER_GEMINI_API_KEY', '')
            if not api_key:
                api_key = getattr(_s, 'GEMINI_API_KEY', '') or os.environ.get('GEMINI_API_KEY', '')
        except Exception:
            api_key = os.environ.get('FREELANCER_GEMINI_API_KEY', '') or os.environ.get('GEMINI_API_KEY', '')

        if not api_key:
            return None

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        prompt = (
            'You are a search query parser for a freelancer job-matching platform.\n'
            f'Parse this query: "{raw_query}"\n\n'
            'Extract:\n'
            '- skills: list of technology/skill keywords (normalise e.g. "fullstack"→"full-stack", "js"→"javascript")\n'
            '- experience_years: integer or null (recognise "3 yr", "3yrs", "three years" etc.)\n'
            '- availability: "full_time", "part_time", "contract", or null\n'
            '- languages: list of spoken languages (e.g. "english", "malay")\n\n'
            'Respond ONLY in JSON, no markdown:\n'
            '{"skills": [...], "experience_years": null, "availability": null, "languages": []}'
        )
        resp = model.generate_content(prompt)
        text = resp.text.strip()
        text = re.sub(r'^```[a-z]*\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
        import json
        data = json.loads(text)
        return {
            'skills':       [str(s).lower() for s in data.get('skills', []) if s],
            'experience':   int(data['experience_years']) if data.get('experience_years') is not None else None,
            'availability': data.get('availability'),
            'languages':    [str(l).lower() for l in data.get('languages', []) if l],
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Keyword parsing (NLP-enhanced)
# ---------------------------------------------------------------------------

def parse_keywords(query: str) -> dict:
    """
    Parses a raw search query into structured fields.
    Tries Gemini NLP first; falls back to regex + synonym expansion.

    Returns:
        {
          'skills':       list[str],   # tech/skill tokens (with synonyms expanded)
          'experience':   int | None,
          'availability': str | None,  # 'full_time' | 'part_time' | 'contract'
          'languages':    list[str],
        }
    """
    # ── Try Gemini NLP first ───────────────────────────────────────
    gemini_result = _gemini_parse_query(query)
    if gemini_result is not None:
        expanded = _expand_with_synonyms(gemini_result.get('skills', []))
        return {
            'skills':       expanded,
            'languages':    gemini_result.get('languages', []),
            'experience':   gemini_result.get('experience'),
            'availability': gemini_result.get('availability'),
        }

    # ── Regex fallback ───────────────────────────────────────────
    raw = query.lower()

    # Extract experience years
    exp_match = re.search(r'(\d+)\s*(?:\+\s*)?(?:years?|yrs?)', raw)
    experience = int(exp_match.group(1)) if exp_match else None
    if exp_match:
        raw = raw.replace(exp_match.group(0), '', 1)

    # Extract availability
    availability = None
    if re.search(r'\bfull[\s-]?time\b', raw):
        availability = 'full_time'
        raw = re.sub(r'\bfull[\s-]?time\b', '', raw)
    elif re.search(r'\bpart[\s-]?time\b', raw):
        availability = 'part_time'
        raw = re.sub(r'\bpart[\s-]?time\b', '', raw)
    elif re.search(r'\bcontract\b', raw):
        availability = 'contract'
        raw = re.sub(r'\bcontract\b', '', raw)

    # Extract spoken languages
    _KNOWN_LANGS = {'english', 'malay', 'chinese', 'mandarin', 'tamil', 'hindi',
                    'japanese', 'korean', 'french', 'german', 'spanish'}
    query_langs = []
    for lang in _KNOWN_LANGS:
        if re.search(r'\b' + re.escape(lang) + r'\b', raw):
            query_langs.append(lang)
            raw = re.sub(r'\b' + re.escape(lang) + r'\b', '', raw)

    # Remaining tokens = tech/skill keywords
    _stop = {'and', 'or', 'the', 'a', 'an', 'for', 'in', 'with', 'to', 'of',
             'is', 'are', 'was', 'were', 'my', 'i', 'have', 'has', 'using',
             'experience', 'developer', 'engineer', 'working'}
    raw_tokens = [t for t in re.split(r'[\s,;/|]+', raw)
                  if len(t) >= 2 and t not in _stop]

    # Expand with synonyms (e.g. 'fullstack' → full-stack, react, django …)
    expanded = _expand_with_synonyms(raw_tokens)

    return {
        'skills':       expanded,
        'languages':    query_langs,
        'experience':   experience,
        'availability': availability,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROFICIENCY_WEIGHT = {
    'basic':          0.25,
    'conversational': 0.50,
    'fluent':         0.85,
    'native':         1.00,
}

def _to_set(text: str) -> set:
    """Lowercased, comma-separated text → set of stripped tokens."""
    if not text:
        return set()
    return {t.strip().lower() for t in text.split(',') if t.strip()}

def _jaccard(a: set, b: set) -> float:
    """Jaccard similarity: |A ∩ B| / |A ∪ B|.  Returns 0 if both empty."""
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


# ---------------------------------------------------------------------------
# Main matching class
# ---------------------------------------------------------------------------

class AISearchManager:
    """
    Jaccard similarity + weighted scoring for freelancer–project matching.
    Drop-in replacement for the old TF-IDF cosine similarity manager.
    """

    # Component weights (must sum to 1.0)
    W_SKILLS        = 0.40
    W_LANGUAGE      = 0.20
    W_EXPERIENCE    = 0.20
    W_WORK_TITLE    = 0.10
    W_AVAILABILITY  = 0.10

    def calculate_match_scores(self, projects, freelancer=None, query=None):
        """
        Returns list of (project, score) tuples, score in [0, 100].
        Compatible with the previous cosine-similarity version's signature.
        """
        parsed = parse_keywords(query) if query else {'skills': [], 'languages': [], 'experience': None, 'availability': None}
        results = []
        for project in projects:
            score, _, _ = self._score_project(project, freelancer, parsed, has_query=bool(query and query.strip()))
            final_score: float = float(score)
            results.append((project, round(final_score, 1)))  # type: ignore[call-overload]
        return results

    def calculate_match_details(self, projects, freelancer=None, query=None):
        """
        Extended version used by the search view.
        Returns list of dicts:
          { project, score, suitability_sentence, calculation_logic }
        """
        parsed = parse_keywords(query) if query else {'skills': [], 'languages': [], 'experience': None, 'availability': None}
        has_query = bool(query and query.strip())
        results = []
        for project in projects:
            score, sentence, logic = self._score_project(project, freelancer, parsed, has_query=has_query)
            final_score: float = float(score)
            results.append({
                'project':              project,
                'score':                round(final_score, 1),  # type: ignore[call-overload]
                'suitability_sentence': sentence,
                'calculation_logic':    logic,
            })
        return results

    # ------------------------------------------------------------------
    # Internal scoring
    # ------------------------------------------------------------------

    def _score_project(self, project, freelancer, parsed: dict, has_query: bool = False) -> tuple[float, str, str]:
        """
        Computes the weighted match score for one project.
        Returns (score_0_to_100, suitability_sentence, calculation_logic_string).
        """
        # ── Freelancer data ────────────────────────────────────────────
        if freelancer:
            fl_skills_set   = set(freelancer.skills_list)
            fl_exp_years    = getattr(freelancer, 'experience_years', 0) or 0
            fl_availability = getattr(freelancer, 'availability_status', '') or ''

            # Language data: {lang_lower: weight}
            fl_lang_map = {}
            try:
                for lang_obj in freelancer.languages.all():
                    w = _PROFICIENCY_WEIGHT.get(lang_obj.proficiency.lower(), 0.5)
                    fl_lang_map[lang_obj.language.strip().lower()] = w
            except Exception:
                pass

            # Work title keywords: past job titles + portfolio titles/descriptions
            fl_work_titles = set()
            try:
                for we in freelancer.work_experiences.all():
                    for token in re.split(r'[\s,/]+', (we.job_title or '').lower()):
                        if len(token) >= 3:
                            fl_work_titles.add(token)
            except Exception:
                pass
            try:
                for pf in freelancer.portfolios.all():
                    for token in re.split(r'[\s,/\-_]+', (pf.title or '').lower()):
                        if len(token) >= 3:
                            fl_work_titles.add(token)
                    for token in re.split(r'[\s,/\-_]+', (pf.description or '').lower()):
                        if len(token) >= 3:
                            fl_work_titles.add(token)
            except Exception:
                pass
        else:
            fl_skills_set   = set()
            fl_exp_years    = 0
            fl_availability = ''
            fl_lang_map     = {}
            fl_work_titles  = set()

        # ── Query-keyword data ─────────────────────────────────────────
        query_skills = set(t.lower() for t in parsed.get('skills', []))
        query_langs  = set(t.lower() for t in parsed.get('languages', []))
        query_exp    = parsed.get('experience')    # int or None
        query_avail  = parsed.get('availability')  # str or None

        # ── Effective values for scoring ───────────────────────────────
        # IMPORTANT: effective_skills uses only the freelancer's PROFILE skills for Jaccard.
        # query_skills are used ONLY for the relevance gate (below), NOT for scoring.
        # This ensures the score on the search card is IDENTICAL to the detail page score.
        effective_skills = fl_skills_set

        # Experience: prefer query if specified, else profile
        effective_exp = query_exp if query_exp is not None else fl_exp_years

        # Availability: prefer query if specified, else profile
        effective_avail = query_avail if query_avail else fl_availability

        # Language: profile + query-stated languages
        effective_lang_map = fl_lang_map.copy()
        for ql in query_langs:
            # Query-stated language gets high weight (effectively native/fluent)
            effective_lang_map[ql] = max(effective_lang_map.get(ql, 0.0), 0.95)

        # ── Relevance gate (only when a query is provided) ─────────────
        # If a query was given but produced NO skill tokens (e.g. "hi", "hello"),
        # suppress ALL results — nothing can match an empty keyword set.
        if has_query and not query_skills:
            logic = "Search query did not contain any recognisable skill keywords."
            sentence = "No recognisable keywords found — please try a specific skill, technology, or role."
            return 0.0, sentence, logic

        # At least ONE query skill token must appear in project title, description,
        # or required_skills to pass. This prevents unrelated projects from showing up.
        if has_query and query_skills:
            proj_text = ' '.join([
                project.title or '',
                project.description or '',
                project.required_skills or '',
            ]).lower()
            has_any_match = any(token in proj_text for token in query_skills)
            if not has_any_match:
                # Irrelevant project — suppress with score=0
                logic = "No query keywords matched this project's title, description, or required skills."
                sentence = "This project does not appear relevant to your search keywords."
                return 0.0, sentence, logic

        # ── Project data ───────────────────────────────────────────────
        proj_skills_set = _to_set(project.required_skills)
        proj_exp_req    = getattr(project, 'year_of_experience', 0) or 0
        proj_lang       = (project.preferred_language or '').strip().lower()

        # Project title keywords for work-title match
        proj_title_tokens = set(
            t for t in re.split(r'[\s,/\-]+', project.title.lower()) if len(t) >= 3
        )

        # ── Component scores ───────────────────────────────────────────

        # 1) Skills Jaccard (40%) — uses merged profile+query skills
        skills_jaccard = _jaccard(effective_skills, proj_skills_set)
        common_skills  = effective_skills & proj_skills_set

        # 2) Language match (20%)
        if proj_lang:
            # Check merged language map (profile + query-stated languages)
            lang_score = effective_lang_map.get(proj_lang, 0.0)
        else:
            # No language preference = full marks
            lang_score = 1.0

        # 3) Experience years (20%)
        if proj_exp_req == 0:
            exp_score = 1.0
        else:
            exp_score = min(effective_exp / proj_exp_req, 1.0)

        # 4) Work title Jaccard (10%)
        work_title_jaccard = _jaccard(fl_work_titles, proj_title_tokens)

        # 5) Availability (10%)
        if not effective_avail:
            avail_score = 0.5   # unknown → neutral
        elif effective_avail == 'not_available':
            avail_score = 0.0
        elif effective_avail in ('full_time', 'contract'):
            avail_score = 1.0
        else:
            avail_score = 0.7   # part_time is eligible but partial

        # ── Weighted total ─────────────────────────────────────────────
        raw_score = (
            self.W_SKILLS       * skills_jaccard       +
            self.W_LANGUAGE     * lang_score           +
            self.W_EXPERIENCE   * exp_score            +
            self.W_WORK_TITLE   * work_title_jaccard   +
            self.W_AVAILABILITY * avail_score
        )
        score = raw_score * 100   # 0–100

        # ── Human-readable breakdown (for info popup) ──────────────────
        common_list  = ', '.join(sorted(common_skills)) if common_skills else 'none'
        lang_display = proj_lang.title() if proj_lang else 'Any'

        lang_source = ''
        if proj_lang:
            is_in_profile = proj_lang in fl_lang_map
            is_in_query   = proj_lang in query_langs
            
            if is_in_profile and is_in_query:
                lang_source = ' (profile + query)'
            elif is_in_query:
                lang_source = ' (from search query)'
            elif is_in_profile:
                lang_source = ' (from profile)'
            else:
                lang_source = ' (not found)'

        logic = (
            f"Skills Jaccard: {skills_jaccard:.0%} "
            f"({len(common_skills)} common: {common_list}) x 40%\n"
            f"Language ({lang_display}): {lang_score:.0%}{lang_source} x 20%\n"
            f"Experience: {effective_exp} yr / {proj_exp_req} yr req -> {exp_score:.0%} x 20%\n"
            f"Work Title overlap: {work_title_jaccard:.0%} x 10%\n"
            f"Availability ({effective_avail or 'unknown'}): {avail_score:.0%} x 10%\n"
            f"Total: {score:.1f}%"
        )

        # ── Suitability sentence ───────────────────────────────────────
        sentence = _build_sentence(
            score, common_skills, effective_exp, proj_exp_req,
            effective_avail, lang_score, proj_lang
        )

        return score, sentence, logic


# ---------------------------------------------------------------------------
# Sentence generator
# ---------------------------------------------------------------------------

def _build_sentence(score, common_skills, fl_exp, proj_exp, fl_avail, lang_score, proj_lang):
    """Generates a short plain-English suitability sentence."""
    if score >= 75:
        strength = "an excellent"
    elif score >= 50:
        strength = "a good"
    elif score >= 25:
        strength = "a fair"
    else:
        strength = "a low"

    parts: list[str] = []

    if common_skills:
        # Cast to a strictly typed string list to satisfy Pyre slicing
        skill_list: list[str] = list(sorted(common_skills))
        skill_str = ', '.join(islice(skill_list, 3))
        if len(common_skills) > 3:
            skill_str += f" +{len(common_skills)-3} more"
        parts.append(f"your {skill_str} skills align")
    else:
        parts.append("no direct skill overlap found")

    if proj_exp > 0:
        if fl_exp >= proj_exp:
            parts.append(f"your {fl_exp} yr experience meets the {proj_exp} yr requirement")
        else:
            parts.append(f"your {fl_exp} yr experience is below the {proj_exp} yr requirement")

    if proj_lang:
        if lang_score >= 0.85:
            parts.append(f"you speak {proj_lang.title()} at a high level")
        elif lang_score > 0:
            parts.append(f"you have some {proj_lang.title()} proficiency")
        else:
            parts.append(f"the preferred language ({proj_lang.title()}) is not in your profile")

    detail = "; ".join(parts) if parts else "general profile match"
    return f"You are {strength} match ({score:.0f}%): {detail}."


# ---------------------------------------------------------------------------
# Recommendations shortcut (used on freelancer home)
# ---------------------------------------------------------------------------

def get_recommendations(freelancer, limit=4):
    """
    Returns top recommended (project, score) pairs for the freelancer home page.
    """
    from core.models import Project  # type: ignore

    open_projects = list(Project.objects.filter(status='open'))
    if not open_projects:
        return []

    manager = AISearchManager()
    scored: list[tuple] = manager.calculate_match_scores(open_projects, freelancer=freelancer)
    scored = sorted(scored, key=lambda x: x[1], reverse=True)
    return list(islice(scored, limit))
