"""
Common/guest views – home page, about, support.
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from core.decorators import guest_required
from django.contrib import messages

from core.forms import SupportForm
from core.models import Ticket

@guest_required
def home(request):
    return render(request, 'core/home.html')

def aboutUS(request):
    if request.user.is_authenticated and hasattr(request.user, 'client'):
        base_template = 'core/client_master.html'
    elif request.user.is_authenticated and hasattr(request.user, 'freelancer'):
        base_template = 'core/freelancer_master.html'
    else:
        base_template = 'core/master.html'
    return render(request, 'core/about.html', {'base_template': base_template})