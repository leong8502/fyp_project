"""
Freelancer views – home, job search, project tracking, wallet, profile, settings.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.utils import timezone

from core.decorators import freelancer_required
from core.models import (
    Project, ProjectApplication, Review, Wallet, Transaction,
    UserSecurity, Milestone, MilestoneAttachment, CancellationRequest,
    Ticket, MatchScore
)
from core.ai_utils import get_recommendations, AISearchManager
from django.db.models import Sum, Count, Q
from django.db.models.functions import ExtractYear
import json
from decimal import Decimal
import random
from django.core.mail import send_mail, get_connection
from django.http import JsonResponse
from core.forms import (
    SecurePinForm,
    FreelancerProfileForm, FreelancerPortfolioForm, FreelancerWorkExperienceForm,
    FreelancerCertificationForm, FreelancerHeaderForm, FreelancerRateForm,
    FreelancerBackgroundForm, FreelancerSocialForm, FreelancerBioForm,
    FreelancerSkillsForm, FreelancerLanguageForm, SupportForm,
)
from core.services.project_service import ProjectService



# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------

@freelancer_required
def freelancer_home(request):
    freelancer = request.user.freelancer
    recommendations = get_recommendations(freelancer, limit=4)
    return render(request, 'core/freelancer_home.html', {'recommendations': recommendations})


# ---------------------------------------------------------------------------
# Job search
# ---------------------------------------------------------------------------

@freelancer_required
def freelancer_search_job(request):
    query = request.GET.get('q', '').strip()
    freelancer = request.user.freelancer

    # Threshold: user-adjustable, default 20%, range 5-100
    try:
        threshold = int(request.GET.get('threshold', 20))
        threshold = max(5, min(100, threshold))
    except (ValueError, TypeError):
        threshold = 20

    # Instantiate the manager
    manager = AISearchManager()

    # Use the new detailed method
    projects_qs = Project.objects.filter(
        status__in=['open', 'in_progress']
    ).select_related('client').prefetch_related('milestones').annotate(
        accepted_freelancers_count=Count('applications', filter=Q(applications__status='accepted'))
    )

    details = manager.calculate_match_details(
        projects_qs,
        freelancer=freelancer, query=query
    )

    # Sort descending by score
    details.sort(key=lambda d: d['score'], reverse=True)

    # Filter by threshold and attach skills_list
    matched = []
    for d in details:
        project = d['project']
        score   = d['score']

        # Always attach skills_list for template rendering
        project.skills_list = [s.strip() for s in (project.required_skills or '').split(',') if s.strip()]

        # Check if project can accept more freelancers
        can_apply = False
        if project.status == 'open':
            can_apply = True
        elif project.status == 'in_progress':
            accepted_count = project.applications.filter(status='accepted').count()
            if accepted_count < project.max_freelancers:
                can_apply = True

        if score >= threshold and can_apply:
            matched.append(d)

        # Persist / update MatchScore in DB (only for meaningful scores)
        if score > 0:
            try:
                MatchScore.objects.update_or_create(
                    freelancer=freelancer,
                    project=project,
                    defaults={
                        'score': score,
                        'calculation_logic': d['calculation_logic'],
                        'suitability_sentence': d['suitability_sentence'],
                    }
                )
            except Exception:
                pass

    return render(request, 'core/freelancer_searchJob.html', {
        'query':             query,
        'threshold':         threshold,
        'matched':           matched,
        'threshold_choices': [5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100],
    })


# ---------------------------------------------------------------------------
# Project tracking
# ---------------------------------------------------------------------------

@freelancer_required
def freelancer_track_project(request):
    """Freelancer's project tracking page."""
    freelancer = request.user.freelancer
    
    current_projects = Project.objects.filter(
        applications__freelancer=freelancer,
        applications__status='accepted',
        status__in=['open', 'in_progress', 'reviewing']
    ).prefetch_related('milestones').distinct()
    
    pass_projects = Project.objects.filter(
        applications__freelancer=freelancer,
        applications__status='accepted',
        status__in=['completed', 'cancelled']
    ).distinct()

    for project in pass_projects:
        project.has_reviewed = Review.objects.filter(project=project, reviewer=request.user).exists()

    pending_applications = ProjectApplication.objects.filter(
        freelancer=freelancer, status='pending'
    ).order_by('-created_at')

    # Attach pending cancellation request addressed to THIS freelancer
    pending_cancellations = CancellationRequest.objects.filter(
        freelancer=freelancer,
        status='pending'
    ).select_related('project')
    
    pending_cancellation_map = {cr.project_id: cr for cr in pending_cancellations}
    for project in current_projects:
        project.pending_cancellation = pending_cancellation_map.get(project.id)

    return render(request, 'core/freelancer_trackProject.html', {
        'current_projects': current_projects,
        'pass_projects': pass_projects,
        'pending_applications': pending_applications,
        'active_tab': request.GET.get('tab', 'current'),
    })


@freelancer_required
def freelancer_respond_cancellation(request, cancellation_id):
    """Freelancer responds to a cancellation request: agree or decline."""
    cancellation_req = get_object_or_404(
        CancellationRequest,
        id=cancellation_id,
        freelancer=request.user.freelancer,
        status='pending'
    )
    project = cancellation_req.project

    if request.method == 'POST':
        response = request.POST.get('response')
        if response == 'agree':
            try:
                ProjectService.confirm_cancellation(cancellation_req, request.user)
                messages.success(
                    request,
                    f"You agreed to cancel project '{project.title}'. The client's remaining escrow has been refunded."
                )
            except Exception as e:
                messages.error(request, f"Error processing cancellation: {str(e)}")
        elif response == 'decline':
            try:
                ProjectService.decline_cancellation(cancellation_req, request.user)
                messages.info(
                    request,
                    f"You declined the cancellation request for '{project.title}'. The project continues."
                )
            except Exception as e:
                messages.error(request, f"Error processing decline: {str(e)}")
        else:
            messages.error(request, "Invalid response.")

    return redirect('freelancer_track_project')


@freelancer_required
def freelancer_apply_project(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    
    can_apply = False
    if project.status == 'open':
        can_apply = True
    elif project.status == 'in_progress':
        accepted_count = project.applications.filter(status='accepted').count()
        if accepted_count < project.max_freelancers:
            can_apply = True

    if not can_apply:
        messages.error(request, "This project is no longer accepting applications.")
        return redirect('freelancer_search_job')

    if request.method == 'POST':
        message = request.POST.get('message', '')
        attachment = request.FILES.get('attachment')

        application = ProjectApplication.objects.filter(
            project=project, freelancer=request.user.freelancer
        ).first()

        if application:
            if application.status in ['pending', 'accepted']:
                messages.error(request, "You have already applied or been invited to this project.")
                return redirect('freelancer_search_job')
            application.status = 'pending'
            application.message = message
            application.application_type = 'apply'
            if attachment:
                application.attachment = attachment
            application.save()
        else:
            application = ProjectApplication.objects.create(
                project=project,
                freelancer=request.user.freelancer,
                application_type='apply',
                message=message,
                attachment=attachment,
            )

        from core.services import NotificationService
        NotificationService.create_notification(
            recipient=project.client.user,
            notification_type='proposal_received',
            title='New Proposal Received',
            message=f"Freelancer {request.user.freelancer.full_name or request.user.username} has applied for your project '{project.title}'.",
            link=reverse('client_projectInfo', kwargs={'project_id': project.id})
        )

        messages.success(request, "Application sent successfully!")
        return redirect('freelancer_track_project')

    return redirect('freelancer_search_job')


@freelancer_required
def freelancer_submit_milestone(request, milestone_id):
    milestone = get_object_or_404(
        Milestone, id=milestone_id, assigned_to=request.user.freelancer
    )
    if milestone.status != 'in_progress':
        messages.error(request, "Milestone must be in progress to submit.")
        return redirect('freelancer_track_project')

    if request.method == 'POST':
        files = request.FILES.getlist('attachments')
        if not files and milestone.attachments.count() == 0:
            messages.error(request, "Please upload at least one file to submit the milestone.")
            return redirect('freelancer_track_project')

        ProjectService.submit_milestone(milestone, files, request.user)
        messages.success(request, "Milestone submitted successfully! Waiting for client approval.")

    return redirect('freelancer_track_project')


# ---------------------------------------------------------------------------
# Support
# ---------------------------------------------------------------------------

@freelancer_required
def freelancer_support(request):
    if request.method == 'POST':
        form = SupportForm(request.POST, user=request.user)
        if form.is_valid():
            Ticket.objects.create(
                user=request.user,
                title=form.cleaned_data['title'],
                category=form.cleaned_data['category'],
                description=form.cleaned_data['description'],
                status='open'
            )
            messages.success(request, "Your support ticket has been submitted. We will get back to you soon!")
            return redirect('freelancer_support')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = SupportForm(user=request.user)

    user_tickets = Ticket.objects.filter(user=request.user).order_by('-created_at')

    return render(request, 'core/freelancer_support.html', {
        'form': form,
        'user_tickets': user_tickets
    })


# ---------------------------------------------------------------------------
# Wallet
# ---------------------------------------------------------------------------

@freelancer_required
def freelancer_wallet(request):
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    recent_transactions = Transaction.objects.filter(wallet=wallet).order_by('-created_at')[:5]
    return render(request, 'core/freelancer_wallet.html', {
        'wallet': wallet,
        'recent_transactions': recent_transactions,
    })


@freelancer_required
def freelancer_performance(request):
    freelancer = request.user.freelancer
    wallet, _ = Wallet.objects.get_or_create(user=request.user)

    # Card Year filter (independent of graph year)
    now      = timezone.now()
    all_txns = Transaction.objects.filter(wallet=wallet, status='completed')
    card_year = request.GET.get('card_year', str(now.year))

    # Card Metrics — filtered by card_year
    card_txns        = all_txns.filter(created_at__year=card_year)
    total_topup      = card_txns.filter(transaction_type='top_up').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    total_withdrawal = card_txns.filter(transaction_type='withdrawal').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    total_income     = card_txns.filter(transaction_type='payout', direction='credit').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

    # Graph / Skill-table Period Selection
    selected_year  = request.GET.get('year', str(now.year))
    selected_month = request.GET.get('month', '')

    txn_years = set(all_txns.annotate(y=ExtractYear('created_at')).values_list('y', flat=True))
    range_years = set(range(now.year - 3, now.year + 2))
    year_list = sorted(txn_years | range_years, reverse=True)

    if selected_month:
        graph_labels = ['Week 1', 'Week 2', 'Week 3', 'Week 4+']
        week_ranges  = [(1, 7), (8, 14), (15, 21), (22, 31)]
        period_type  = 'weekly'
    else:
        graph_labels = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
        period_type  = 'monthly'

    n = len(graph_labels)

    # Transactions in selected period
    period_txns = all_txns.filter(created_at__year=selected_year)
    if selected_month:
        period_txns = period_txns.filter(created_at__month=int(selected_month))

    # Collect all unique skills for colour consistency
    income_txns_all = all_txns.filter(
        transaction_type='payout', direction='credit'
    ).select_related('related_milestone__project')

    PALETTE = ['#22d3ee','#f59e0b','#3b82f6','#f97316','#8b5cf6','#ec4899','#10b981','#6366f1']
    all_skills = []
    for txn in income_txns_all:
        if txn.related_milestone:
            for s in (txn.related_milestone.project.required_skills or '').split(','):
                s = s.strip()
                if s and s not in all_skills:
                    all_skills.append(s)
    skill_color = {sk: PALETTE[i % len(PALETTE)] for i, sk in enumerate(all_skills)}

    # Per-period aggregation
    # Initialise to 0.0 so past periods with no activity stay at zero (line connects).
    # Future periods will be overwritten to None so Chart.js draws no point there.
    data_topup     = [0.0] * n
    data_withdrawn = [0.0] * n
    skill_amt  = {sk: [0.0] * n for sk in all_skills}
    skill_tips = {sk: [[] for _ in range(n)] for sk in all_skills}

    # Helper: is this period entirely in the future?
    yr = int(selected_year)
    def is_future_period(month_num=None, week_start_day=None):
        if yr > now.year:
            return True
        if yr < now.year:
            return False
        # Same year
        if period_type == 'monthly':
            return month_num > now.month
        else:  # weekly
            sm = int(selected_month)
            if sm > now.month:
                return True
            if sm < now.month:
                return False
            return week_start_day > now.day

    def process_period(idx, p_txns):
        tu = p_txns.filter(transaction_type='top_up').aggregate(s=Sum('amount'))['s'] or 0
        wd = p_txns.filter(transaction_type='withdrawal').aggregate(s=Sum('amount'))['s'] or 0
        data_topup[idx]     = float(tu)
        data_withdrawn[idx] = float(wd)
        for txn in p_txns.filter(transaction_type='payout', direction='credit').select_related('related_milestone__project'):
            if not txn.related_milestone:
                continue
            ms     = txn.related_milestone
            skills = [x.strip() for x in (ms.project.required_skills or '').split(',') if x.strip()]
            n_s    = len(skills) or 1
            per    = float(txn.amount) / n_s
            for sk in skills:
                if sk in all_skills:
                    skill_amt[sk][idx] += per
                    skill_tips[sk][idx].append({
                        'project': ms.project.title,
                        'milestone': ms.title,
                        'amount': round(per, 2)
                    })

    if period_type == 'weekly':
        for i, (sd, ed) in enumerate(week_ranges):
            if is_future_period(week_start_day=sd):
                # Mark future — no point drawn
                data_topup[i] = None
                data_withdrawn[i] = None
                for sk in all_skills:
                    skill_amt[sk][i] = None
            else:
                process_period(i, period_txns.filter(created_at__day__range=(sd, ed)))
    else:
        for i, m in enumerate(range(1, 13)):
            if is_future_period(month_num=m):
                data_topup[i] = None
                data_withdrawn[i] = None
                for sk in all_skills:
                    skill_amt[sk][i] = None
            else:
                process_period(i, period_txns.filter(created_at__month=m))

    for sk in all_skills:
        skill_amt[sk] = [round(v, 2) if v is not None else None for v in skill_amt[sk]]

    # Running Balance — None for future periods
    pre_txns = all_txns.filter(created_at__year__lt=int(selected_year))
    if selected_month:
        pre_txns = pre_txns | all_txns.filter(
            created_at__year=selected_year, created_at__month__lt=int(selected_month))
    running = Decimal('0.00')
    for t in pre_txns:
        running += t.amount if t.direction == 'credit' else -t.amount

    data_balance = []
    if period_type == 'weekly':
        for sd, ed in week_ranges:
            if is_future_period(week_start_day=sd):
                data_balance.append(None)
            else:
                for t in period_txns.filter(created_at__day__range=(sd, ed)).order_by('created_at'):
                    running += t.amount if t.direction == 'credit' else -t.amount
                data_balance.append(round(float(running), 2))
    else:
        for m in range(1, 13):
            if is_future_period(month_num=m):
                data_balance.append(None)
            else:
                for t in period_txns.filter(created_at__month=m).order_by('created_at'):
                    running += t.amount if t.direction == 'credit' else -t.amount
                data_balance.append(round(float(running), 2))

    # Build Chart.js datasets — spanGaps:false so nulls create real gaps
    datasets = [
        {'label':'Total Wallet','data':data_balance,'borderColor':'#a855f7',
         'backgroundColor':'rgba(168,85,247,0.08)','borderWidth':2.5,'fill':True,
         'tension':0.4,'pointRadius':4,'pointHoverRadius':7,'dtype':'balance','spanGaps':False,
         'tooltipData':[({'amount':v} if v is not None else None) for v in data_balance]},
        {'label':'Top-up','data':data_topup,'borderColor':'#22c55e',
         'backgroundColor':'transparent','borderWidth':2.5,'borderDash':[5,5],
         'fill':False,'tension':0.4,'pointRadius':4,'pointHoverRadius':7,'dtype':'topup','spanGaps':False,
         'tooltipData':[({'amount':v} if v is not None else None) for v in data_topup]},
        {'label':'Withdrawn','data':data_withdrawn,'borderColor':'#ef4444',
         'backgroundColor':'transparent','borderWidth':2.5,'borderDash':[5,5],
         'fill':False,'tension':0.4,'pointRadius':4,'pointHoverRadius':7,'dtype':'withdrawn','spanGaps':False,
         'tooltipData':[({'amount':v} if v is not None else None) for v in data_withdrawn]},
    ]
    for sk in all_skills:
        datasets.append({
            'label':sk,'data':skill_amt[sk],'borderColor':skill_color[sk],
            'backgroundColor':'transparent','borderWidth':2.5,'fill':False,
            'tension':0.4,'pointRadius':5,'pointHoverRadius':8,'spanGaps':False,
            'dtype':'income','skill':sk,'tooltipData':skill_tips[sk],
        })

    # Skill table — filtered by graph's selected_year
    income_txns_year = income_txns_all.filter(created_at__year=selected_year)
    total_ms_income_year = float(
        income_txns_year.aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    ) or 1.0
    sk_totals_year     = {sk: 0.0 for sk in all_skills}
    sk_milestones_year = {sk: [] for sk in all_skills}
    for txn in income_txns_year:
        if not txn.related_milestone:
            continue
        ms     = txn.related_milestone
        skills = [x.strip() for x in (ms.project.required_skills or '').split(',') if x.strip()]
        n_s    = len(skills) or 1
        per    = float(txn.amount) / n_s
        for sk in skills:
            if sk in all_skills:
                sk_totals_year[sk] += per
                sk_milestones_year[sk].append({
                    'project': ms.project.title,
                    'milestone': ms.title,
                    'amount': round(per, 2)
                })

    skill_table = []
    for sk in all_skills:
        if sk_totals_year[sk] == 0.0:
            continue  # skip skills with no income this year
        pct = (sk_totals_year[sk] / total_ms_income_year) * 100
        skill_table.append({
            'skill':      sk,
            'color':      skill_color[sk],
            'total':      round(sk_totals_year[sk], 2),
            'percent':    round(pct, 2),
            'milestones': sk_milestones_year[sk],
        })

    # Income card mini-skill breakdown — filtered by card_year
    income_txns_card = income_txns_all.filter(created_at__year=card_year)
    total_card_income_f = float(
        income_txns_card.aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    ) or 1.0
    sk_totals_card = {sk: 0.0 for sk in all_skills}
    for txn in income_txns_card:
        if not txn.related_milestone:
            continue
        ms     = txn.related_milestone
        skills = [x.strip() for x in (ms.project.required_skills or '').split(',') if x.strip()]
        n_s    = len(skills) or 1
        per    = float(txn.amount) / n_s
        for sk in skills:
            if sk in all_skills:
                sk_totals_card[sk] += per

    card_skill_table = []
    for sk in all_skills:
        if sk_totals_card[sk] == 0.0:
            continue
        card_skill_table.append({
            'skill':   sk,
            'color':   skill_color[sk],
            'percent': round((sk_totals_card[sk] / total_card_income_f) * 100, 2),
        })

    context = {
        'wallet_balance':    wallet.balance,
        'total_topup':       total_topup,
        'total_withdrawal':  total_withdrawal,
        'total_income':      total_income,
        'card_year':         card_year,
        'card_skill_table':  card_skill_table,
        'selected_year':     selected_year,
        'selected_month':    str(selected_month),
        'year_list':         year_list,
        'graph_labels_json': json.dumps(graph_labels),
        'datasets_json':     json.dumps(datasets),
        'skill_table':       skill_table,
        'all_skills':        all_skills,
        'all_skills_info':   [{'skill': sk, 'color': skill_color[sk]} for sk in all_skills],
        'skill_color':       skill_color,
    }
    return render(request, 'core/freelancer_performance.html', context)


@freelancer_required
def freelancer_transaction(request):
    from django.core.paginator import Paginator
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    page_obj = None

    if wallet:
        qs = Transaction.objects.filter(wallet=wallet)

        filter_type = request.GET.get('type')
        if filter_type == 'income':
            qs = qs.filter(transaction_type__in=['payment', 'payout'])
        elif filter_type in ['top_up', 'withdrawal']:
            qs = qs.filter(transaction_type=filter_type)

        sort_by = request.GET.get('sort', 'newest')
        if sort_by == 'oldest':
            qs = qs.order_by('created_at')
        elif sort_by == 'highest':
            qs = qs.order_by('-amount')
        else:
            qs = qs.order_by('-created_at')

        paginator = Paginator(qs, 8)
        page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'core/freelancer_transaction.html', {
        'wallet': wallet,
        'transactions': page_obj,
        'page_obj': page_obj,
        'current_type': request.GET.get('type', ''),
        'current_sort': request.GET.get('sort', 'newest'),
    })


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@freelancer_required
def freelancer_settings(request):
    user_security, _ = UserSecurity.objects.get_or_create(user=request.user)
    is_verified_otp = request.session.get('pin_reset_verified', False)

    if request.method == 'POST':
        form = SecurePinForm(request.POST, user_security=user_security, is_verified_otp=is_verified_otp)
        if form.is_valid():
            user_security.secure_pin = make_password(form.cleaned_data['new_pin'])
            user_security.save()
            # Clear verified flag upon successful save
            if 'pin_reset_verified' in request.session:
                del request.session['pin_reset_verified']
            messages.success(request, "Secure PIN updated successfully.")
            return redirect('freelancer_settings')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = SecurePinForm(user_security=user_security, is_verified_otp=is_verified_otp)

    return render(request, 'core/freelancer_settings.html', {'form': form, 'is_verified_otp': is_verified_otp})

@freelancer_required
def api_request_pin_otp(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method.'})
    
    otp = f"{random.randint(0, 999999):06d}"
    
    request.session['pin_reset_otp'] = otp
    request.session['pin_reset_expires'] = (timezone.now() + timezone.timedelta(minutes=5)).timestamp()
    
    # Custom connection config to use gunyx-wp22@student.tarc.edu.my
    try:
        connection = get_connection(
            backend='django.core.mail.backends.smtp.EmailBackend',
            host='smtp.gmail.com',
            port=587,
            use_tls=True,
            username='gunyx-wp22@student.tarc.edu.my',
            password='xdji yfoq izud sysy',
        )
        
        send_mail(
            subject='TalentSync - Your PIN Reset OTP',
            message=f'Your OTP for resetting your Secure PIN is: {otp}. It will expire in 5 minutes.',
            from_email='gunyx-wp22@student.tarc.edu.my',
            recipient_list=[request.user.email],
            connection=connection,
            fail_silently=False,
        )
        return JsonResponse({'success': True, 'message': 'OTP sent successfully to your email.'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error sending email: {str(e)}'})

@freelancer_required
def api_verify_pin_otp(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method.'})
    
    try:
        data = json.loads(request.body)
        submitted_otp = data.get('otp', '').strip()
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid data.'})

    session_otp = request.session.get('pin_reset_otp')
    expires = request.session.get('pin_reset_expires')

    if not session_otp or not expires:
        return JsonResponse({'success': False, 'message': 'OTP has expired or was not requested.'})

    if timezone.now().timestamp() > expires:
        return JsonResponse({'success': False, 'message': 'OTP has expired. Please request a new one.'})

    if submitted_otp == session_otp:
        request.session['pin_reset_verified'] = True
        # Clear the old OTP
        del request.session['pin_reset_otp']
        del request.session['pin_reset_expires']
        return JsonResponse({'success': True, 'message': 'OTP verified successfully.'})
    else:
        return JsonResponse({'success': False, 'message': 'Invalid OTP.'})


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@freelancer_required
def freelancer_profile(request):
    freelancer = request.user.freelancer

    portfolios = freelancer.portfolios.all().order_by('-created_at')
    work_experiences = freelancer.work_experiences.all().order_by('-start_date')
    certifications = freelancer.certifications.all().order_by('-issue_date')
    languages = freelancer.languages.all()
    completed_projects = Project.objects.filter(
        applications__freelancer=freelancer, applications__status='accepted', status='completed'
    ).order_by('-created_at').distinct()
    reviews = Review.objects.filter(reviewee=freelancer.user, is_hidden=False).order_by('-created_at')

    # Attach reviews to completed projects for the template
    review_map = {r.project_id: r for r in reviews}
    for project in completed_projects:
        project.review = review_map.get(project.id)

    # Forms
    header_form = FreelancerHeaderForm(instance=freelancer)
    rate_form = FreelancerRateForm(instance=freelancer)
    background_form = FreelancerBackgroundForm(instance=freelancer)
    social_form = FreelancerSocialForm(instance=freelancer)
    bio_form = FreelancerBioForm(instance=freelancer)
    skills_form = FreelancerSkillsForm(instance=freelancer)
    profile_for_view = FreelancerProfileForm(instance=freelancer)
    portfolio_form = FreelancerPortfolioForm()
    work_exp_form = FreelancerWorkExperienceForm()
    cert_form = FreelancerCertificationForm()
    language_form = FreelancerLanguageForm()

    if request.method == 'POST':
        if 'update_avatar_direct' in request.POST:
            if 'profile_image' in request.FILES:
                freelancer.profile_image = request.FILES['profile_image']
                freelancer.save()
                messages.success(request, "Profile picture updated!")
            else:
                messages.error(request, "No image selected.")
            return redirect('freelancer_profile')

        elif 'update_header' in request.POST:
            header_form = FreelancerHeaderForm(request.POST, instance=freelancer)
            if header_form.is_valid():
                header_form.save()
                messages.success(request, "Header info updated!")
                return redirect('freelancer_profile')

        elif 'update_rate' in request.POST:
            rate_form = FreelancerRateForm(request.POST, instance=freelancer)
            if rate_form.is_valid():
                rate_form.save()
                messages.success(request, "Rate & availability updated!")
                return redirect('freelancer_profile')

        elif 'update_background' in request.POST:
            if 'background_image' in request.FILES:
                freelancer.background_image = request.FILES['background_image']
                freelancer.save()
                messages.success(request, "Background image updated!")
            else:
                messages.error(request, "No background image selected.")
            return redirect('freelancer_profile')

        elif 'update_bio' in request.POST:
            bio_form = FreelancerBioForm(request.POST, instance=freelancer)
            if bio_form.is_valid():
                bio_form.save()
                messages.success(request, "Bio updated!")
                return redirect('freelancer_profile')
            else:
                messages.error(request, "Error updating bio.")

        elif 'update_skills' in request.POST:
            skills_form = FreelancerSkillsForm(request.POST, instance=freelancer)
            if skills_form.is_valid():
                skills_form.save()
                messages.success(request, "Skills updated!")
                return redirect('freelancer_profile')
            else:
                messages.error(request, "Error updating skills.")

        elif 'update_profile' in request.POST:
            profile_form = FreelancerProfileForm(request.POST, request.FILES, instance=freelancer)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profile updated successfully!")
                return redirect('freelancer_profile')
            else:
                messages.error(request, "Error updating profile.")

        elif 'add_portfolio' in request.POST:
            portfolio_form = FreelancerPortfolioForm(request.POST, request.FILES)
            if portfolio_form.is_valid():
                portfolio = portfolio_form.save(commit=False)
                portfolio.freelancer = freelancer
                portfolio.save()
                messages.success(request, "Portfolio item added!")
                return redirect('freelancer_profile')
            else:
                messages.error(request, "Error adding portfolio.")

        elif 'add_work_exp' in request.POST:
            work_exp_form = FreelancerWorkExperienceForm(request.POST)
            if work_exp_form.is_valid():
                exp = work_exp_form.save(commit=False)
                exp.freelancer = freelancer
                exp.save()
                messages.success(request, "Work experience added!")
                return redirect('freelancer_profile')
            else:
                messages.error(request, "Error adding work experience.")

        elif 'add_cert' in request.POST:
            cert_form = FreelancerCertificationForm(request.POST, request.FILES)
            if cert_form.is_valid():
                cert = cert_form.save(commit=False)
                cert.freelancer = freelancer
                if cert.certificate_file.name.lower().endswith('.pdf'):
                    cert.is_verified = True
                    cert.verification_date = timezone.now()
                cert.save()
                messages.success(request, "Certification added!")
                return redirect('freelancer_profile')
            else:
                messages.error(request, "Error adding certification.")

        elif 'add_language' in request.POST:
            language_form = FreelancerLanguageForm(request.POST)
            if language_form.is_valid():
                lang = language_form.save(commit=False)
                lang.freelancer = freelancer
                lang.save()
                messages.success(request, "Language added!")
                return redirect('freelancer_profile')
            else:
                messages.error(request, "Error adding language.")

    return render(request, 'core/freelancer_profile.html', {
        'freelancer': freelancer,
        'portfolios': portfolios,
        'work_experiences': work_experiences,
        'certifications': certifications,
        'completed_projects': completed_projects,
        'is_owner': True,
        'header_form': header_form,
        'rate_form': rate_form,
        'background_form': background_form,
        'social_form': social_form,
        'bio_form': bio_form,
        'skills_form': skills_form,
        'profile_form': profile_for_view,
        'portfolio_form': portfolio_form,
        'work_exp_form': work_exp_form,
        'cert_form': cert_form,
        'language_form': language_form,
        'languages': languages,
    })


# ---------------------------------------------------------------------------
# Company Profile (read-only view for freelancer to view a client's profile)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Resume Upload / View / Delete
# ---------------------------------------------------------------------------

@freelancer_required
def freelancer_upload_resume(request):
    """Handle resume file upload and AI-powered data extraction."""
    if request.method != 'POST':
        return redirect('freelancer_profile')

    freelancer = request.user.freelancer
    uploaded_file = request.FILES.get('resume_file')

    if not uploaded_file:
        messages.error(request, "No file selected. Please choose a PDF or image file.")
        return redirect('freelancer_profile')

    # Validate file type
    allowed_types = ['application/pdf', 'image/jpeg', 'image/png', 'image/webp']
    content_type = uploaded_file.content_type
    if content_type not in allowed_types:
        messages.error(request, "Invalid file type. Please upload a PDF, JPEG, PNG, or WebP file.")
        return redirect('freelancer_profile')

    # Validate file size (max 10 MB)
    if uploaded_file.size > 10 * 1024 * 1024:
        messages.error(request, "File too large. Maximum size is 10 MB.")
        return redirect('freelancer_profile')

    # Delete old resume file if one exists
    if freelancer.resume:
        try:
            import os
            if os.path.isfile(freelancer.resume.path):
                os.remove(freelancer.resume.path)
        except Exception:
            pass

    # Save the new resume file
    freelancer.resume = uploaded_file
    freelancer.save(update_fields=['resume'])

    # Call Gemini AI to extract resume data
    try:
        import os
        from core.ai_utils import extract_resume_data
        from core.models import FreelancerLanguage, FreelancerWorkExperience
        import datetime

        file_path = freelancer.resume.path
        extracted = extract_resume_data(file_path)

        # --- Skills ---
        new_skills = extracted.get('skills', [])
        if new_skills:
            existing_skills = [s.strip().lower() for s in (freelancer.skills or '').split(',') if s.strip()]
            added_skills = []
            for sk in new_skills:
                if sk.strip().lower() not in existing_skills:
                    added_skills.append(sk.strip())

            if added_skills:
                current = freelancer.skills.strip().rstrip(',') if freelancer.skills else ''
                freelancer.skills = (current + ', ' + ', '.join(added_skills)).strip().strip(',')
                # Track which skills were added by this resume
                freelancer.resume_skills = ', '.join(added_skills)
            else:
                freelancer.resume_skills = ''
            freelancer.save(update_fields=['skills', 'resume_skills'])

        # --- Languages ---
        # Remove previously AI-added languages first, then add fresh ones
        FreelancerLanguage.objects.filter(freelancer=freelancer, is_from_resume=True).delete()
        for lang_data in extracted.get('languages', []):
            lang_name = lang_data.get('language', '').strip()
            if not lang_name:
                continue
            # Skip if this language already exists manually
            if not FreelancerLanguage.objects.filter(
                freelancer=freelancer, language__iexact=lang_name, is_from_resume=False
            ).exists():
                FreelancerLanguage.objects.create(
                    freelancer=freelancer,
                    language=lang_name,
                    proficiency=lang_data.get('proficiency', 'Basic'),
                    is_from_resume=True,
                )

        # --- Work Experiences ---
        # Remove previously AI-added work experiences, then add fresh ones
        FreelancerWorkExperience.objects.filter(freelancer=freelancer, is_from_resume=True).delete()
        for exp_data in extracted.get('work_experiences', []):
            company   = exp_data.get('company', '').strip()
            job_title = exp_data.get('job_title', '').strip()
            if not company or not job_title:
                continue

            start_str = exp_data.get('start_date')
            end_str   = exp_data.get('end_date')

            def parse_iso(val):
                if not val:
                    return None
                try:
                    return datetime.date.fromisoformat(str(val))
                except Exception:
                    return None

            FreelancerWorkExperience.objects.create(
                freelancer=freelancer,
                company=company,
                job_title=job_title,
                description=exp_data.get('description', ''),
                start_date=parse_iso(start_str) or datetime.date(2000, 1, 1),
                end_date=parse_iso(end_str),
                is_current=bool(exp_data.get('is_current', False)),
                is_from_resume=True,
            )

        messages.success(
            request,
            f"Resume uploaded and parsed successfully! "
            f"Added {len(new_skills)} skills, "
            f"{len(extracted.get('languages', []))} languages, "
            f"and {len(extracted.get('work_experiences', []))} work experiences."
        )

    except Exception as e:
        # Resume was saved, but AI parsing failed — inform the user gracefully
        error_msg = str(e)
        if "429" in error_msg or "quota" in error_msg.lower():
            friendly_err = "The AI service is currently unavailable due to strict usage limits on the Gemini API Free Tier."
        else:
            friendly_err = f"A processing error occurred ({error_msg[:50]}...)."
            
        messages.warning(
            request,
            f"Resume uploaded successfully, but AI extraction failed: {friendly_err} "
            "You can manually update your profile using the edit buttons."
        )

    return redirect('freelancer_profile')


@freelancer_required
def freelancer_view_resume(request):
    """Display the freelancer's uploaded resume."""
    freelancer = request.user.freelancer
    if not freelancer.resume:
        messages.error(request, "You have not uploaded a resume yet.")
        return redirect('freelancer_profile')
        
    resume_skills_list = []
    if freelancer.resume_skills:
        resume_skills_list = [s.strip() for s in freelancer.resume_skills.split(',') if s.strip()]
        
    return render(request, 'core/freelancer_resume.html', {
        'freelancer': freelancer,
        'resume_skills_list': resume_skills_list
    })


@freelancer_required
def freelancer_delete_resume(request):
    """Delete the resume and remove only the AI-added profile data."""
    if request.method != 'POST':
        return redirect('freelancer_profile')

    freelancer = request.user.freelancer

    if not freelancer.resume:
        messages.error(request, "No resume to delete.")
        return redirect('freelancer_profile')

    from core.models import FreelancerLanguage, FreelancerWorkExperience

    # 1. Delete the physical file
    try:
        import os
        if os.path.isfile(freelancer.resume.path):
            os.remove(freelancer.resume.path)
    except Exception:
        pass

    # 2. Remove AI-added skills stored in resume_skills
    if freelancer.resume_skills:
        ai_skills = {s.strip().lower() for s in freelancer.resume_skills.split(',') if s.strip()}
        remaining = [s for s in freelancer.skills_list if s.lower() not in ai_skills]
        freelancer.skills = ', '.join(remaining)

    # 3. Clear resume fields
    freelancer.resume = None
    freelancer.resume_skills = ''
    freelancer.save(update_fields=['resume', 'resume_skills', 'skills'])

    # 4. Delete AI-added languages and work experiences
    lang_count = FreelancerLanguage.objects.filter(freelancer=freelancer, is_from_resume=True).count()
    exp_count  = FreelancerWorkExperience.objects.filter(freelancer=freelancer, is_from_resume=True).count()
    FreelancerLanguage.objects.filter(freelancer=freelancer, is_from_resume=True).delete()
    FreelancerWorkExperience.objects.filter(freelancer=freelancer, is_from_resume=True).delete()

    messages.success(
        request,
        f"Resume deleted. Removed AI-added skills, {lang_count} language(s), and {exp_count} work experience(s). "
        "Manually entered data is preserved."
    )
    return redirect('freelancer_profile')


@freelancer_required
def freelancer_company_profile(request, client_id):
    """Read-only company profile page shown to freelancers."""
    from core.models import Client, Review, RatingSummary
    client = get_object_or_404(Client, id=client_id)

    # Open/in-progress projects by this client visible to freelancers
    open_projects = Project.objects.filter(
        client=client, status__in=['open', 'in_progress']
    ).select_related('category').order_by('-published_at')[:6]

    # Reviews received by this client (as reviewee)
    reviews = Review.objects.filter(
        reviewee=client.user, is_hidden=False
    ).select_related('reviewer', 'project').order_by('-created_at')[:5]

    # Rating summary
    try:
        rating_summary = client.user.rating_summary
    except Exception:
        rating_summary = None

    # Tags list
    tags = client.tags_list if hasattr(client, 'tags_list') else []

    # Languages list
    languages = [lang.strip() for lang in client.languages.split(',') if lang.strip()] if client.languages else []

    return render(request, 'core/freelancer_companyProfile.html', {
        'client': client,
        'open_projects': open_projects,
        'reviews': reviews,
        'rating_summary': rating_summary,
        'tags': tags,
        'languages': languages,
    })

