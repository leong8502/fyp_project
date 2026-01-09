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