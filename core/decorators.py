from django.http import HttpResponseForbidden
from django.shortcuts import redirect

def freelancer_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not hasattr(request.user, 'freelancer'):
            return HttpResponseForbidden("Freelancer access only")
        return view_func(request, *args, **kwargs)
    return wrapper

def client_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not hasattr(request.user, 'client'):
            return HttpResponseForbidden("Client access only")
        return view_func(request, *args, **kwargs)
    return wrapper

def guest_required(view_func):
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            if hasattr(request.user, 'client'):
                return redirect('client_home')
            elif hasattr(request.user, 'freelancer'):
                return redirect('freelancer_home')
        return view_func(request, *args, **kwargs)
    return wrapper