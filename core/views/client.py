"""
Client views – profile, wallet, projects, payments, support, settings.
"""
import decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from django.core.paginator import Paginator
from django.urls import reverse
from django.db.models import Sum
from django.utils import timezone

from django.contrib.auth.decorators import login_required
from core.decorators import client_required, freelancer_required
from core.models import (
    Project, Milestone, ProjectApplication, Review,
    Wallet, Transaction, UserSecurity, Escrow, Freelancer,
    Ticket, ProjectActivity, CancellationRequest
)
from core.forms import (
    ClientProfileForm, ProjectForm, SecurePinForm, PaymentPinForm,
    WithdrawForm, SupportForm, ReviewForm
)
from core.services.project_service import ProjectService
from core.services.wallet_service import WalletService, PaymentService
from core.services.review_service import ReviewService


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------

@client_required
def client_home(request):
    return render(request, 'core/client_home.html')

# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@client_required
def client_search(request):
    from django.db.models import Q
    from core.models import Freelancer

    query = request.GET.get('q', '')
    rating_filter = request.GET.get('rating')
    avail_filter = request.GET.get('availability')

    freelancers = Freelancer.objects.select_related('user__rating_summary').all()

    # 1. Search Query (multi-term)
    if query:
        for term in query.split():
            freelancers = freelancers.filter(
                Q(full_name__icontains=term) |
                Q(skills__icontains=term) |
                Q(tagline__icontains=term) |
                Q(user__username__icontains=term)
            )

    # 2. Rating Filter
    if rating_filter:
        try:
            freelancers = freelancers.filter(
                user__rating_summary__average_rating__gte=float(rating_filter)
            )
        except ValueError:
            pass

    # 3. Availability Filter
    if avail_filter:
        freelancers = freelancers.filter(availability_status=avail_filter)

    # 4. Pagination
    paginator = Paginator(freelancers, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    from django.db.models import Count, Q, F

    open_projects = Project.objects.annotate(
        accepted_freelancers_count=Count(
            'applications',
            filter=Q(applications__status='accepted')
        )
    ).filter(
        client=request.user.client,
        status__in=['open', 'in_progress']
    ).filter(
        Q(status='open') | Q(accepted_freelancers_count__lt=F('max_freelancers'))
    )

    return render(request, 'core/client_search.html', {
        'freelancers': page_obj,
        'query': query,
        'current_rating': rating_filter,
        'current_avail': avail_filter,
        'has_filter': bool(rating_filter or avail_filter),
        'open_projects': open_projects,
    })


@client_required
def client_freelancerProfile(request, freelancer_id):
    from django.core.paginator import Paginator
    freelancer = get_object_or_404(Freelancer, id=freelancer_id)
    from django.db.models import Count, Q, F

    open_projects = Project.objects.annotate(
        accepted_freelancers_count=Count(
            'applications',
            filter=Q(applications__status='accepted')
        )
    ).filter(
        client=request.user.client,
        status__in=['open', 'in_progress']
    ).filter(
        Q(status='open') | Q(accepted_freelancers_count__lt=F('max_freelancers'))
    )
    
    # Fetch reviews for the freelancer (excluding hidden reviews)
    reviews_list = freelancer.user.received_reviews.filter(is_hidden=False).order_by('-created_at')
    
    # Paginate reviews: 5 per page
    paginator = Paginator(reviews_list, 5)
    page_number = request.GET.get('page')
    reviews = paginator.get_page(page_number)
    
    return render(request, 'core/client_freelancerProfile.html', {
        'freelancer': freelancer,
        'open_projects': open_projects,
        'reviews': reviews,
    })


# ---------------------------------------------------------------------------
# Support
# ---------------------------------------------------------------------------

@client_required
def client_support(request):
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
            messages.success(request, "Your ticket has been submitted successfully! We will contact you shortly.")
            return redirect('client_support')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = SupportForm(user=request.user)

    user_tickets = Ticket.objects.filter(user=request.user).order_by('-created_at')

    return render(request, 'core/client_support.html', {
        'form': form,
        'user_tickets': user_tickets
    })


# ---------------------------------------------------------------------------
# Settings / PIN
# ---------------------------------------------------------------------------

@client_required
def client_settings(request):
    user_security, _ = UserSecurity.objects.get_or_create(user=request.user)
    from core.models import NotificationSetting
    notification_settings, _ = NotificationSetting.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        section = request.POST.get('section')
        
        if section == 'security':
            form = SecurePinForm(request.POST, user_security=user_security)
            if form.is_valid():
                user_security.secure_pin = make_password(form.cleaned_data['new_pin'])
                user_security.save()
                messages.success(request, "Secure PIN updated successfully.")
                return redirect('client_settings')
            else:
                messages.error(request, "Please correct the errors below.")
        
        elif section == 'notifications':
            notification_settings.project_updates = 'project_updates' in request.POST
            notification_settings.payment_notifications = 'payment_notifications' in request.POST
            notification_settings.review_notifications = 'review_notifications' in request.POST
            notification_settings.save()
            messages.success(request, "Notification preferences updated.")
            return redirect(reverse('client_settings') + '#notifications')

    else:
        form = SecurePinForm(user_security=user_security)

    return render(request, 'core/client_settings.html', {
        'form': form,
        'notification_settings': notification_settings
    })


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@client_required
def client_profile(request):
    from django.core.paginator import Paginator
    
    # Fetch reviews for the current user (excluding hidden reviews)
    reviews_list = request.user.received_reviews.filter(is_hidden=False).order_by('-created_at')
    
    # Paginate reviews: 5 per page
    paginator = Paginator(reviews_list, 5)
    page_number = request.GET.get('page')
    reviews = paginator.get_page(page_number)
    
    context = {
        'reviews': reviews,
    }
    return render(request, 'core/client_profile.html', context)


@client_required
def client_editProfile(request):
    client = request.user.client

    if request.method == 'POST':
        form = ClientProfileForm(request.POST, request.FILES, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully!")
            return redirect('client_profile')
        else:
            for field, errors in form.errors.items():
                label = form.fields[field].label if field in form.fields else field
                for error in errors:
                    messages.error(request, f"{label}: {error}")
    else:
        form = ClientProfileForm(instance=client)

    return render(request, 'core/client_editProfile.html', {'form': form})


# ---------------------------------------------------------------------------
# Wallet
# ---------------------------------------------------------------------------

@client_required
def client_wallet(request):
    wallet = getattr(request.user, 'wallet', None)
    recent_transactions = []
    if wallet:
        recent_transactions = Transaction.objects.filter(wallet=wallet).order_by('-created_at')[:5]

    return render(request, 'core/client_wallet.html', {
        'wallet': wallet,
        'recent_transactions': recent_transactions,
    })


@login_required
def topUp(request):
    if hasattr(request.user, 'client'):
        base_template = 'core/client_master.html'
    elif hasattr(request.user, 'freelancer'):
        base_template = 'core/freelancer_master.html'
    else:
        messages.error(request, "User role not identified.")
        return redirect('home')

    if request.method == 'POST':
        amount_str = request.POST.get('amount')
        try:
            amount = decimal.Decimal(amount_str)
            if amount < 20:
                raise ValueError("Minimum top up amount is RM 20.")

            txn = WalletService.create_topup_transaction(request.user, amount)
            session = PaymentService.create_stripe_checkout_session(request, txn)
            return redirect(session.url)

        except Exception as e:
            messages.error(request, f"An error occurred: {str(e)}")
            return redirect('topUp')

    return render(request, 'core/topUp.html', {'base_template': base_template})


@login_required
def payment_success(request):
    session_id = request.GET.get('session_id')

    if session_id:
        try:
            reference_id = PaymentService.verify_stripe_payment(session_id)
            if reference_id:
                completed, _ = WalletService.complete_topup(reference_id)
                if completed:
                    messages.success(request, "Payment successful! Your wallet balance has been updated.")
                else:
                    messages.success(request, "Payment successful!")
            else:
                messages.warning(request, "Payment is still processing.")
        except Exception:
            messages.error(request, "Could not verify payment status.")
    else:
        messages.success(request, "Payment successful!")

    if hasattr(request.user, 'client'):
        return redirect('client_wallet')
    return redirect('freelancer_wallet')


@login_required
def payment_cancel(request):
    messages.warning(request, "Payment is pending. Please continue to pay for the transaction.")
    if hasattr(request.user, 'client'):
        return redirect('client_wallet')
    return redirect('freelancer_wallet')


@login_required
def payment_cancel_pending(request, transaction_id):
    if request.method == 'POST':
        success = WalletService.cancel_topup(transaction_id, request.user)
        if success:
            messages.success(request, "Pending top up has been cancelled.")
        else:
            messages.error(request, "This transaction cannot be cancelled.")

    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    if hasattr(request.user, 'client'):
        return redirect('client_wallet')
    return redirect('freelancer_wallet')


@login_required
def payment_continue(request, transaction_id):
    wallet = get_object_or_404(Wallet, user=request.user)
    txn = get_object_or_404(Transaction, id=transaction_id, wallet=wallet)

    if txn.status != 'pending' or txn.transaction_type != 'top_up':
        messages.error(request, "This transaction cannot be continued.")
        if hasattr(request.user, 'client'):
            return redirect('client_wallet')
        return redirect('freelancer_wallet')

    try:
        session = PaymentService.create_stripe_checkout_session(request, txn)
        return redirect(session.url)
    except Exception as e:
        messages.error(request, f"An error occurred with the payment gateway: {str(e)}")
        if hasattr(request.user, 'client'):
            return redirect('client_wallet')
        return redirect('freelancer_wallet')


@login_required
def withdraw(request):
    if hasattr(request.user, 'client'):
        base_template = 'core/client_master.html'
    elif hasattr(request.user, 'freelancer'):
        base_template = 'core/freelancer_master.html'
    else:
        messages.error(request, "User role not identified.")
        return redirect('home')

    wallet = getattr(request.user, 'wallet', None)

    # Ensure the user has a Secure PIN set up
    user_security = getattr(request.user, 'security', None)
    if not user_security or not user_security.secure_pin:
        if hasattr(request.user, 'client'):
            messages.warning(request, "Please set up your Secure PIN before making a withdrawal.")
            return redirect('client_settings')
        else:
            messages.warning(request, "Please set up your Secure PIN before making a withdrawal.")
            return redirect('freelancer_settings')

    if request.method == 'POST':
        # Verify PIN first
        pin_form = PaymentPinForm(request.POST)
        if not pin_form.is_valid():
            messages.error(request, "Please enter a valid 6-digit PIN.")
            return redirect('withdraw')

        if not check_password(pin_form.cleaned_data['secure_pin'], user_security.secure_pin):
            messages.error(request, "Incorrect Secure PIN. Please try again.")
            return redirect('withdraw')

        # PIN OK – now validate the withdrawal fields
        form = WithdrawForm(request.POST, wallet=wallet)
        if form.is_valid():
            try:
                WalletService.withdraw(
                    wallet,
                    form.cleaned_data['amount'],
                    form.cleaned_data['bank_name'],
                    form.cleaned_data['account_number'],
                )
                messages.success(request, f"Withdrawal request for RM {form.cleaned_data['amount']:.2f} submitted successfully!")
                if hasattr(request.user, 'client'):
                    return redirect('client_wallet')
                return redirect('freelancer_home')
            except Exception as e:
                messages.error(request, f"An error occurred: {str(e)}")
        else:
            for _, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)

    return render(request, 'core/withdraw.html', {'base_template': base_template, 'wallet': wallet})



@client_required
def client_transaction(request):
    wallet = getattr(request.user, 'wallet', None)
    page_obj = None

    if wallet:
        qs = Transaction.objects.filter(wallet=wallet)

        filter_type = request.GET.get('type')
        if filter_type in ['top_up', 'withdrawal', 'payment', 'refund']:
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

    return render(request, 'core/client_transaction.html', {
        'wallet': wallet,
        'transactions': page_obj,
        'page_obj': page_obj,
        'current_type': request.GET.get('type', ''),
        'current_sort': request.GET.get('sort', 'newest'),
    })


@login_required
def toggle_balance_privacy(request):
    if request.method == "POST":
        wallet = WalletService.toggle_balance_privacy(request.user)
        if wallet:
            return JsonResponse({'status': 'success', 'is_hidden': wallet.is_hidden})
    return JsonResponse({'status': 'error'}, status=400)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

@client_required
def client_project(request):
    all_projects = Project.objects.filter(client=request.user.client).prefetch_related(
        'applications__freelancer__user'
    ).order_by('-created_at')
    
    # Stats (calculated from all client projects)
    active_count = all_projects.filter(status='open').count()
    completed_count = all_projects.filter(status='completed').count()
    in_progress_count = all_projects.filter(status='in_progress').count()
    total_spent = all_projects.exclude(status='draft').aggregate(Sum('budget'))['budget__sum'] or 0

    # Filtering for the current view
    projects = all_projects
    
    search = request.GET.get('search', '')
    if search:
        projects = projects.filter(title__icontains=search)
        
    status_filter = request.GET.get('status', '')
    if status_filter and status_filter != 'all':
        projects = projects.filter(status=status_filter)
        
    date_filter = request.GET.get('date', '')
    if date_filter and date_filter != 'all':
        now = timezone.now()
        if date_filter == 'last30':
            projects = projects.filter(created_at__gte=now - timezone.timedelta(days=30))
        elif date_filter == 'last90':
            projects = projects.filter(created_at__gte=now - timezone.timedelta(days=90))
        elif date_filter == 'this-year':
            projects = projects.filter(created_at__year=now.year)

    # Paginator: 10 per page
    paginator = Paginator(projects, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'core/client_project.html', {
        'projects': page_obj,
        'active_count': active_count,
        'completed_count': completed_count,
        'in_progress_count': in_progress_count,
        'total_spent': total_spent,
        'search': search,
        'status_filter': status_filter,
        'date_filter': date_filter,
    })


@client_required
def client_projectCreate(request):
    if request.method == 'POST':
        form = ProjectForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                ProjectService.create_project(request.user.client, form, request.POST)
                messages.success(request, "Project created successfully! You can publish it once you are ready.")
                return redirect('client_project')
            except Exception as e:
                messages.error(request, f"Error creating project: {str(e)}")
        else:
            messages.error(request, "Please correct the errors below.")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = ProjectForm()

    return render(request, 'core/client_projectCreate.html', {'form': form})


from core.services.ai_generation_service import AIGenerationService
from django.views.decorators.http import require_POST
import json

@client_required
@require_POST
def api_generate_project_scope(request):
    """
    Generate a project scope from a user prompt using AI.
    """
    try:
        data = json.loads(request.body)
        prompt = data.get('prompt')
        if not prompt:
            return JsonResponse({'error': 'Prompt is required.'}, status=400)
            
        generated_data = AIGenerationService.generate_project_scope(prompt)
        return JsonResponse(generated_data)
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format.'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@client_required
def api_get_ai_quota(request):
    """
    Returns the current day's AI quota usage.
    """
    try:
        usage = AIGenerationService.get_current_quota_usage()
        limit = AIGenerationService.DAILY_QUOTA_LIMIT
        return JsonResponse({
            'usage': usage,
            'limit': limit,
            'remaining': max(0, limit - usage)
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@client_required
def client_start_project(request, project_id):
    project = get_object_or_404(Project, id=project_id, client=request.user.client)
    
    if project.status != 'open':
        messages.error(request, "Only open projects can be started.")
        return redirect('client_projectInfo', project_id=project.id)

    if request.method == 'POST':
        try:
            ProjectService.start_project(project, request.user)
            messages.success(request, f"Project '{project.title}' has started successfully.")
        except ValueError as ve:
            messages.error(request, str(ve))
        except Exception as e:
            messages.error(request, f"Error starting project: {e}")

    return redirect('client_projectInfo', project_id=project.id)


@client_required
def client_projectInfo(request, project_id):
    project = get_object_or_404(Project, id=project_id, client=request.user.client)
    escrow = getattr(project, 'escrow', None)

    has_accepted_freelancers = project.applications.filter(status='accepted').exists()

    hired_freelancers = []
    if project.status in ['in_progress', 'completed'] or has_accepted_freelancers:
        hired_freelancers = [app.freelancer for app in project.applications.filter(status='accepted')]
        
    reviews_by_user = {}
    if project.status == 'completed':
        for r in Review.objects.filter(project=project, reviewer=request.user):
            reviews_by_user[r.reviewee.id] = r
            
    for f in hired_freelancers:
        f.client_review = reviews_by_user.get(f.user.id)
        
    contract_started = None
    if has_accepted_freelancers:
        first_accepted = project.applications.filter(status='accepted').order_by('updated_at').first()
        if first_accepted:
            contract_started = first_accepted.updated_at

    milestones = project.milestones.all()
    total_milestones = milestones.count()
    approved_milestones = milestones.filter(status='approved').count()
    progress_percentage = int((approved_milestones / total_milestones) * 100) if total_milestones > 0 else 0

    activities = project.activities.all()[:10]

    # Simple logic: disable cancellation if current active milestone is 'completed' (Waiting for Approval)
    current_active_milestone = project.milestones.exclude(status='approved').order_by('order').first()
    is_cancellation_available = True
    if current_active_milestone and current_active_milestone.status == 'completed':
        is_cancellation_available = False

    # Pending cancellation requests (for in-progress projects)
    pending_cancellations = project.cancellation_requests.filter(status='pending')
    has_pending_cancellation = pending_cancellations.exists()

    return render(request, 'core/client_projectInfo.html', {
        'project': project,
        'escrow': escrow,
        'contract_started': contract_started,
        'progress_percentage': progress_percentage,
        'activities': activities,
        'has_pending_cancellation': has_pending_cancellation,
        'pending_cancellations': pending_cancellations,
        'is_cancellation_available': is_cancellation_available,
        'current_active_milestone': current_active_milestone,
        'has_accepted_freelancers': has_accepted_freelancers,
        'hired_freelancers': hired_freelancers,
        'has_pending_cancellation': has_pending_cancellation,
        'pending_cancellations': pending_cancellations,
        'today': timezone.now().date(),
    })


@client_required
def client_projectMatches(request, project_id):
    from core.ai_matching import MatchEngine
    project = get_object_or_404(Project, id=project_id, client=request.user.client)

    if request.GET.get('refresh'):
        MatchEngine().compute_matches(project.id)
        return redirect('client_projectMatches', project_id=project.id)

    matches = project.matches.select_related('freelancer__user__rating_summary').all()

    if not matches.exists() and project.status == 'open':
        MatchEngine().compute_matches(project.id)
        matches = project.matches.select_related('freelancer').all()

    return render(request, 'core/client_projectMatches.html', {
        'project': project,
        'matches': matches,
    })


@client_required
def client_projectEdit(request, project_id):
    project = Project.objects.get(id=project_id, client=request.user.client)
    experience_5_plus = project.year_of_experience >= 5

    if project.status != 'draft':
        messages.error(request, "Only draft projects can be edited.")
        return redirect('client_projectInfo', project_id=project.id)

    if request.method == 'POST':
        form = ProjectForm(request.POST, request.FILES, instance=project)
        if form.is_valid():
            try:
                remove_attachment = bool(request.POST.get('attachment-clear'))
                ProjectService.update_project(project, request.user.client, form, request.POST, remove_attachment)
                messages.success(request, "Project updated successfully!")
                return redirect('client_projectInfo', project_id=project.id)
            except Exception as e:
                messages.error(request, f"Error updating project: {str(e)}")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = ProjectForm(instance=project)

    return render(request, 'core/client_projectEdit.html', {
        'form': form,
        'project': project,
        'experience_5_plus': experience_5_plus,
    })


@client_required
def client_projectDelete(request, project_id):
    project = Project.objects.get(id=project_id, client=request.user.client)

    if project.status == 'draft':
        if request.method == 'POST':
            try:
                project.delete()
                messages.success(request, "Project deleted successfully.")
                return redirect('client_project')
            except Exception as e:
                messages.error(request, f"Error deleting project: {str(e)}")
                return redirect('client_projectInfo', project_id=project.id)
        return redirect('client_projectInfo', project_id=project.id)

    elif project.status == 'open':
        if request.method == 'POST':
            try:
                ProjectService.cancel_open_project(project, request.user)
                messages.success(
                    request,
                    f"Project '{project.title}' has been cancelled. Your escrow payment has been refunded to your wallet."
                )
                return redirect('client_project')
            except Exception as e:
                messages.error(request, f"Error cancelling project: {str(e)}")
                return redirect('client_projectInfo', project_id=project.id)
        return redirect('client_projectInfo', project_id=project.id)

    else:
        messages.error(request, "Only draft or open projects can be cancelled here.")
        return redirect('client_projectInfo', project_id=project.id)


@client_required
def client_request_cancellation(request, project_id):
    """Client requests cancellation of an in-progress project."""
    project = get_object_or_404(Project, id=project_id, client=request.user.client)

    if project.status != 'in_progress':
        messages.error(request, "Only in-progress projects can be requested for cancellation.")
        return redirect('client_projectInfo', project_id=project.id)

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        freelancer_id = request.POST.get('freelancer_id')
        
        if not freelancer_id:
            messages.error(request, "Please select a freelancer to cancel.")
            return redirect('client_projectInfo', project_id=project.id)
            
        if freelancer_id == 'all':
            # Check if any cancellation requests are already pending
            if project.cancellation_requests.filter(status='pending').exists():
                messages.warning(request, "There are already pending cancellation requests. Please wait for them to be resolved.")
                return redirect('client_projectInfo', project_id=project.id)
                
            try:
                is_cancelled_immediately = ProjectService.request_full_project_cancellation(project, request.user, reason)
                if is_cancelled_immediately:
                    messages.success(request, f"Project '{project.title}' has been directly cancelled and escrow refunded as no freelancers were assigned.")
                else:
                    messages.success(
                        request,
                        "Full project cancellation request sent to all freelancers. "
                        "The project will be cancelled if all freelancers agree."
                    )
            except Exception as e:
                messages.error(request, f"Failed to request project cancellation: {str(e)}")
            return redirect('client_projectInfo', project_id=project.id)

        from core.models import Freelancer
        freelancer = get_object_or_404(Freelancer, id=freelancer_id)
        
        # Check if freelancer is hired for this project
        if not project.applications.filter(freelancer=freelancer, status='accepted').exists():
            messages.error(request, "Selected freelancer is not active on this project.")
            return redirect('client_projectInfo', project_id=project.id)

        # Check if cancellation is already pending for this freelancer
        if project.cancellation_requests.filter(freelancer=freelancer, status='pending').exists():
            messages.warning(request, "A cancellation request for this freelancer is already pending.")
            return redirect('client_projectInfo', project_id=project.id)

        try:
            ProjectService.request_project_cancellation(project, request.user, reason, freelancer)
            messages.success(
                request,
                f"Cancellation request sent to {freelancer.user.username}. "
                "They will be removed from the project if they agree."
            )
        except Exception as e:
            messages.error(request, f"Failed to send cancellation request: {str(e)}")

    return redirect('client_projectInfo', project_id=project.id)


@client_required
def client_projectPublish(request, project_id):
    """Display payment confirmation page for publishing a project."""
    project = get_object_or_404(Project, id=project_id, client=request.user.client)

    if project.status != 'draft':
        messages.error(request, "Only draft projects can be published.")
        return redirect('client_projectInfo', project_id=project.id)

    # Block publishing if the deadline has already passed
    if project.deadline < timezone.now().date():
        messages.error(
            request,
            "Cannot publish: the project deadline has already passed. "
            "Please edit the project and set a future deadline first."
        )
        return redirect('client_projectEdit', project_id=project.id)

    user_security = getattr(request.user, 'security', None)
    if not user_security or not user_security.secure_pin:
        messages.warning(request, "Please set up your Secure PIN before publishing a project.")
        return redirect('client_settings')

    wallet = getattr(request.user, 'wallet', None)
    if not wallet:
        messages.error(request, "Wallet not found. Please contact support.")
        return redirect('client_projectInfo', project_id=project.id)

    milestones = project.milestones.all().order_by('order')
    
    import decimal
    platform_fee = round(project.budget * decimal.Decimal('0.10'), 2)
    total_payment = project.budget + platform_fee
    
    has_sufficient_balance = wallet.balance >= total_payment
    balance_after_payment = wallet.balance - total_payment
    amount_needed = total_payment - wallet.balance if not has_sufficient_balance else decimal.Decimal('0.00')

    return render(request, 'core/client_projectPublish.html', {
        'project': project,
        'milestones': milestones,
        'wallet': wallet,
        'platform_fee': platform_fee,
        'total_payment': total_payment,
        'has_sufficient_balance': has_sufficient_balance,
        'balance_after_payment': balance_after_payment,
        'amount_needed': amount_needed,
        'form': PaymentPinForm(),
    })


@client_required
def client_confirmPayment(request, project_id):
    """Process payment and publish project."""
    if request.method != 'POST':
        return redirect('client_projectPublish', project_id=project_id)

    project = get_object_or_404(Project, id=project_id, client=request.user.client)

    if project.status != 'draft':
        messages.error(request, "Only draft projects can be published.")
        return redirect('client_projectInfo', project_id=project.id)

    # Defence-in-depth: block publish if deadline has passed
    if project.deadline < timezone.now().date():
        messages.error(
            request,
            "Cannot publish: the project deadline has already passed. "
            "Please edit the project and set a future deadline first."
        )
        return redirect('client_projectEdit', project_id=project.id)

    user_security = getattr(request.user, 'security', None)
    if not user_security or not user_security.secure_pin:
        messages.error(request, "Secure PIN not set up.")
        return redirect('client_settings')

    form = PaymentPinForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please enter a valid 6-digit PIN.")
        return redirect('client_projectPublish', project_id=project_id)

    if not check_password(form.cleaned_data['secure_pin'], user_security.secure_pin):
        messages.error(request, "Incorrect Secure PIN. Please try again.")
        return redirect('client_projectPublish', project_id=project_id)

    wallet = getattr(request.user, 'wallet', None)
    if not wallet:
        messages.error(request, "Wallet not found.")
        return redirect('client_projectInfo', project_id=project.id)

    import decimal
    platform_fee = round(project.budget * decimal.Decimal('0.10'), 2)
    total_payment = project.budget + platform_fee

    if wallet.balance < total_payment:
        messages.error(request, f"Insufficient balance. You need RM {total_payment - wallet.balance:.2f} more.")
        return redirect('client_projectPublish', project_id=project_id)

    try:
        ProjectService.publish_project(project, wallet)
        messages.success(
            request,
            f"Project '{project.title}' published successfully! RM {project.budget:.2f} has been placed in escrow and RM {platform_fee:.2f} paid as platform fee."
        )
        return redirect('client_projectInfo', project_id=project.id)
    except Exception as e:
        messages.error(request, f"An error occurred while processing payment: {str(e)}")
        return redirect('client_projectPublish', project_id=project_id)


# ---------------------------------------------------------------------------
# Application / Invitation management (client side)
# ---------------------------------------------------------------------------

@client_required
def client_invite_freelancer(request, freelancer_id):
    freelancer = get_object_or_404(Freelancer, id=freelancer_id)
    if request.method == 'POST':
        project_id = request.POST.get('project_id')
        message = request.POST.get('message', '')
        project = get_object_or_404(Project, id=project_id, client=request.user.client)
        
        can_invite = False
        if project.status == 'open':
            can_invite = True
        elif project.status == 'in_progress':
            accepted_count = project.applications.filter(status='accepted').count()
            if accepted_count < project.max_freelancers:
                can_invite = True
                
        if not can_invite:
            messages.error(request, "Project is not open or is already full.")
            return redirect('client_freelancerProfile', freelancer_id=freelancer.id)

        application = ProjectApplication.objects.filter(project=project, freelancer=freelancer).first()
        if application:
            if application.status in ['pending', 'accepted']:
                messages.error(request, "You have already invited this freelancer or they have already applied.")
                return redirect('client_freelancerProfile', freelancer_id=freelancer.id)
            application.status = 'pending'
            application.message = message
            application.application_type = 'invite'
            application.save()
        else:
            ProjectApplication.objects.create(
                project=project, freelancer=freelancer,
                application_type='invite', message=message
            )

        messages.success(request, f"Invitation sent to {freelancer.user.username} for {project.title}!")
        return redirect('client_projectInfo', project_id=project.id)

    return redirect('client_search')


@login_required
def accept_application(request, app_id):
    application = get_object_or_404(ProjectApplication, id=app_id)
    project = application.project

    is_client_accepting = (
        getattr(request.user, 'client', None) == project.client
        and application.application_type == 'apply'
    )
    is_freelancer_accepting = (
        getattr(request.user, 'freelancer', None) == application.freelancer
        and application.application_type == 'invite'
    )

    if not (is_client_accepting or is_freelancer_accepting):
        messages.error(request, "Unauthorized to accept this application.")
        return redirect('home')

    if project.status not in ['open', 'in_progress']:
        messages.error(request, "This project is no longer open for new freelancers.")
        return redirect('home')

    try:
        ProjectService.accept_application(application, request.user)
        messages.success(request, f"Application from {application.freelancer.user.username} accepted! You can now assign milestones to them.")
    except Exception as e:
        messages.error(request, f"Error: {e}")

    if hasattr(request.user, 'client'):
        return redirect('client_projectInfo', project_id=project.id)
    return redirect('freelancer_track_project')


@login_required
def reject_application(request, app_id):
    application = get_object_or_404(ProjectApplication, id=app_id)

    can_reject = (
        getattr(request.user, 'client', None) == application.project.client
        or getattr(request.user, 'freelancer', None) == application.freelancer
    )

    if can_reject:
        ProjectService.reject_application(application, request.user)
        messages.success(request, "Application rejected.")
    else:
        messages.error(request, "Unauthorized to reject this application.")

    if hasattr(request.user, 'client'):
        return redirect('client_projectInfo', project_id=application.project.id)
    return redirect('freelancer_track_project')


# ---------------------------------------------------------------------------
# Milestone management (client side)
# ---------------------------------------------------------------------------

@client_required
def client_assign_milestone(request, milestone_id):
    milestone = get_object_or_404(Milestone, id=milestone_id, project__client=request.user.client)
    
    if milestone.project.status != 'in_progress':
        messages.error(request, "Project must be 'in progress' to assign milestones.")
        return redirect('client_projectInfo', project_id=milestone.project.id)

    if request.method == 'POST':
        freelancer_id = request.POST.get('freelancer_id')
        if not freelancer_id:
            messages.error(request, "Please select a freelancer.")
            return redirect('client_projectInfo', project_id=milestone.project.id)

        from core.models import Freelancer
        freelancer = get_object_or_404(Freelancer, id=freelancer_id)
        if not milestone.project.applications.filter(freelancer=freelancer, status='accepted').exists():
            messages.error(request, "Freelancer is not hired for this project.")
            return redirect('client_projectInfo', project_id=milestone.project.id)
            
        if milestone.assigned_to != freelancer:
            milestone.revision_requested = False
            milestone.revision_count = 0
            milestone.revision_reason = ""
            milestone.attachments.all().delete()

        milestone.assigned_to = freelancer
        milestone.save()
        messages.success(request, f"Milestone '{milestone.title}' assigned to {freelancer.user.username}.")
        
    return redirect('client_projectInfo', project_id=milestone.project.id)


@client_required
def client_request_revision(request, milestone_id):
    milestone = get_object_or_404(Milestone, id=milestone_id, project__client=request.user.client)
    if milestone.status != 'completed':
        messages.error(request, "Milestone must be completed by freelancer first.")
        return redirect('client_projectInfo', project_id=milestone.project.id)

    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        ProjectService.request_revision(milestone, reason, request.user)
        messages.success(request, "Revision requested.")

    return redirect('client_projectInfo', project_id=milestone.project.id)


@client_required
def client_release_milestone_payment(request, milestone_id):
    milestone = get_object_or_404(Milestone, id=milestone_id, project__client=request.user.client)
    if milestone.status != 'completed':
        messages.error(request, "Milestone must be submitted before releasing payment.")
        return redirect('client_projectInfo', project_id=milestone.project.id)

    if request.method == 'POST':
        user_security = getattr(request.user, 'security', None)
        entered_pin = request.POST.get('secure_pin')
        if not user_security or not check_password(entered_pin, user_security.secure_pin):
            messages.error(request, "Invalid Secure PIN.")
            return redirect('client_projectInfo', project_id=milestone.project.id)

        try:
            next_milestone, is_complete = ProjectService.release_milestone_payment(milestone, request.user)
            if is_complete:
                messages.success(request, "Payment released! All milestones done, project is now completed.")
            else:
                messages.success(
                    request,
                    f"Payment released! Next milestone '{next_milestone.title}' is now in progress."
                )
        except Exception as e:
            messages.error(request, f"Error releasing payment: {e}")

    return redirect('client_projectInfo', project_id=milestone.project.id)


    

@login_required
def report_project(request, project_id):
    """View to report a project and create a support ticket."""
    project = get_object_or_404(Project, id=project_id)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, "Please provide a reason for reporting.")
            return redirect('client_projectInfo', project_id=project.id)
            
        # Create a support ticket
        Ticket.objects.create(
            user=request.user,
            title=f"Report Project: {project.title} (ID: {project.id})",
            category='disputes',
            description=f"{reason}",
            status='open'
        )
        
        messages.success(request, "Project report submitted successfully. Our team will review it.")
        
    return redirect('client_projectInfo', project_id=project.id)


@login_required
def report_review(request, review_id):
    """View to report a review and create a support ticket under 'reviews' category."""
    review = get_object_or_404(Review, id=review_id)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, "Please provide a reason for reporting.")
        else:
            reviewee_name = review.reviewee.username
            if hasattr(review.reviewee, 'freelancer'):
                reviewee_name = review.reviewee.freelancer.full_name or reviewee_name
            elif hasattr(review.reviewee, 'client'):
                reviewee_name = review.reviewee.client.company_name or reviewee_name

            Ticket.objects.create(
                user=request.user,
                title=f"Report Review (ID: {review.id})",
                category='reviews',
                description=reason,
                status='open'
            )
            messages.success(request, "Review report submitted. Our team will investigate.")
    
    # Redirect back to wherever the user came from
    return redirect(request.META.get('HTTP_REFERER', '/'))


@client_required
def client_scoreCalculate(request, match_id):
    """View to show the dynamic freelancer match score breakdown."""
    from core.models import ProjectMatch
    
    match = get_object_or_404(ProjectMatch, id=match_id, project__client=request.user.client)
    
    # Calculate percentage scores for the progress bars
    bd = match.score_breakdown
    
    percentages = {
        'semantic': (bd.get('semantic', 0) / 1.0) * 100, 
        'skill_overlap': (bd.get('skill_overlap', 0) / 1.0) * 100,
        'experience': (bd.get('experience', 0) / 1.0) * 100,
        'reputation': (bd.get('reputation', 0) / 1.0) * 100,
        'language': (bd.get('language', 0) / 1.0) * 100,
        'availability': (bd.get('availability', 0) / 1.0) * 100,
    }
    
    # --- Generate Dynamic Metric Insights ---
    project = match.project
    freelancer = match.freelancer
    
    insights = {}
    
    # 1. Semantic Match
    sem_score = percentages['semantic']
    if sem_score >= 80:
        insights['semantic'] = "Strong alignment. The freelancer's profile and experience description highly match your project's context."
    elif sem_score >= 50:
        insights['semantic'] = "Moderate alignment. Some elements of the freelancer's profile match your project context."
    else:
        insights['semantic'] = "Low alignment. The freelancer's profile indicates focus in different technical domains or contexts."

    # 2. Skill Overlap
    req_skills_raw = [s.strip() for s in project.required_skills.split(',')] if project.required_skills else []
    free_skills_raw = [s.strip() for s in freelancer.skills.split(',')] if freelancer.skills else []
    
    req_skills = set(s.lower() for s in req_skills_raw if s)
    free_skills = set(s.lower() for s in free_skills_raw if s)
    
    overlap = req_skills.intersection(free_skills)
    missing = req_skills.difference(free_skills)
    
    overlap_display = [s for s in req_skills_raw if s.lower() in overlap]
    missing_display = [s for s in req_skills_raw if s.lower() in missing]
    
    if req_skills:
        skill_text = ""
        if overlap_display:
            skill_text += f"<strong style='color: #2e7d32;'>Matched:</strong> {', '.join(overlap_display)}. "
        if missing_display:
             skill_text += f"<strong style='color: #c62828;'>Missing:</strong> {', '.join(missing_display)}."
        if not overlap_display and not missing_display:
            skill_text = "No required skills specified or parsed."
        insights['skill_overlap'] = skill_text.strip()
    else:
        insights['skill_overlap'] = "You have not listed specific skill requirements for this project."

    # 3. Experience
    req_exp = project.get_experience_level_display()
    free_exp = f"{freelancer.experience_years} year{'s' if freelancer.experience_years != 1 else ''}"
    exp_pct = percentages['experience']
    
    if exp_pct == 100:
        insights['experience'] = f"Fully satisfies requirement. You requested an <strong>{req_exp}</strong> level professional, and this freelancer has <strong>{free_exp}</strong> of experience."
    elif exp_pct > 0:
        insights['experience'] = f"Partial match. You requested an <strong>{req_exp}</strong> level professional, but this freelancer has <strong>{free_exp}</strong> of experience."
    else:
        insights['experience'] = f"Does not meet requirement. You requested an <strong>{req_exp}</strong> level professional. This freelancer lists {free_exp} of experience."

    # 4. Reputation
    avg_rating = 0.0
    total_reviews = 0
    try:
        if hasattr(freelancer.user, 'rating_summary'):
            avg_rating = float(freelancer.user.rating_summary.average_rating)
            total_reviews = freelancer.user.rating_summary.total_reviews
    except Exception:
        pass
    
    if total_reviews > 0:
        insights['reputation'] = f"Freelancer maintains a <strong>{avg_rating:.1f} star</strong> rating across <strong>{total_reviews}</strong> completed projects on the platform."
    else:
        insights['reputation'] = "Freelancer does not currently have enough project history or reviews to establish a reputation score."

    # 5. Language
    pref_lang = project.preferred_language
    if pref_lang:
        # Checking if freelancer has this language (basic check vs model logic)
        lang_match = freelancer.languages.filter(language__icontains=pref_lang.lower().strip()).exists()
        if lang_match:
            insights['language'] = f"Freelancer is proficient in <strong>{pref_lang}</strong>, satisfying your language preference."
        else:
            insights['language'] = f"Freelancer did not list <strong>{pref_lang}</strong> in their recorded languages."
    else:
        insights['language'] = "You did not specify a preferred language for this project."

    # 6. Availability
    avail_status = freelancer.get_availability_status_display()
    if percentages['availability'] == 100:
        insights['availability'] = f"Excellent alignment. Freelancer is available for <strong>{avail_status}</strong> work, seamlessly fitting project timelines."
    elif percentages['availability'] > 30:
        insights['availability'] = f"Moderate alignment. Freelancer is available for <strong>{avail_status}</strong> work, which may require schedule coordination."
    else:
         insights['availability'] = f"Low alignment. Freelancer's current status is <strong>{avail_status}</strong>, which might impact delivery speed."

    
    context = {
        'match': match,
        'breakdown': bd,
        'percentages': percentages,
        'insights': insights
    }
    
    return render(request, 'core/client_scoreCalculate.html', context)
