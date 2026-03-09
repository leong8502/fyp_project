"""
Common/guest views – home page, about, support.
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from core.decorators import guest_required
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator

from core.forms import SupportForm
from core.models import Ticket, Freelancer, Project

@guest_required
def home(request):
    from django.db.models import Avg
    from core.models import RatingSummary
    
    # Bayesian Average Formula Parameters
    # score = (v/(v+m))*R + (m/(v+m))*C
    # m = minimum reviews required (user specified 5)
    # v = number of reviews for the freelancer
    # R = average rating of the freelancer
    # C = mean rating across the whole report (average of all average_ratings)
    
    m = 5
    
    # Calculate C: mean rating across all freelancers who have at least one review
    # Or count all freelancers? Usually it's based on those with reviews.
    avg_data = RatingSummary.objects.filter(total_reviews__gt=0).aggregate(Avg('average_rating'))
    C = float(avg_data['average_rating__avg'] or 0)
    
    freelancers = list(Freelancer.objects.select_related('user__rating_summary'))
    
    # Calculate score for each freelancer
    for f in freelancers:
        rating_summary = getattr(f.user, 'rating_summary', None)
        if rating_summary:
            v = float(rating_summary.total_reviews)
            R = float(rating_summary.average_rating)
            # Apply Bayesian formula
            f.bayesian_score = (v / (v + m)) * R + (m / (v + m)) * C
        else:
            # For freelancers with no rating summary, v=0, R=0
            f.bayesian_score = (0 / (0 + m)) * 0 + (m / (0 + m)) * C
            
        f.skills_list_preview = [s.strip() for s in f.skills.split(',') if s.strip()][:3]

    # Sort freelancers by bayesian_score descending
    top_freelancers = sorted(freelancers, key=lambda x: x.bayesian_score, reverse=True)[:3]
        
    return render(request, 'core/home.html', {
        'top_freelancers': top_freelancers
    })

def guest_search(request):
    query = request.GET.get('q', '').strip()
    search_type = request.GET.get('type', 'hire') # 'hire' = search freelancers, 'work' = search projects
    
    # If user is logged in, redirect to their respective search pages
    if request.user.is_authenticated:
        if hasattr(request.user, 'client'):
            return redirect(f'/client/search/?q={query}')
        elif hasattr(request.user, 'freelancer'):
            return redirect(f'/freelancer/search-job/?q={query}')

    if search_type == 'hire':
        results = Freelancer.objects.select_related('user__rating_summary').all()
        if query:
            results = results.filter(
                Q(full_name__icontains=query) |
                Q(skills__icontains=query) |
                Q(tagline__icontains=query)
            )
        results = results.order_by('-user__rating_summary__average_rating')
    else:
        results = Project.objects.filter(status='open')
        if query:
            results = results.filter(
                Q(title__icontains=query) |
                Q(description__icontains=query) |
                Q(required_skills__icontains=query)
            )
        results = results.order_by('-published_at')

    paginator = Paginator(results, 9)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Get elided page range (e.g., [1, 2, '...', 7, 8, 9, '...', 20])
    # page_obj.number is the current page
    custom_page_range = paginator.get_elided_page_range(page_obj.number, on_each_side=2, on_ends=1)

    return render(request, 'core/guest_search.html', {
        'results': page_obj,
        'query': query,
        'search_type': search_type,
        'custom_page_range': custom_page_range,
    })

def aboutUS(request):
    if request.user.is_authenticated and hasattr(request.user, 'client'):
        base_template = 'core/client_master.html'
    elif request.user.is_authenticated and hasattr(request.user, 'freelancer'):
        base_template = 'core/freelancer_master.html'
    else:
        base_template = 'core/master.html'
    return render(request, 'core/about.html', {'base_template': base_template})