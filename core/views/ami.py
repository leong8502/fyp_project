"""
ami.py – Ami AI chatbox views.

Handles:
  POST /ami/ask/     → keyword/regex NLP, saves to ChatMessage, returns JSON
  GET  /ami/history/ → returns last 20 messages for the current user as JSON
"""
import re
import random
from django.contrib.auth.decorators import login_required  # type: ignore[import-untyped]
from django.views.decorators.http import require_POST  # type: ignore[import-untyped]
from django.http import JsonResponse  # type: ignore[import-untyped]
from django.urls import reverse  # type: ignore[import-untyped]

from core.models import ChatMessage  # type: ignore[import-untyped]


# ---------------------------------------------------------------------------
# Static response banks
# ---------------------------------------------------------------------------

_GREETINGS = [
    "Hi there! I'm Ami, your TalentSync assistant 😊 How can I help you today?",
    "Hello! Great to see you! I'm Ami – ask me anything about TalentSync 🌟",
    "Hey! I'm Ami, here to help you navigate TalentSync. What's on your mind?",
    "Welcome back! I'm Ami 👋 How can I assist you today?",
    "Good to see you! I'm Ami – your personal TalentSync guide. What do you need?",
]

_APOLOGIES = [
    "Hmm, I'm not quite sure I understood that. Could you try rephrasing? 😊",
    "Sorry, I didn't quite catch that. Could you be a bit more specific?",
    "I'm still learning! Could you rephrase your question?",
    "I'm not sure I can help with that directly, but feel free to ask something else!",
    "That one's a bit beyond me right now. Could you try asking differently?",
]


def _link(text: str, url_name: str, *args) -> str:
    """Build an HTML anchor tag for a named URL."""
    try:
        url = reverse(url_name, args=args)
    except Exception:
        url = "#"
    return f'<a href="{url}" style="color:#2e7d32;font-weight:600;">{text}</a>'


# ---------------------------------------------------------------------------
# NLP engine – keyword / regex matching
# ---------------------------------------------------------------------------

def _get_response(message: str, user) -> str:
    """
    Match the user message against known intents and return a helpful reply.
    Detects whether the user is a freelancer or client for role-specific links.
    """
    msg = message.lower().strip()
    is_freelancer = hasattr(user, 'freelancer')
    is_client = hasattr(user, 'client')

    # ── Greetings ─────────────────────────────────────────────────────────
    if re.search(r'\b(hi|hello|hey|good morning|good afternoon|good evening|howdy|hiya|yo)\b', msg):
        name = user.freelancer.full_name or user.username if is_freelancer else (
            user.client.company_name or user.username if is_client else user.username
        )
        name = name.split()[0] if name else user.username
        return f"Hello, {name}! 👋 I'm Ami. How can I help you today?"

    # ── Wallet / balance / top-up / withdraw ─────────────────────────────
    if re.search(r'\b(wallet|balance|top.?up|withdraw|topup|payment|money|fund|earning)\b', msg):
        if is_freelancer:
            return (f"You can check your wallet and balance {_link('here', 'freelancer_wallet')}. "
                    "You can also withdraw your earnings from there!")
        elif is_client:
            return (f"You can manage your wallet and top up {_link('here', 'client_wallet')}.")
        return "Please log in as a freelancer or client to view your wallet."

    # ── Job search (freelancer) ────────────────────────────────────────────
    if re.search(r'\b(find job|search job|browse job|search project|find project|browse project|look for work|job listing|job board|available job|open project)\b', msg):
        if is_freelancer:
            return (f"You can search for open projects {_link('here', 'freelancer_search_job')}. "
                    "Use the search bar to filter by skill, experience level, or keywords!")
        return "Job search is available for freelancer accounts."

    # ── Apply for a job ───────────────────────────────────────────────────
    if re.search(r'\b(apply|how to apply|submit proposal|send proposal|submit application)\b', msg):
        if is_freelancer:
            return (f"To apply for a project, go to {_link('Job Search', 'freelancer_search_job')}, "
                    "find a project you like, and click <strong>Apply Now</strong>.")
        return "Applications are sent by freelancers. Switch to a freelancer account to apply."

    # ── Track / current / ongoing projects (freelancer) ───────────────────
    if re.search(r'\b(track|ongoing|current job|current project|my project|active project|project status|in.?progress)\b', msg):
        if is_freelancer:
            return (f"You can track your ongoing projects {_link('here', 'freelancer_track_project')}. "
                    "You'll also find pending applications and completed jobs there.")
        elif is_client:
            return (f"View and manage all your projects {_link('here', 'client_project')}.")

    # ── Proposals / applications received (client) ────────────────────────
    if re.search(r'\b(proposal|application|applicant|who applied|see applicant)\b', msg):
        if is_client:
            return (f"You can view all proposals received on your project pages {_link('here', 'client_project')}. "
                    "Click a project to see its applicants.")
        elif is_freelancer:
            return (f"You can check the status of your applications {_link('here', 'freelancer_track_project')} "
                    "under the 'Pending Applications' tab.")

    # ── Create / post a project (client) ──────────────────────────────────
    if re.search(r'\b(post project|create project|new project|add project|publish project|hire freelancer|hire someone)\b', msg):
        if is_client:
            return (f"You can post a new project {_link('here', 'client_projectCreate')}. "
                    "Fill in the details, set the budget and milestones, and publish!")
        return "Posting projects is available for client accounts."

    # ── Profile ───────────────────────────────────────────────────────────
    if re.search(r'\b(my profile|view profile|edit profile|profile page|update profile|profile setting)\b', msg):
        if is_freelancer:
            return (f"View and edit your freelancer profile {_link('here', 'freelancer_profile')}. "
                    "You can update your bio, skills, rates, portfolio, and more!")
        elif is_client:
            return (f"View and edit your company profile {_link('here', 'client_profile')}.")

    # ── Messages / inbox / chat ───────────────────────────────────────────
    if re.search(r'\b(message|inbox|chat with|dm|direct message|send message|conversation)\b', msg):
        return (f"You can access your messages and conversations {_link('here', 'chat')}. "
                "Click any conversation to continue chatting!")

    # ── Notifications ─────────────────────────────────────────────────────
    if re.search(r'\b(notification|alert|update|unread|bell)\b', msg):
        return (f"Check all your notifications {_link('here', 'notifications')}. "
                "You can mark them all as read from there too.")

    # ── Settings / PIN / security / password ──────────────────────────────
    if re.search(r'\b(setting|account setting|security|pin|secure pin|change pin|change password|password)\b', msg):
        if is_freelancer:
            return (f"Go to {_link('Settings', 'freelancer_settings')} to change your secure PIN. "
                    f"To reset your password, use the {_link('password reset page', 'password_reset')}.")
        elif is_client:
            return (f"Go to {_link('Settings', 'client_settings')} to manage your account. "
                    f"To reset your password, use the {_link('password reset page', 'password_reset')}.")
        return (f"You can reset your password {_link('here', 'password_reset')}.")

    # ── Forgot / reset password ───────────────────────────────────────────
    if re.search(r'\b(forgot password|reset password|lost password|can\'t login|cant login)\b', msg):
        return (f"No worries! You can reset your password {_link('here', 'password_reset')}. "
                "Enter your email and follow the instructions sent to your inbox.")

    # ── Support / help / contact / report / issue ─────────────────────────
    if re.search(r'\b(support|help|contact|report|issue|problem|complaint|bug|ticket)\b', msg):
        if is_client:
            return (f"You can submit a support ticket {_link('here', 'client_support')}. "
                    "Our team will get back to you as soon as possible!")
        elif is_freelancer:
            return (f"You can browse our {_link('About page', 'about')} or contact support through the platform. "
                    "If you have a specific project issue, your client can help resolve it too.")
        return f"Visit our {_link('About page', 'about')} to learn more or find contact options."

    # ── About / platform info ─────────────────────────────────────────────
    if re.search(r'\b(about|talentsync|platform|what is this|what is talentsync|platform info)\b', msg):
        return (f"TalentSync is a freelance marketplace connecting talented freelancers with clients. "
                f"Learn more on the {_link('About page', 'about')}!")

    # ── Logout / sign out ─────────────────────────────────────────────────
    if re.search(r'\b(logout|log out|sign out|signout)\b', msg):
        return (f"You can log out safely by clicking {_link('here', 'logout')}. "
                "See you next time! 👋")

    # ── Completed jobs / history ───────────────────────────────────────────
    if re.search(r'\b(completed job|finished project|past project|job history|done project|completed project)\b', msg):
        if is_freelancer:
            return (f"You can view your completed projects {_link('here', 'freelancer_track_project')}. "
                    "Switch to the 'Completed' tab to see them all.")
        elif is_client:
            return (f"Your completed projects are listed {_link('here', 'client_project')}.")

    # ── Client search for freelancers ─────────────────────────────────────
    if re.search(r'\b(find freelancer|search freelancer|hire|browse freelancer|look for freelancer)\b', msg):
        if is_client:
            return (f"You can search for freelancers {_link('here', 'client_search')}. "
                    "Filter by skills, ratings, and experience level!")
        return "Searching for freelancers is available for client accounts."

    # ── Unknown ───────────────────────────────────────────────────────────
    return random.choice(_APOLOGIES)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

@login_required
@require_POST
def chat_ami(request):
    """AJAX endpoint – receives a message, returns Ami's response as JSON."""
    message = request.POST.get('message', '').strip()
    if not message:
        return JsonResponse({'response': "Please type a message first! 😊"})

    response = _get_response(message, request.user)

    # Persist to DB
    ChatMessage.objects.create(
        user=request.user,
        message=message,
        response=response,
    )

    return JsonResponse({'response': response})


@login_required
def ami_history(request):
    """Returns the last 20 Ami messages for the current user as JSON."""
    messages_qs = ChatMessage.objects.filter(user=request.user).order_by('created_at')[:20]
    history = [
        {'message': m.message, 'response': m.response}
        for m in messages_qs
    ]
    return JsonResponse({'history': history})
