"""
Review views – submit reviews for projects.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from core.models import Project, Review
from core.forms import ReviewForm
from core.services import ReviewService

@login_required
def submit_review(request, project_id):
    """View to submit a review for a project."""
    project = get_object_or_404(Project, pk=project_id)
    reviewer = request.user

    reviewee = None
    if hasattr(reviewer, 'client') and project.client == reviewer.client:
        if project.assigned_freelancer:
            reviewee = project.assigned_freelancer.user
    elif hasattr(reviewer, 'freelancer') and project.assigned_freelancer == reviewer.freelancer:
        reviewee = project.client.user

    if not reviewee:
        messages.error(request, "You cannot review this project.")
        return redirect('client_project')

    existing_review = Review.objects.filter(project=project, reviewer=reviewer).first()
    if existing_review:
        messages.info(request, "You have already reviewed this project.")
        if hasattr(reviewer, 'client'):
            return redirect('client_projectInfo', project_id=project.id)
        return redirect(reverse('freelancer_track_project') + '?tab=pass')

    base_template = None
    if hasattr(reviewer, 'client'):
        base_template = 'core/client_master.html'
    elif hasattr(reviewer, 'freelancer'):
        base_template = 'core/freelancer_master.html'

    form = ReviewForm()

    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            try:
                tags = request.POST.getlist('feedback_tags')
                ReviewService.submit_review(project, reviewer, reviewee, form, tags)
                messages.success(request, "Review submitted successfully!")
                if hasattr(reviewer, 'client'):
                    return redirect('client_projectInfo', project_id=project.id)
                return redirect(reverse('freelancer_track_project') + '?tab=pass')
            except Exception as e:
                messages.error(request, f"Error submitting review: {str(e)}")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")

    if hasattr(reviewee, 'freelancer'):
        available_tags = ['High Quality Work', 'Fast Delivery', 'Great Communication', 'Skilled', 'Creative', 'Professional']
    elif hasattr(reviewee, 'client'):
        available_tags = ['Clear Requirements', 'Fast Payment', 'Good Communication', 'Respectful', 'Professional']
    else:
        available_tags = []

    return render(request, 'core/review.html', {
        'project': project,
        'reviewee': reviewee,
        'available_tags': available_tags,
        'base_template': base_template,
        'form': form,
    })
