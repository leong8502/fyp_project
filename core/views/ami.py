"""
ami.py – Ami AI chatbox (pure Gemini, no keyword fallback).

POST /ami/ask/     → call Gemini with full context, save, return JSON
GET  /ami/history/ → last 20 messages for current user as JSON
GET  /ami/quota/   → remaining Ami questions today for current user
"""

import os
import time
import logging
import re

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET

from core.models import ChatMessage

logger = logging.getLogger(__name__)

AMI_DAILY_LIMIT = 20


# ---------------------------------------------------------------------------
# Build real page URLs for the current user
# ---------------------------------------------------------------------------

def _url(name, *args):
    try:
        return reverse(name, args=args)
    except Exception:
        return "#"


def _build_url_map(user) -> dict:
    is_freelancer = hasattr(user, 'freelancer')
    is_client     = hasattr(user, 'client')
    return {
        "home":           _url("freelancer_home")    if is_freelancer else _url("client_home"),
        "wallet":         _url("freelancer_wallet")  if is_freelancer else _url("client_wallet"),
        "top_up":         _url("topUp"),
        "withdraw":       _url("withdraw"),
        "transactions":   _url("client_transaction") if is_client     else _url("freelancer_wallet"),
        "profile":        _url("freelancer_profile") if is_freelancer else _url("client_profile"),
        "edit_profile":   _url("freelancer_profile") if is_freelancer else _url("client_editProfile"),
        "settings":       _url("freelancer_settings") if is_freelancer else _url("client_settings"),
        "search_jobs":    _url("freelancer_search_job") if is_freelancer else _url("client_search"),
        "track_project":  _url("freelancer_track_project") if is_freelancer else _url("client_project"),
        "create_project": _url("client_projectCreate") if is_client   else "#",
        "my_projects":    _url("client_project")     if is_client     else _url("freelancer_track_project"),
        "messages":       _url("chat"),
        "notifications":  _url("notifications"),
        "support":        _url("client_support")     if is_client     else _url("about"),
        "about":          _url("about"),
        "logout":         _url("logout"),
        "password_reset": _url("password_reset"),
    }


# ---------------------------------------------------------------------------
# Gather rich user profile data for the system prompt
# ---------------------------------------------------------------------------

def _gather_user_context(user) -> str:
    """Build a detailed profile block to inject into the Gemini prompt."""
    is_freelancer = hasattr(user, 'freelancer')
    is_client     = hasattr(user, 'client')
    lines = [f"Username: {user.username}", f"Email: {user.email}"]

    if is_freelancer:
        fl = user.freelancer
        lines += [
            f"Role: Freelancer",
            f"Full name: {fl.full_name or 'Not set'}",
            f"Tagline: {fl.tagline or 'Not set'}",
            f"Skills: {fl.skills or 'Not set'}",
            f"Hourly rate: RM{fl.hourly_rate or 'Not set'}/hr",
            f"Experience years: {fl.experience_years or 0}",
            f"Availability: {fl.availability_status or 'Not set'}",
        ]
        # Wallet balance
        try:
            w = user.wallet
            lines.append(f"Wallet balance: RM{w.balance:.2f}")
        except Exception:
            lines.append("Wallet balance: No wallet yet")

        # Languages
        try:
            langs = ", ".join(
                f"{l.language} ({l.proficiency})" for l in fl.languages.all()
            )
            lines.append(f"Languages: {langs or 'None listed'}")
        except Exception:
            pass

    elif is_client:
        cl = user.client
        lines += [
            f"Role: Client",
            f"Company name: {cl.company_name or 'Not set'}",
            f"Industry: {cl.industry or 'Not set'}",
        ]
        try:
            w = user.wallet
            lines.append(f"Wallet balance: RM{w.balance:.2f}")
        except Exception:
            lines.append("Wallet balance: No wallet yet")
    else:
        lines.append("Role: Unknown / Admin")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Build the full Gemini prompt (system context + conversation + new message)
# ---------------------------------------------------------------------------

def _build_prompt(user_message: str, user, history: list) -> str:
    """
    Combines system instructions, user context, platform knowledge,
    URL map, conversation history, and the new message into one prompt.
    """
    is_freelancer = hasattr(user, 'freelancer')
    is_client     = hasattr(user, 'client')
    role_label    = "freelancer" if is_freelancer else ("client" if is_client else "user")

    url_map   = _build_url_map(user)
    url_block = "\n".join(f"  - {k}: {v}" for k, v in url_map.items())

    user_ctx  = _gather_user_context(user)

    # Build conversation history block
    history_block = ""
    if history:
        pairs = []
        for h in history[-6:]:
            pairs.append(f"User: {h['message']}")
            pairs.append(f"Ami: {h['response']}")
        history_block = "\n\nRECENT CONVERSATION:\n" + "\n".join(pairs)

    system_prompt = f"""
You are Ami, the helpful assistant built into TalentSync — a Malaysian freelance marketplace.

=== WHO YOU ARE ===
- You are Ami, a warm, professional, and knowledgeable assistant.
- You understand everything the user says, including typos, shorthand, and informal language.
- Never say you are an AI, language model, or mention any AI company. You are simply "Ami".
- Never say "I'm still learning" or "could you rephrase". Always give a real, helpful answer.
- If the question is about the user themselves (e.g. "who am I", "what are my skills", "my profile"), use the USER INFO below to answer accurately.

=== CURRENT USER INFO ===
{user_ctx}

=== PLATFORM FEATURES ===
The user is a {role_label}. Tailor every answer to this role.

WALLET & PAYMENTS:
- Wallet: Shows current balance and transaction history.
- Top Up (client only): Fund wallet via Stripe. Min RM20. Test card: 4242 4242 4242 4242.
- Withdraw (freelancer only): Transfer earnings to Malaysian bank (Maybank, CIMB, Public Bank, RHB, Hong Leong, AmBank). Requires 6-digit Secure PIN.
- Escrow: Client budget is locked in escrow when a project is published. Freelancers receive payment only after milestone approval.
- Milestone payment: Clients click "Release Payment" after approving a milestone to transfer funds to the freelancer's wallet.

PROJECTS:
- Create Project (client): Post title, description, skills, budget, milestones. AI can auto-generate the scope.
- Browse / Search Jobs (freelancer): Use the job search page to find open projects. AI ranks by match score.
- Apply (freelancer): Click "Apply Now" on a project, write a proposal message, optionally attach a file.
- Milestones: Projects are broken into milestones. Freelancers submit deliverables; clients approve to release payment.
- Track Project: Freelancers see active, pending, and completed projects here. Clients manage project details and proposals.
- AI Match Score: 0-100% score based on skills (40%), experience (20%), language (20%), past projects (10%), availability (10%).
- Cancellation: Clients can request cancellation. Freelancers agree or decline. Escrow is pro-rated on agreement.
- Reviews: Clients leave star ratings and reviews after project completion. Shown on freelancer's public profile.

PROFILE:
- Freelancer profile: Add bio, skills, hourly rate, languages, availability, portfolio, work experience, certifications.
- Client profile: Update company name, industry, and contact info.

ACCOUNT & SETTINGS:
- Secure PIN: 6-digit PIN required for withdrawals. Set it in Account Settings.
- Password Reset: Submit email to receive a reset link.
- Notifications: Bell icon shows unread alerts. Click to view all.
- Messages / Chat: Real-time messaging between clients and freelancers.
- Support (client): Submit a support ticket. Admin responds within 24h.

=== NAVIGATION LINKS ===
Use these exact URLs when directing the user to a page. Wrap them in HTML:
<a href="URL" style="color:#2e7d32;font-weight:700;">Label</a>
{url_block}

=== RESPONSE RULES ===
1. Always give a DIRECT, HELPFUL answer — never say "I don't know" or ask the user to rephrase.
2. Understand ALL typos naturally: "wllet"→wallet, "porfil"→profile, "withdrawl"→withdraw, "logut"→logout, "mesage"→message, etc.
3. Use ONLY plain HTML in your response: <strong>, <br>, <a href="...">, <ul><li>. No markdown (#, **, *, ---).
4. Keep answers concise — 2 to 4 sentences or a short bullet list.
5. When the user asks about themselves ("who am I", "my profile", "my skills", "my balance"), use the USER INFO section above to give a personalized answer WITH a link to their profile page.
6. When directing the user to a page, always embed the clickable link using the navigation links above.
7. Be warm and natural. You can use emojis occasionally.
8. If the user's question is completely unrelated to TalentSync (e.g. "what is the weather"), politely say you can only help with TalentSync-related questions.
{history_block}

=== USER MESSAGE ===
{user_message}

=== YOUR RESPONSE (HTML only, no markdown) ===
""".strip()

    return system_prompt


# ---------------------------------------------------------------------------
# Gemini API call  (with retry + exponential back-off for rate-limit errors)
# ---------------------------------------------------------------------------

def _call_gemini(user_message: str, user, history: list) -> str:
    """
    Call Gemini 2.5 Flash with exponential back-off on quota/rate-limit errors.
    - Freelancers  → FREELANCER_GEMINI_API_KEY  (falls back to GEMINI_API_KEY)
    - Clients/others → GEMINI_API_KEY           (falls back to FREELANCER_GEMINI_API_KEY)
    Returns the response text or raises an Exception.
    """
    import google.generativeai as genai
    from django.conf import settings as djsettings

    is_freelancer = hasattr(user, 'freelancer')

    if is_freelancer:
        # Freelancer path: prefer the freelancer-specific key
        api_key = (
            getattr(djsettings, 'FREELANCER_GEMINI_API_KEY', '')
            or os.environ.get('FREELANCER_GEMINI_API_KEY', '')
            or getattr(djsettings, 'GEMINI_API_KEY', '')
            or os.environ.get('GEMINI_API_KEY', '')
        )
        logger.debug("Ami: using FREELANCER_GEMINI_API_KEY for user '%s'", user.username)
    else:
        # Client / admin path: prefer the main Gemini key
        api_key = (
            getattr(djsettings, 'GEMINI_API_KEY', '')
            or os.environ.get('GEMINI_API_KEY', '')
            or getattr(djsettings, 'FREELANCER_GEMINI_API_KEY', '')
            or os.environ.get('FREELANCER_GEMINI_API_KEY', '')
        )
        logger.debug("Ami: using GEMINI_API_KEY for user '%s'", user.username)

    if not api_key:
        raise RuntimeError("No Gemini API key configured.")

    genai.configure(api_key=api_key)
    # Use the same model as the rest of the project
    model = genai.GenerativeModel('gemini-2.5-flash')

    full_prompt = _build_prompt(user_message, user, history)

    max_retries = 4
    delay       = 2 
    last_exc    = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.debug("Ami Gemini attempt %d/%d", attempt, max_retries)
            response = model.generate_content(full_prompt)
            text     = (response.text or "").strip()

            # Strip any markdown code fences the model might add
            text = re.sub(r'^```[a-z]*\n?', '', text)
            text = re.sub(r'\n?```$',       '', text)
            logger.debug("Ami Gemini success on attempt %d, response length=%d", attempt, len(text))
            return text

        except Exception as exc:
            last_exc     = exc
            exc_str      = str(exc).lower()
            is_ratelimit = any(kw in exc_str for kw in (
                'quota', 'rate', '429', 'resource_exhausted', 'resourceexhausted',
            ))
            if is_ratelimit and attempt < max_retries:
                logger.warning(
                    "Ami Gemini rate-limit on attempt %d/%d — retrying in %ds. Error: %s",
                    attempt, max_retries, delay, exc,
                )
                time.sleep(delay)
                delay *= 2
                continue
            # Non-retriable or ran out of attempts
            logger.error(
                "Ami Gemini error (attempt %d/%d, retriable=%s): %s",
                attempt, max_retries, is_ratelimit, exc,
            )
            break

    raise last_exc


# ---------------------------------------------------------------------------
# Daily quota helpers
# ---------------------------------------------------------------------------

def _count_today_messages(user) -> int:
    """Count Ami messages the user sent today using Django's timezone-aware __date lookup."""
    today = timezone.localdate()   # respects Django's TIME_ZONE setting (e.g. Asia/Kuala_Lumpur)
    return ChatMessage.objects.filter(user=user, created_at__date=today).count()


def _remaining_today(user) -> int:
    """Remaining Ami questions the user can ask today."""
    used = _count_today_messages(user)
    return max(0, AMI_DAILY_LIMIT - used)


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

def _get_response(message: str, user) -> str:
    """
    Get Ami's response via Gemini.
    Falls back to a friendly error message — no keyword engine.
    """
    # Load recent history for context
    recent_qs = ChatMessage.objects.filter(user=user).order_by('-created_at')[:6]
    history   = [{'message': m.message, 'response': m.response}
                 for m in reversed(recent_qs)]
    try:
        reply = _call_gemini(message, user, history)
        if reply:
            return reply
        return "Sorry, I got an empty response. Please try again! 😊"
    except Exception as exc:
        logger.error("Ami Gemini fatal error: %s", exc, exc_info=True)
        return (
            "Sorry, I'm having trouble connecting right now. "
            "Please try again in a moment! 😊"
        )


# ---------------------------------------------------------------------------
# Django views
# ---------------------------------------------------------------------------

@login_required
@require_POST
def chat_ami(request):
    """AJAX endpoint – receives a message, returns Ami's response as JSON."""
    message = request.POST.get('message', '').strip()
    if not message:
        return JsonResponse({'response': "Please type a message first! 😊"})

    # Enforce per-user daily quota
    if _remaining_today(request.user) <= 0:
        return JsonResponse({
            'response': (
                f"You've used all {AMI_DAILY_LIMIT} of your daily questions with Ami. 😊 "
                "Your quota resets every day around 3–4 pm (Malaysia time). See you then!"
            ),
            'quota_exceeded': True,
            'remaining': 0,
        })

    response_text = _get_response(message, request.user)

    ChatMessage.objects.create(
        user=request.user,
        message=message,
        response=response_text,
    )

    remaining = _remaining_today(request.user)
    return JsonResponse({'response': response_text, 'remaining': remaining})


@login_required
def ami_history(request):
    """Returns the last 20 Ami messages for the current user as JSON."""
    qs = ChatMessage.objects.filter(user=request.user).order_by('created_at')[:20]
    history = [{'message': m.message, 'response': m.response} for m in qs]
    return JsonResponse({'history': history})


@login_required
@require_GET
def ami_quota(request):
    """Returns today's remaining Ami questions for the current user."""
    remaining = _remaining_today(request.user)
    return JsonResponse({
        'remaining': remaining,
        'daily_limit': AMI_DAILY_LIMIT,
        'reset_note': 'Resets ~3–4 pm Malaysia time daily',
    })
