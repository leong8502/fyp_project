"""
Auth views – login, logout, registration, email verification.
"""
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from core.decorators import guest_required
from core.models import AdminLog
from core.forms import ClientRegistrationForm
from core.services.auth_service import AuthService


@guest_required
def login(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        role = request.POST.get("role")  # client / freelancer

        from django.contrib.auth.models import User
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            messages.error(request, "Invalid email or password")
            return redirect("login")

        if not user.is_active and user.check_password(password):
            # Check if it's due to email verification or deactivation
            is_verified = False
            if hasattr(user, 'client'):
                is_verified = user.client.is_email_verified
            elif hasattr(user, 'freelancer'):
                is_verified = user.freelancer.is_email_verified
            
            if not is_verified:
                messages.error(request, "Please verify your email before login")
            else:
                messages.error(request, "Your account has been deactivated. Please contact support.")
            return redirect("login")

        user = authenticate(request, username=user.username, password=password)

        if user is None:
            messages.error(request, "Invalid email or password")
            return redirect("login")

        if role == "client" and not hasattr(user, "client"):
            messages.error(request, "This account is not registered as a Client")
            return redirect("login")

        if role == "freelancer" and not hasattr(user, "freelancer"):
            messages.error(request, "This account is not registered as a Freelancer")
            return redirect("login")

        auth_login(request, user)

        if request.POST.get('remember_me'):
            request.session.set_expiry(1209600)
        else:
            request.session.set_expiry(0)

        if role == "client":
            return redirect("client_home")
        return redirect("freelancer_home")

    return render(request, "core/login.html")


def admin_login(request):
    """Admin login – for superusers and staff."""
    if request.user.is_authenticated:
        if request.user.is_superuser or request.user.is_staff:
            return redirect('admin_dashboard')
        else:
            messages.error(request, "Access denied. Admin privileges required.")
            return redirect('home')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_superuser or user.is_staff:
                auth_login(request, user)
                AdminLog.objects.create(
                    admin_user=user,
                    action='login',
                    description='Admin logged in',
                    ip_address=request.META.get('REMOTE_ADDR')
                )
                messages.success(request, f"Welcome back, {user.username}!")
                return redirect('admin_dashboard')
            else:
                messages.error(request, "Access denied. Only administrators can login here.")
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, 'core/admin/admin_login.html')


@login_required
def logout(request):
    if request.user.is_superuser or request.user.is_staff:
        AdminLog.objects.create(
            admin_user=request.user,
            action='logout',
            description='Admin logged out',
            ip_address=request.META.get('REMOTE_ADDR')
        )
    auth_logout(request)
    return redirect('home')


@guest_required
def registerSelection(request):
    return render(request, 'core/registerSelection.html')


@guest_required
def register_client(request):
    if request.method == 'POST':
        form = ClientRegistrationForm(request.POST)
        if form.is_valid():
            try:
                AuthService.register_client(request, form)
                messages.success(
                    request,
                    "Registration successful! Please check your email to verify your account."
                )
                return redirect('login')
            except Exception as e:
                messages.error(request, f"An error occurred during registration: {str(e)}")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = ClientRegistrationForm()

    return render(request, 'core/client_register.html', {'form': form})


@guest_required
def register_freelancer(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        full_name = request.POST.get('full_name')
        skills = request.POST.get('skills')

        try:
            AuthService.register_freelancer(username, email, password, full_name, skills)
            messages.success(request, "Freelancer account created successfully! Please log in.")
            return redirect('login')
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

    return render(request, 'core/freelancer_register.html')


def verify_email(request, uidb64, token):
    success, message = AuthService.verify_email(uidb64, token)
    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)
    return redirect('login')
