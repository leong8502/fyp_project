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
    UserSecurity, Milestone, MilestoneAttachment, CancellationRequest
)
from core.forms import (
    SecurePinForm,
    FreelancerProfileForm, FreelancerPortfolioForm, FreelancerWorkExperienceForm,
    FreelancerCertificationForm, FreelancerHeaderForm, FreelancerRateForm,
    FreelancerBackgroundForm, FreelancerSocialForm, FreelancerBioForm,
    FreelancerSkillsForm, FreelancerLanguageForm,
)
from core.services.project_service import ProjectService
from core.ai_utils import get_recommendations


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
    from core.ai_utils import AISearchManager
    from core.models import MatchScore

    query = request.GET.get('q', '').strip()
    freelancer = request.user.freelancer

    # Threshold: user-adjustable, default 20%, range 5-100
    try:
        threshold = int(request.GET.get('threshold', 20))
        threshold = max(5, min(100, threshold))
    except (ValueError, TypeError):
        threshold = 20

    projects = list(Project.objects.filter(status='open').select_related('client').prefetch_related('milestones'))
    manager = AISearchManager()

    # Use the new detailed method
    details = manager.calculate_match_details(projects, freelancer=freelancer, query=query)

    # Sort descending by score
    details.sort(key=lambda d: d['score'], reverse=True)

    # Filter by threshold and attach skills_list
    matched = []
    for d in details:
        project = d['project']
        score   = d['score']

        # Always attach skills_list for template rendering
        project.skills_list = [s.strip() for s in (project.required_skills or '').split(',') if s.strip()]

        if score >= threshold:
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
                pass  # Never crash the page due to DB errors

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
    freelancer = request.user.freelancer
    current_projects = Project.objects.filter(
        assigned_freelancer=freelancer, status__in=['in_progress', 'reviewing']
    )
    pass_projects = Project.objects.filter(assigned_freelancer=freelancer, status='completed')

    for project in pass_projects:
        project.has_reviewed = Review.objects.filter(project=project, reviewer=request.user).exists()

    pending_applications = ProjectApplication.objects.filter(
        freelancer=freelancer, status='pending'
    ).order_by('-created_at')

    # Attach pending cancellation request (if any) to each current project
    pending_cancellations = CancellationRequest.objects.filter(
        project__assigned_freelancer=freelancer,
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
        project__assigned_freelancer=request.user.freelancer,
        status='pending'
    )
    project = cancellation_req.project

    if request.method == 'POST':
        response = request.POST.get('response')  # 'agree' or 'decline'
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
            cancellation_req.status = 'declined'
            cancellation_req.save()
            # Notify client
            from core.services import NotificationService
            NotificationService.create_notification(
                recipient=project.client.user,
                notification_type='cancellation_request',
                title='Cancellation Request Declined',
                message=f"Freelancer declined your cancellation request for '{project.title}'. The project continues.",
                link=reverse('client_projectInfo', kwargs={'project_id': project.id})
            )
            messages.info(
                request,
                f"You declined the cancellation request for '{project.title}'. The project continues."
            )
        else:
            messages.error(request, "Invalid response.")

    return redirect('freelancer_track_project')


@freelancer_required
def freelancer_apply_project(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    if project.status != 'open':
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
        Milestone, id=milestone_id, project__assigned_freelancer=request.user.freelancer
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


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@freelancer_required
def freelancer_settings(request):
    user_security, _ = UserSecurity.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = SecurePinForm(request.POST, user_security=user_security)
        if form.is_valid():
            user_security.secure_pin = make_password(form.cleaned_data['new_pin'])
            user_security.save()
            messages.success(request, "Secure PIN updated successfully.")
            return redirect('freelancer_settings')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = SecurePinForm(user_security=user_security)

    return render(request, 'core/freelancer_settings.html', {'form': form})


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
        assigned_freelancer=freelancer, status='completed'
    ).order_by('-created_at')
    reviews = Review.objects.filter(reviewee=freelancer.user).order_by('-created_at')

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
