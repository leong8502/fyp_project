"""
match_result.py – Standalone views for the AI Match Result detail page.
These views do NOT modify any existing client views or templates.
"""
import os
import re
import logging
from itertools import islice

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

logger = logging.getLogger(__name__)


# ── Proficiency weights (mirrors ai_utils.py) ──────────────────────────────
_PROFICIENCY_WEIGHT = {
    'basic':          0.25,
    'conversational': 0.50,
    'fluent':         0.85,
    'native':         1.00,
}

def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0

def _to_set(text: str) -> set:
    if not text:
        return set()
    return {t.strip().lower() for t in text.split(',') if t.strip()}


def _generate_fallback_feedback(d: dict) -> dict:
    """
    Generates rule-based localized feedback mirroring the JSON structure of the AI
    when the Google Gemini API quota is hit or unavailable, guaranteeing 100% uptime.
    """
    feedback = {}
    
    # 1. Skills
    if not d['missing_skills']:
        feedback['skills'] = "Excellent match! You possess all the required core skills for this position."
    elif d['skills_pct'] >= 40.0:
        missing_str = ", ".join(d['missing_skills'][:2])
        feedback['skills'] = f"Good match. You have {len(d['common_skills'])} of {len(d['proj_skills'])} required skills. Consider brushing up on {missing_str}."
    else:
        missing_str = ", ".join(d['missing_skills'][:3])
        feedback['skills'] = f"You are missing some key skills like {missing_str}. Focus on gaining these moving forward."
        
    # 2. Language
    if d['lang_status'] == 'any':
        feedback['language'] = "There are no specific language requirements for this project, so you're good to go."
    elif d['language_pct'] >= 80.0:
        feedback['language'] = f"Your {d['lang_proficiency'] or 'high'} proficiency in {d['proj_lang']} is a strong asset here."
    elif d['language_pct'] > 0:
        feedback['language'] = f"Your basic proficiency in {d['proj_lang']} meets the basic communication needs."
    else:
        feedback['language'] = f"The project prefers {d['proj_lang']}, which currently isn't listed in your profile languages."
        
    # 3. Experience
    if d['proj_exp_req'] == 0:
        feedback['experience'] = "This role is completely flexible with experience levels, making you a suitable candidate!"
    elif d['experience_pct'] == 100.0:
        feedback['experience'] = f"Your {d['fl_exp_years']} years of experience perfectly meets their {d['proj_exp_req']}-year requirement."
    else:
        feedback['experience'] = f"Your {d['fl_exp_years']} years of experience is below the {d['proj_exp_req']} year requirement, which could be a slight disadvantage."
        
    # 4. Past Projects
    if d['work_title_pct'] == 100.0:
        feedback['work_title'] = "You have proven experience on this platform entirely covering this project's required skills."
    elif d['work_title_pct'] >= 50.0:
        feedback['work_title'] = "Your past completed projects cover a majority of the core requirements for this role."
    elif d['work_title_pct'] > 0:
        feedback['work_title'] = "You have previously completed projects that share some skills with this position."
    else:
        feedback['work_title'] = "You haven't completed past projects on this platform with these specific skills yet."

    # 5. Availability
    if d['availability_pct'] == 100.0:
        feedback['availability'] = f"Your {d['fl_availability']} availability fits their standard expectations perfectly."
    elif d['availability_pct'] >= 50.0:
        feedback['availability'] = f"Your {d['fl_availability']} schedule is acceptable, though full-time engagement is often preferred."
    else:
        feedback['availability'] = "Your current availability status indicates you might not be ready to take this on."
        
    # 6. Overall
    if d['total_pct'] >= 70.0:
        feedback['overall'] = "You are a fantastic match for this role. You are highly encouraged to apply immediately and showcase your strengths!"
    elif d['total_pct'] >= 40.0:
        feedback['overall'] = "You are a fair match. Be sure to highlight your strongest overlapping skills in your proposal to stand out."
    else:
        feedback['overall'] = "This project might be a stretch given your profile match, but you can still apply and emphasize your willingness to learn."

    return feedback


def _can_view_match(request, project):
    """Returns True if the request user is a freelancer."""
    return hasattr(request.user, 'freelancer')


def _compute_match_details(project, freelancer, query_skills=None) -> dict:
    """
    Recomputes the Jaccard match for a single freelancer↔project pair.
    query_skills: set of skill tokens typed in the search bar (merged into effective skills).
    Returns a rich dict with per-field breakdown for the UI.
    """
    if query_skills is None:
        query_skills = set()
    # ── Freelancer data ───────────────────────────────────────────────────────
    fl_skills_set   = set(freelancer.skills_list) if hasattr(freelancer, 'skills_list') else _to_set(freelancer.skills or '')
    fl_exp_years    = getattr(freelancer, 'experience_years', 0) or 0
    fl_availability = getattr(freelancer, 'availability_status', '') or ''

    fl_lang_map = {}
    try:
        for lang_obj in freelancer.languages.all():
            w = _PROFICIENCY_WEIGHT.get(lang_obj.proficiency.lower(), 0.5)
            fl_lang_map[lang_obj.language.strip().lower()] = w
    except Exception:
        pass

    # Past project required skills (replaces old work title logic)
    fl_work_titles = set()
    try:
        for app in freelancer.applications.filter(status='accepted'):
            if app.project.required_skills:
                fl_work_titles.update(_to_set(app.project.required_skills))
    except Exception:
        pass

    # ── Project data ──────────────────────────────────────────────────────────
    proj_skills_set   = _to_set(project.required_skills)
    proj_exp_req      = getattr(project, 'year_of_experience', 0) or 0
    proj_lang         = (project.preferred_language or '').strip().lower()
    proj_title_tokens = proj_skills_set

    # ── 1. Skills Jaccard (40%) ───────────────────────────────────────────────
    effective_fl_skills = fl_skills_set | query_skills
    common_skills  = effective_fl_skills & proj_skills_set
    missing_skills = proj_skills_set - effective_fl_skills
    extra_skills   = effective_fl_skills - proj_skills_set
    # Note: Jaccard score uses effective_fl_skills so the math matches the display
    skills_jaccard = _jaccard(effective_fl_skills, proj_skills_set)

    # ── 2. Language (20%) ─────────────────────────────────────────────────────
    if proj_lang:
        lang_score   = fl_lang_map.get(proj_lang, 0.0)
        lang_status  = 'found' if lang_score > 0 else 'missing'
        proficiency  = next(
            (k for k, v in _PROFICIENCY_WEIGHT.items() if abs(v - lang_score) < 0.01),
            None
        )
    else:
        lang_score   = 1.0
        lang_status  = 'any'
        proficiency  = None

    # ── 3. Experience (20%) ───────────────────────────────────────────────────
    if proj_exp_req == 0:
        exp_score = 1.0
    else:
        exp_score = min(fl_exp_years / proj_exp_req, 1.0)

    # ── 4. Past Project Relevance (10%) ───────────────────────────────────────
    title_common   = fl_work_titles & proj_title_tokens
    if not proj_title_tokens:
        title_jaccard = 1.0
    else:
        title_jaccard = len(title_common) / len(proj_title_tokens)

    # ── 5. Availability (10%) ─────────────────────────────────────────────────
    if not fl_availability or fl_availability == 'not_available':
        avail_score = 0.0 if fl_availability == 'not_available' else 0.5
    elif fl_availability in ('full_time', 'contract'):
        avail_score = 1.0
    else:
        avail_score = 0.7  # part_time

    # ── Weighted total ────────────────────────────────────────────────────────
    total = (
        0.40 * skills_jaccard +
        0.20 * lang_score +
        0.20 * exp_score +
        0.10 * title_jaccard +
        0.10 * avail_score
    ) * 100

    return {
        # Per-field scores (0–100 %)
        'skills_pct':       round(skills_jaccard * 100, 1),
        'language_pct':     round(lang_score      * 100, 1),
        'experience_pct':   round(exp_score        * 100, 1),
        'work_title_pct':   round(title_jaccard    * 100, 1),
        'availability_pct': round(avail_score       * 100, 1),
        'total_pct':        round(total, 1),

        # Skills detail
        'proj_skills':     sorted(proj_skills_set),
        'fl_skills':       sorted(effective_fl_skills),
        'common_skills':   sorted(common_skills),
        'missing_skills':  sorted(missing_skills),
        'extra_skills':    sorted(extra_skills),

        # Language detail
        'proj_lang':       proj_lang.title() if proj_lang else 'Any',
        'fl_languages':    {k.title(): v for k, v in fl_lang_map.items()},
        'lang_status':     lang_status,
        'lang_proficiency': proficiency,

        # Experience detail
        'fl_exp_years':    fl_exp_years,
        'proj_exp_req':    proj_exp_req,

        # Work title detail
        'title_common':    sorted(title_common),
        'fl_work_titles':  sorted(fl_work_titles),
        'proj_title_kw':   sorted(proj_title_tokens),

        # Availability detail
        'fl_availability': fl_availability.replace('_', ' ').title() if fl_availability else 'Not set',
        'avail_pct':       round(avail_score * 100),
    }


# ── Freelancer view ───────────────────────────────────────────────────────────

@login_required
def freelancer_match_result_by_project(request, project_id):
    """Renders the standalone AI match result detail page for a freelancer."""
    from core.models import Project
    from core.ai_utils import parse_keywords

    if not hasattr(request.user, 'freelancer'):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Only freelancers can access this page.")

    project    = get_object_or_404(Project, id=project_id)
    freelancer = request.user.freelancer
    
    q_str = request.GET.get('q', '')
    parsed = parse_keywords(q_str) if q_str else {}
    query_skills = set(parsed.get('skills', []))
    
    details    = _compute_match_details(project, freelancer, query_skills)

    # ── Use stored search-time score if available (ensures consistency with search list) ──
    # The search view saves scores to MatchScore; we display that score here so the
    # "42%" shown on the card always matches the "42%" shown on the detail page.
    try:
        from core.models import MatchScore
        stored_ms = MatchScore.objects.filter(
            project=project,
            freelancer=freelancer,
        ).order_by('-created_at').first()
        if stored_ms is not None and stored_ms.overall_score is not None:
            details = dict(details)
            details['total_pct'] = round(float(stored_ms.overall_score), 1)
    except Exception:
        pass  # If MatchScore table doesn't exist or query fails, use computed value

    return render(request, 'core/freelancer_matchresult.html', {
        'project':    project,
        'freelancer': freelancer,
        'details':    details,
    })


# ── Client view (kept for backwards compat if linked from match lists) ────────

@login_required
def freelancer_match_result(request, match_id):
    """Client-side view using a precomputed ProjectMatch record."""
    from core.models import ProjectMatch

    match = get_object_or_404(ProjectMatch, id=match_id)
    if not (hasattr(request.user, 'client') and match.project.client == request.user.client):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("You do not have permission to view this page.")

    project    = match.project
    freelancer = match.freelancer
    details    = _compute_match_details(project, freelancer)

    return render(request, 'core/freelancer_matchresult.html', {
        'project':    project,
        'freelancer': freelancer,
        'details':    details,
    })


# ── AI analysis API ────────────────────────────────────────────────────────────

@login_required
def api_freelancer_match_ai_analysis(request, project_id):
    """
    JSON endpoint: returns Gemini AI feedback for each scoring field.
    Called from the match result page via AJAX.
    """
    from core.models import Project
    from core.ai_utils import parse_keywords
    from django.core.cache import cache
    import json
    import time

    project    = get_object_or_404(Project, id=project_id)
    freelancer = request.user.freelancer if hasattr(request.user, 'freelancer') else None

    if not freelancer:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    q_str = request.GET.get('q', '')
    parsed = parse_keywords(q_str) if q_str else {}
    query_skills = set(parsed.get('skills', []))

    # Use Django's cache to store AI responses for 24h to completely bypass API quotas for repeated views
    cache_key = f"ai_feedback_{project.id}_{freelancer.id}_{hash(q_str)}"
    cached_data = cache.get(cache_key)
    if cached_data:
        return JsonResponse({'success': True, 'feedback': cached_data})

    d = _compute_match_details(project, freelancer, query_skills)

    prompt = f"""You are an expert AI career analyst for TalentSync, a freelancer marketplace.

A freelancer is considering applying for the project: "{project.title}".
Description: {(project.description or 'N/A')[:300]}

Here is their match breakdown (Jaccard similarity scoring):

1. SKILLS MATCH ({d['skills_pct']}% | weight 40%)
   - Project needs: {', '.join(d['proj_skills']) or 'not specified'}
   - Freelancer has: {', '.join(d['fl_skills']) or 'not listed'}
   - Matched: {', '.join(d['common_skills']) or 'none'}
   - Missing: {', '.join(d['missing_skills']) or 'none'}

2. LANGUAGE ({d['language_pct']}% | weight 20%)
   - Project prefers: {d['proj_lang']}
   - Freelancer speaks: {', '.join(d['fl_languages'].keys()) or 'not listed'}
   - Status: {d['lang_status']}

3. EXPERIENCE ({d['experience_pct']}% | weight 20%)
   - Project requires: {d['proj_exp_req']} years
   - Freelancer has: {d['fl_exp_years']} years

4. PAST PROJECT RELEVANCE ({d['work_title_pct']}% | weight 10%)
   - Overlapping past project skills: {', '.join(d['title_common']) or 'none'}

5. AVAILABILITY ({d['availability_pct']}% | weight 10%)
   - Freelancer status: {d['fl_availability']}

Overall match score: {d['total_pct']}%

For EACH of the 5 criteria above, write ONE concise sentence (max 20 words) of plain-English feedback.
Then write ONE overall recommendation sentence.

Respond ONLY in this exact JSON format (no markdown, no extra keys):
{{
  "skills": "...",
  "language": "...",
  "experience": "...",
  "work_title": "...",
  "availability": "...",
  "overall": "..."
}}"""

    try:
        import google.generativeai as genai
        # Try Django settings first (loaded from .env via python-dotenv), then os.environ
        try:
            from django.conf import settings as django_settings
            api_key = getattr(django_settings, 'FREELANCER_GEMINI_API_KEY', '') or os.environ.get('FREELANCER_GEMINI_API_KEY', '')
            if not api_key:
                api_key = getattr(django_settings, 'GEMINI_API_KEY', '') or os.environ.get('GEMINI_API_KEY', '')
        except Exception:
            api_key = os.environ.get('FREELANCER_GEMINI_API_KEY', '') or os.environ.get('GEMINI_API_KEY', '')

        if not api_key:
            raise ValueError("GEMINI_API_KEY not configured")
        genai.configure(api_key=api_key)
        model    = genai.GenerativeModel('gemini-2.0-flash')
        
        # Exponential backoff loop to automatically handle 429 errors from Google
        MAX_RETRIES = 3
        for attempt in range(MAX_RETRIES):
            try:
                response = model.generate_content(prompt)
                
                text = response.text.strip()
                text = re.sub(r'^```[a-z]*\n?', '', text)
                text = re.sub(r'\n?```$', '', text)

                data = json.loads(text)
                cache.set(cache_key, data, 86400) # Save in cache for 24 hrs
                return JsonResponse({'success': True, 'feedback': data})
                
            except Exception as loop_exc:
                err_str = str(loop_exc).lower()
                if attempt < MAX_RETRIES - 1 and ('429' in err_str or 'quota' in err_str or 'exhausted' in err_str or 'rate' in err_str):
                    time.sleep(1) # Sleep briefly, then retry
                    continue
                # If we hit max retries or it's a quota error on the last attempt, use the offline fallback generator
                fallback_data = _generate_fallback_feedback(d)
                # Don't cache fallbacks for 24h, just in case their quota resets soon. Use 10 minutes (600s).
                cache.set(cache_key, fallback_data, 600)
                return JsonResponse({'success': True, 'feedback': fallback_data})
                
    except Exception as exc:
        # Failsafe even if the entire API configuration crashes
        fallback_data = _generate_fallback_feedback(d)
        return JsonResponse({'success': True, 'feedback': fallback_data})
