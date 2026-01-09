import uuid
from django.shortcuts import render, redirect
from .forms import SkillsForm  # ← Add this (we'll create forms.py next)
from .models import Job        # ← Add this
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib import messages
from django.contrib.sites.shortcuts import get_current_site
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.contrib import messages
from django.conf import settings
from django.urls import reverse
from .models import Client
from django.db import transaction
from .decorators import client_required, freelancer_required

# Create your views here.
def login(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        role = request.POST.get("role")  # client / freelancer

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            messages.error(request, "Invalid email or password")
            return redirect("login")

        user = authenticate(request, username=user.username, password=password)

        if user is None:
            messages.error(request, "Invalid email or password")
            return redirect("login")

        # ROLE VALIDATION
        if role == "client" and not hasattr(user, "client"):
            messages.error(request, "This account is not registered as a Client")
            return redirect("login")

        if role == "freelancer" and not hasattr(user, "freelancer"):
            messages.error(request, "This account is not registered as a Freelancer")
            return redirect("login")

        # SUCCESS
        auth_login(request, user)

        if role == "client":
            return redirect("client_home")
        else:
            return redirect("freelancer_home") 

    return render(request, "core/login.html")

def register_client(request):
    # GET request: Show form (possibly with preserved data)
    if request.method == 'GET':
        # Try to get preserved form data from session
        form_data = request.session.pop('register_form_data', {})
        return render(request, 'core/client_register.html', {'form_data': form_data})

    # POST request: Process form
    if request.method == 'POST':
        # Extract data
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        full_name = request.POST.get('name', '').strip()
        company_name = request.POST.get('company', '').strip()
        phone = request.POST.get('phone', '').strip()
        industry_type = request.POST.get('industry', '')

        # Prepare data to repopulate form on error
        form_data = {
            'name': full_name,
            'email': email,
            'phone': phone,
            'company': company_name,
            'industry': industry_type,
        }

        # Basic validation
        if User.objects.filter(email=email).exists():
            messages.error(request, 'This email is already registered.')
            request.session['register_form_data'] = form_data
            return redirect('register_client')

        if not all([email, password, full_name, company_name, phone, industry_type]):
            messages.error(request, 'Please fill in all required fields.')
            request.session['register_form_data'] = form_data
            return redirect('register_client')

        # Atomic transaction for all-or-nothing
        try:
            with transaction.atomic():
                # Create inactive user
                user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=password,
                    first_name=full_name.split()[0] if full_name else '',
                    last_name=' '.join(full_name.split()[1:]) if len(full_name.split()) > 1 else '',
                    is_active=False
                )

                # Default images
                default_profile_path = 'core/media/clients/profiles/default_profile.png'
                default_background_path = 'core/media/clients/backgrounds/default_background.jpg'

                # Create Client profile
                client = Client.objects.create(
                    user=user,
                    company_name=company_name,
                    phone=phone,
                    industry_type=industry_type,
                    profile_image=default_profile_path,
                    background_image=default_background_path,
                )

                # Generate token
                token = str(uuid.uuid4())
                client.email_verification_token = token
                client.save()

                # Send email
                current_site = get_current_site(request)
                verify_url = reverse('verify_email', kwargs={
                    'uidb64': urlsafe_base64_encode(force_bytes(user.pk)),
                    'token': token
                })
                full_verify_link = f"{request.scheme}://{current_site.domain}{verify_url}"

                mail_subject = 'Activate Your Freelance Platform Account'
                message = render_to_string('emails/verification_email.html', {
                    'user': user,
                    'company_name': company_name,
                    'verify_link': full_verify_link,
                })

                email_msg = EmailMessage(
                    mail_subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [email],
                )
                email_msg.content_subtype = "html"
                email_msg.send()

            # SUCCESS → Clear any session data and redirect
            messages.success(request, 'Registration successful! Please check your email to verify your account.')
            return redirect('login')

        except Exception as e:
            messages.error(request, 'Registration failed. Please try again later.')
            print(f"Registration error: {e}")
            request.session['register_form_data'] = form_data  # ← Preserve on exception
            return redirect('register_client')

def verify_email(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
        client = Client.objects.get(user=user)

        if client.email_verification_token == token:
            user.is_active = True
            user.save()
            client.is_email_verified = True
            client.email_verification_token = ''
            client.save()

            messages.success(request, 'Email verified successfully! You can now log in.')
            return redirect('login')
        else:
            messages.error(request, 'Invalid or expired verification link.')
    except (TypeError, ValueError, OverflowError, User.DoesNotExist, Client.DoesNotExist):
        messages.error(request, 'Invalid verification link.')

    return redirect('login')

def client_home(request):
    return render(request, 'core/client_home.html')

def client_profile(request):
    return render(request, 'core/client_profile.html')

def client_editProfile(request):
    return render(request, 'core/client_editProfile.html')

def client_project(request):
    return render(request, 'core/client_project.html')

def client_projectCreate(request):
    return render(request, 'core/client_projectCreate.html')

def client_projectInfo(request):
    return render(request, 'core/client_projectInfo.html')

def client_about(request):
    return render(request, 'core/client_about.html')

def client_chat(request):
    return render(request, 'core/client_chat.html')

def match_jobs(request):
    """
    AI-Powered Job Matching Demo
    Freelancer enters skills → System returns ranked job matches with relevance scores
    Uses TF-IDF + Cosine Similarity (foundation for future BERT upgrade)
    """
    form = SkillsForm()
    results = []
    query = ""

    if request.method == 'POST':
        form = SkillsForm(request.POST)
        if form.is_valid():
            query = form.cleaned_data['skills'].strip()

            if query:
                # Get all jobs from database
                jobs = Job.objects.all()

                if jobs.exists():
                    # Prepare documents: job descriptions + freelancer skills
                    job_descriptions = [job.description for job in jobs]
                    documents = job_descriptions + [query]

                    # Vectorize using TF-IDF
                    vectorizer = TfidfVectorizer(stop_words='english', lowercase=True)
                    tfidf_matrix = vectorizer.fit_transform(documents)

                    # Compute similarity between freelancer skills (last vector) and all jobs
                    query_vector = tfidf_matrix[-1]  # Last row = user's skills
                    job_vectors = tfidf_matrix[:-1]

                    cosine_similarities = cosine_similarity(query_vector, job_vectors).flatten()

                    # Create results list
                    for idx, job in enumerate(jobs):
                        score = cosine_similarities[idx]
                        if score > 0.05:  # Filter very low matches
                            results.append({
                                'job': job,
                                'score': round(score * 100, 2),  # Convert to percentage
                                'snippet': job.description[:200] + "..." if len(job.description) > 200 else job.description
                            })

                    # Sort by relevance (highest first)
                    results.sort(key=lambda x: x['score'], reverse=True)

    context = {
        'form': form,
        'results': results,
        'query': query,
        'title': 'AI-Powered Job Matching Results'
    }

    return render(request, 'core/match.html', {'form': form, 'results': results})

def home(request):
    if request.method == 'POST':
        role = request.POST.get('role')
        # Simulate successful login (no real check)
        if role == 'freelancer':
            return render(request, 'core/freelancer_home.html')  # New freelancer UI
        else:
            return render(request, 'core/client_home.html')  # Existing client UI
    # GET: Show login page (home.html)
    return render(request, 'core/home.html')

def logout(request):
    auth_logout(request)
    return redirect('home')