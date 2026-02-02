import uuid
import decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from .forms import SkillsForm, ProjectForm, ClientRegistrationForm, ClientProfileForm, TopUpForm, WithdrawForm, SecurePinForm, PaymentPinForm
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
from .models import Client, Freelancer, Project, Milestone, ProjectCategory, Industry, Wallet, Transaction, UserSecurity, Escrow, ProjectMatch, Conversation, ChatParticipant, Message
from django.contrib.auth.hashers import make_password, check_password
from django.db import transaction
from .decorators import client_required, freelancer_required, guest_required
from django.utils import timezone

# Create your views here.
# Auth part
@guest_required
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

        # Check if user is inactive but has correct password
        if not user.is_active and user.check_password(password):
            messages.error(request, "Please verify your email before login")
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

        # Remember Me Logic
        if request.POST.get('remember_me'):
            request.session.set_expiry(1209600) # 2 weeks (for tick then login)
        else:
            request.session.set_expiry(0) # Expires when browser closes (for untick then login)

        if role == "client":
            return redirect("client_home")
        else:
            return redirect("freelancer_home") 

    return render(request, "core/login.html")

@login_required
def logout(request):
    auth_logout(request)
    return redirect('home')

@guest_required
def registerSelection(request):
    return render(request, "core/registerSelection.html")

@guest_required
def register_client(request):
    if request.method == 'POST':
        form = ClientRegistrationForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Save form (creates User and Client)
                    client = form.save()

                    # Create Wallet for the new client
                    wallet_number = str(uuid.uuid4()).replace('-', '')[:16].upper() # Generate unique ID
                    Wallet.objects.create(
                        user=client.user,
                        wallet_number=wallet_number,
                        balance=0.00,
                        currency='RM',
                        status='active'
                    )
                    
                    # Send email verification
                    current_site = get_current_site(request)
                    verify_url = reverse('verify_email', kwargs={
                        'uidb64': urlsafe_base64_encode(force_bytes(client.user.pk)),
                        'token': client.email_verification_token
                    })
                    
                    verify_link = f"http://{current_site.domain}{verify_url}"
                    email_subject = "Verify Your Email Address"

                    email_body = render_to_string('emails/verification_email.html', {
                        'user': client.user,
                        'verify_link': verify_link,
                    })

                    email = EmailMessage(
                        email_subject,
                        email_body,
                        settings.DEFAULT_FROM_EMAIL,
                        [client.user.email],
                    )
                    email.content_subtype = "html"
                    email.send(fail_silently=False)

                messages.success(request, "Registration successful! Please check your email to verify your account.")
                return redirect('login')

            except Exception as e:
                messages.error(request, f"An error occurred during registration: {str(e)}")
        else:
             # Form invalid, errors are in form.errors
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
            user = User.objects.create_user(username=username, email=email, password=password)
            freelancer = Freelancer.objects.create(
                user=user,
                full_name=full_name,
                skills=skills
            )
            # Auto-create wallet as per friend's comment
            Wallet.objects.create(user=user, balance=0.00)  # Assuming Wallet has user and balance fields
            messages.success(request, "Freelancer account and wallet created successfully! Please log in.")
            return redirect('login')
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
    
    return render(request, 'core/freelancer_register.html')

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

# Guest part
@guest_required
def home(request):
    return render(request, 'core/home.html')

# Client part 

@client_required
def client_home(request):
    return render(request, 'core/client_home.html')

@client_required
def client_search(request):
    query = request.GET.get('q', '')
    rating_filter = request.GET.get('rating')
    avail_filter = request.GET.get('availability')

    # Start with all freelancers
    from django.db.models import Q
    freelancers = Freelancer.objects.all()

    # 1. Search Query (Multi-term support)
    if query:
        search_terms = query.split()
        for term in search_terms:
            freelancers = freelancers.filter(
                Q(full_name__icontains=term) | 
                Q(skills__icontains=term) |
                Q(tagline__icontains=term) |
                Q(user__username__icontains=term)
            )

    # 2. Rating Filter
    if rating_filter:
        try:
            min_rating = float(rating_filter)
            freelancers = freelancers.filter(average_rating__gte=min_rating)
        except ValueError:
            pass
            
    # 3. Availability Filter
    if avail_filter:
        freelancers = freelancers.filter(availability_status=avail_filter)
        
    # 4. Pagination
    paginator = Paginator(freelancers, 10) # 10 records per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
        
    context = {
        'freelancers': page_obj, # Pass page_obj instead of QuerySet
        'query': query,
        'current_rating': rating_filter,
        'current_avail': avail_filter,
        'has_filter': bool(rating_filter or avail_filter)
    }
    
    return render(request, 'core/client_search.html', context)

@client_required
def client_freelancerProfile(request, freelancer_id):
    freelancer = get_object_or_404(Freelancer, id=freelancer_id)
    return render(request, 'core/client_freelancerProfile.html', {'freelancer': freelancer})

def client_about(request):
    return render(request, 'core/client_about.html')

@client_required
def client_settings(request):
    user_security, created = UserSecurity.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = SecurePinForm(request.POST, user_security=user_security)
        if form.is_valid():
            new_pin = form.cleaned_data['new_pin']
            user_security.secure_pin = make_password(new_pin)
            user_security.save()
            messages.success(request, "Secure PIN updated successfully.")
            return redirect('client_settings')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = SecurePinForm(user_security=user_security)

    return render(request, 'core/client_settings.html', {'form': form})

# Client part (profile)

@client_required
def client_profile(request):
    return render(request, 'core/client_profile.html')

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
            messages.error(request, "Please correct the errors below.")
            for field, errors in form.errors.items():
                for error in errors:
                     messages.error(request, f"{field}: {error}")
    else:
        form = ClientProfileForm(instance=client)

    return render(request, 'core/client_editProfile.html', {'form': form})

# Client part (wallet)
@client_required
def client_wallet(request):
    wallet = getattr(request.user, 'wallet', None)
    recent_transactions = []
    if wallet:
        recent_transactions = Transaction.objects.filter(wallet=wallet).order_by('-created_at')[:5]
    
    return render(request, 'core/client_wallet.html', {
        'wallet': wallet,
        'recent_transactions': recent_transactions
    })

@login_required
def topUp(request):
    # Determine user role and base template
    if hasattr(request.user, 'client'):
        base_template = 'core/client_master.html'
    elif hasattr(request.user, 'freelancer'):
        base_template = 'core/freelancer_master.html'
    else:
        messages.error(request, "User role not identified.")
        return redirect('home')

    if request.method == 'POST':
        form = TopUpForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            payment_method_str = form.cleaned_data['payment_method']
            
            try:
                with transaction.atomic():
                    # Get or Create Wallet
                    wallet, created = Wallet.objects.get_or_create(user=request.user)
                    if created:
                        wallet.wallet_number = str(uuid.uuid4()).replace('-', '')[:16].upper()
                        wallet.save()

                    # Create Transaction
                    method_display = payment_method_str.replace('_', ' ').title()
                    
                    Transaction.objects.create(
                        wallet=wallet,
                        amount=amount,
                        direction='credit',
                        transaction_type='top_up',
                        status='completed',
                        description=f"Top up via {method_display}",
                        reference_id=str(uuid.uuid4()).replace('-', '')[:12].upper()
                    )

                    # Update Balance
                    wallet.balance += decimal.Decimal(amount)
                    wallet.save()

                messages.success(request, f"Successfully topped up RM {amount:.2f} via {method_display}!")
                
                if hasattr(request.user, 'client'):
                    return redirect('client_wallet')
                else:
                    return redirect('freelancer_home')

            except Exception as e:
                messages.error(request, f"An error occurred: {str(e)}")
        else:
             for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            
    return render(request, 'core/topUp.html', {'base_template': base_template})

@login_required
def withdraw(request):
    # Determine user role and base template
    if hasattr(request.user, 'client'):
        base_template = 'core/client_master.html'
    elif hasattr(request.user, 'freelancer'):
        base_template = 'core/freelancer_master.html'
    else:
        messages.error(request, "User role not identified.")
        return redirect('home')
        
    wallet = getattr(request.user, 'wallet', None)

    if request.method == 'POST':
        form = WithdrawForm(request.POST, wallet=wallet)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            bank_name = form.cleaned_data['bank_name']
            account_number = form.cleaned_data['account_number']
            
            try:
                with transaction.atomic():
                    if not wallet:
                         # Should be caught by validation, but double check
                         raise ValueError("Wallet does not exist")

                    # Deduct Balance
                    wallet.balance -= decimal.Decimal(amount)
                    wallet.save()

                    # Create Transaction
                    Transaction.objects.create(
                        wallet=wallet,
                        amount=amount,
                        direction='debit',
                        transaction_type='withdrawal',
                        status='pending', # Withdrawals usually require processing
                        description=f"Withdrawal to {bank_name} ({account_number})",
                        reference_id=str(uuid.uuid4()).replace('-', '')[:12].upper()
                    )

                messages.success(request, f"Withdrawal request for RM {amount:.2f} submitted successfully!")
                
                if hasattr(request.user, 'client'):
                    return redirect('client_wallet')
                else:
                    return redirect('freelancer_home')

            except Exception as e:
                messages.error(request, f"An error occurred: {str(e)}")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{error}")
    
    return render(request, 'core/withdraw.html', {'base_template': base_template, 'wallet': wallet})

@client_required
def client_transaction(request):
    wallet = getattr(request.user, 'wallet', None)
    transactions = []
    
    # 1. Base Query
    if wallet:
        transactions_qs = Transaction.objects.filter(wallet=wallet)
        
        # 2. Filtering
        filter_type = request.GET.get('type')
        if filter_type:
             # Map URL param to model value if different, or use direct if same
             # Frontend uses human readable or matching keys: 'top_up', 'withdrawal', 'payment', 'refund'
             valid_types = ['top_up', 'withdrawal', 'payment', 'refund']
             if filter_type in valid_types:
                 transactions_qs = transactions_qs.filter(transaction_type=filter_type)
        
        # 3. Sorting
        sort_by = request.GET.get('sort', 'newest') # default newest
        if sort_by == 'oldest':
            transactions_qs = transactions_qs.order_by('created_at')
        elif sort_by == 'highest':
            transactions_qs = transactions_qs.order_by('-amount')
        else:
            transactions_qs = transactions_qs.order_by('-created_at') # Newest default
            
        # 4. Pagination
        paginator = Paginator(transactions_qs, 8) # 8 records per page
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        transactions = page_obj
    else:
        page_obj = None

    return render(request, 'core/client_transaction.html', {
        'wallet': wallet,
        'transactions': transactions, # This is actually page_obj
        'page_obj': page_obj,
        'current_type': request.GET.get('type', ''),
        'current_sort': request.GET.get('sort', 'newest'),
    })

@login_required
def toggle_balance_privacy(request):
    if request.method == "POST":
        wallet = getattr(request.user, 'wallet', None)
        if wallet:
            wallet.is_hidden = not wallet.is_hidden
            wallet.save()
            return JsonResponse({'status': 'success', 'is_hidden': wallet.is_hidden})
    return JsonResponse({'status': 'error'}, status=400)

# Client part (project)

@client_required
def client_project(request):
    projects = Project.objects.filter(client=request.user.client).order_by('-created_at')
    
    # Calculate summary statistics
    active_count = projects.filter(status='open').count()
    completed_count = projects.filter(status='completed').count()
    in_progress_count = projects.filter(status='in_progress').count()
    
    # Calculate total spent (exclude draft projects)
    from django.db.models import Sum
    total_spent = projects.exclude(status='draft').aggregate(Sum('budget'))['budget__sum'] or 0
    
    return render(request, 'core/client_project.html', {
        'projects': projects,
        'active_count': active_count,
        'completed_count': completed_count,
        'in_progress_count': in_progress_count,
        'total_spent': total_spent,
    })

@client_required
def client_projectCreate(request):
    categories = ProjectCategory.objects.all()
    
    if request.method == 'POST':
        form = ProjectForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # 1. Create Project
                    project = form.save(commit=False)
                    project.client = request.user.client
                    project.status = 'draft'
                    
                    # 2. Get Milestones Data
                    m_titles = request.POST.getlist('milestone_title[]')
                    m_descriptions = request.POST.getlist('milestone_description[]')
                    m_amounts = request.POST.getlist('milestone_amount[]')
                    m_deadlines = request.POST.getlist('milestone_deadline[]')

                    project.save()
                    
                    # Create Milestones
                    for i in range(len(m_titles)):
                        if m_titles[i] and m_amounts[i] and m_deadlines[i]:
                            Milestone.objects.create(
                                project=project,
                                title=m_titles[i],
                                description=m_descriptions[i] if i < len(m_descriptions) else '',
                                amount=m_amounts[i],
                                deadline=m_deadlines[i],
                                order=i+1
                            )

                messages.success(request, "Project created successfully! You can publish it once you are ready.")
                return redirect('client_project')
            except Exception as e:
                messages.error(request, f"Error creating project: {str(e)}")
        else:
            # Show specific form errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = ProjectForm()

    return render(request, 'core/client_projectCreate.html', {
        'form': form,
        'categories': categories # Still passed for reference or manual iteration if needed, though form handles it
    })

@client_required
def client_projectInfo(request, project_id):
    project = Project.objects.get(id=project_id, client=request.user.client)
    return render(request, 'core/client_projectInfo.html', {'project': project})

@client_required
def client_projectMatches(request, project_id):
    project = get_object_or_404(Project, id=project_id, client=request.user.client)
    
    if request.GET.get('refresh'):
         from .ai_matching import MatchEngine
         engine = MatchEngine()
         engine.compute_matches(project.id)
         # Redirect to base path to clean url
         return redirect('client_projectMatches', project_id=project.id)

    matches = project.matches.select_related('freelancer').all()
    
    # If no matches exist and status is open, try running once automatically
    if not matches.exists() and project.status == 'open':
         from .ai_matching import MatchEngine
         engine = MatchEngine()
         engine.compute_matches(project.id)
         matches = project.matches.select_related('freelancer').all()

    return render(request, 'core/client_projectMatches.html', {
        'project': project,
        'matches': matches
    })

@client_required
def client_projectEdit(request, project_id):
    project = Project.objects.get(id=project_id, client=request.user.client)

    experience_5_plus = project.year_of_experience >= 5
    
    # Only allow editing draft projects
    if project.status != 'draft':
        messages.error(request, "Only draft projects can be edited.")
        return redirect('client_projectInfo', project_id=project.id)
    
    categories = ProjectCategory.objects.all()
    
    if request.method == 'POST':
        form = ProjectForm(request.POST, request.FILES, instance=project)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Update Project
                    project = form.save(commit=False)
                    project.client = request.user.client
                    project.status = 'draft'
                    
                    # Get Milestones Data
                    m_titles = request.POST.getlist('milestone_title[]')
                    m_descriptions = request.POST.getlist('milestone_description[]')
                    m_amounts = request.POST.getlist('milestone_amount[]')
                    m_deadlines = request.POST.getlist('milestone_deadline[]')

                    project.save()
                    
                    # Delete existing milestones and create new ones
                    project.milestones.all().delete()
                    
                    # Create new Milestones
                    for i in range(len(m_titles)):
                        if m_titles[i] and m_amounts[i] and m_deadlines[i]:
                            Milestone.objects.create(
                                project=project,
                                title=m_titles[i],
                                description=m_descriptions[i] if i < len(m_descriptions) else '',
                                amount=m_amounts[i],
                                deadline=m_deadlines[i],
                                order=i+1
                            )

                messages.success(request, "Project updated successfully!")
                return redirect('client_projectInfo', project_id=project.id)
            except Exception as e:
                messages.error(request, f"Error updating project: {str(e)}")
        else:
            # Show specific form errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = ProjectForm(instance=project)

    return render(request, 'core/client_projectEdit.html', {
        'form': form,
        'project': project,
        'categories': categories,
        'experience_5_plus': experience_5_plus
    })

@client_required
def client_projectDelete(request, project_id):
    project = Project.objects.get(id=project_id, client=request.user.client)
    
    # Check if project is draft
    if project.status != 'draft':
        messages.error(request, "Only draft projects can be deleted.")
        return redirect('client_projectInfo', project_id=project.id)
    
    if request.method == 'POST':
        try:
            project.delete()
            messages.success(request, "Project deleted successfully.")
            return redirect('client_project')
        except Exception as e:
            messages.error(request, f"Error deleting project: {str(e)}")
            return redirect('client_projectInfo', project_id=project.id)
            
    return redirect('client_projectInfo', project_id=project.id)

@client_required
def client_projectPublish(request, project_id):
    """Display payment confirmation page for publishing a project"""
    project = get_object_or_404(Project, id=project_id, client=request.user.client)
    
    # Only allow publishing draft projects
    if project.status != 'draft':
        messages.error(request, "Only draft projects can be published.")
        return redirect('client_projectInfo', project_id=project.id)
    
    # Check if user has set up secure PIN
    user_security = getattr(request.user, 'security', None)
    if not user_security or not user_security.secure_pin:
        messages.warning(request, "Please set up your Secure PIN before publishing a project.")
        return redirect('client_settings')
    
    # Get wallet and check balance
    wallet = getattr(request.user, 'wallet', None)
    if not wallet:
        messages.error(request, "Wallet not found. Please contact support.")
        return redirect('client_projectInfo', project_id=project.id)
    
    # Get milestones
    milestones = project.milestones.all().order_by('order')
    
    # Check if sufficient balance
    has_sufficient_balance = wallet.balance >= project.budget
    
    # Calculate balance after payment and amount needed
    balance_after_payment = wallet.balance - project.budget
    amount_needed = project.budget - wallet.balance if not has_sufficient_balance else decimal.Decimal('0.00')
    
    context = {
        'project': project,
        'milestones': milestones,
        'wallet': wallet,
        'has_sufficient_balance': has_sufficient_balance,
        'balance_after_payment': balance_after_payment,
        'amount_needed': amount_needed,
        'form': PaymentPinForm()
    }
    
    return render(request, 'core/client_projectPublish.html', context)

@client_required
def client_confirmPayment(request, project_id):
    """Process payment and publish project"""
    if request.method != 'POST':
        return redirect('client_projectPublish', project_id=project_id)
    
    project = get_object_or_404(Project, id=project_id, client=request.user.client)
    
    # Only allow publishing draft projects
    if project.status != 'draft':
        messages.error(request, "Only draft projects can be published.")
        return redirect('client_projectInfo', project_id=project.id)
    
    # Get user security
    user_security = getattr(request.user, 'security', None)
    if not user_security or not user_security.secure_pin:
        messages.error(request, "Secure PIN not set up.")
        return redirect('client_settings')
    
    # Validate PIN
    form = PaymentPinForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please enter a valid 6-digit PIN.")
        return redirect('client_projectPublish', project_id=project_id)
    
    entered_pin = form.cleaned_data['secure_pin']
    if not check_password(entered_pin, user_security.secure_pin):
        messages.error(request, "Incorrect Secure PIN. Please try again.")
        return redirect('client_projectPublish', project_id=project_id)
    
    # Get wallet
    wallet = getattr(request.user, 'wallet', None)
    if not wallet:
        messages.error(request, "Wallet not found.")
        return redirect('client_projectInfo', project_id=project.id)
    
    # Check balance
    if wallet.balance < project.budget:
        messages.error(request, f"Insufficient balance. You need RM {project.budget - wallet.balance:.2f} more.")
        return redirect('client_projectPublish', project_id=project_id)
    
    # Process payment with database transaction
    try:
        with transaction.atomic():
            # Deduct from wallet
            wallet.balance -= project.budget
            wallet.save()
            
            # Create transaction record
            Transaction.objects.create(
                wallet=wallet,
                amount=project.budget,
                direction='debit',
                transaction_type='payment',
                status='completed',
                description=f"Payment for project: {project.title}",
                reference_id=str(uuid.uuid4()).replace('-', '')[:12].upper(),
                related_project=project
            )
            
            # Create escrow
            Escrow.objects.create(
                project=project,
                total_amount=project.budget,
                released_amount=decimal.Decimal('0.00'),
                remaining_amount=project.budget,
                status='active'
            )
            
            # Update project status
            project.status = 'open'
            project.published_at = timezone.now()
            project.save()
        
        messages.success(request, f"Project '{project.title}' published successfully! RM {project.budget:.2f} has been placed in escrow.")
        return redirect('client_projectInfo', project_id=project.id)
        
    except Exception as e:
        messages.error(request, f"An error occurred while processing payment: {str(e)}")
        return redirect('client_projectPublish', project_id=project_id)

# idk what is this part

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

# Freelancer part

@freelancer_required
def freelancer_home(request):
    return render(request, 'core/freelancer_home.html')


# Chat Functionality (for both client and freelancer)

@login_required
def chat_view(request):
    context = {}
    if hasattr(request.user, 'client'):
        context['base_template'] = 'core/client_master.html'
        context['find_url'] = 'client_search' # URL name for finding freelancers
        context['find_text'] = 'Find Freelancers'
        context['dashboard_url'] = 'client_home'
    elif hasattr(request.user, 'freelancer'):
        context['base_template'] = 'core/freelancer_master.html'
        context['find_url'] = 'home' # Freelancers might search for jobs/projects. For now pointing to home or a project search view if it exists.
        # Assuming there is no 'freelancer_project_search' yet, let's use 'home' or a placeholder.
        # Actually user might not have a project search yet. Let's use 'freelancer_home'.
        context['find_text'] = 'Find Jobs' 
        context['dashboard_url'] = 'freelancer_home'
        # Note: If no specific job search view exists, maybe point to dashboard
    else:
        # Fallback for admin or other
        context['base_template'] = 'core/master.html'
        context['find_url'] = 'home'
        context['find_text'] = 'Go Home'
        
    return render(request, 'core/chat.html', context)

@login_required
def start_chat(request, user_id):
    other_user = get_object_or_404(User, id=user_id)
    if other_user == request.user:
        messages.error(request, "You cannot chat with yourself.")
        return redirect('client_search') # Or dashboard

    # Check for existing conversation
    # Filter conversations where both users are participants
    my_convs = Conversation.objects.filter(participants=request.user)
    common_convs = my_convs.filter(participants=other_user).distinct()
    
    if common_convs.exists():
        conversation = common_convs.first()
    else:
        # Create new conversation
        conversation = Conversation.objects.create()
        ChatParticipant.objects.create(user=request.user, conversation=conversation)
        ChatParticipant.objects.create(user=other_user, conversation=conversation)
    
    # Redirect to chat view with conversation ID (we'll handle opening it in JS via query param)
    return redirect(reverse('chat') + f'?conversation_id={conversation.id}')

@login_required
def api_get_conversations(request):
    participants = ChatParticipant.objects.filter(user=request.user).select_related('conversation')
    data = []
    
    for p in participants:
        conv = p.conversation
        # Get other participant
        other_participant = conv.participants.exclude(id=request.user.id).first()
        if not other_participant:
            continue
            
        last_message = conv.messages.last()
        
        # Determine name and avatar based on role
        name = other_participant.username
        avatar_url = '/static/core/images/default_profile.png' # Fallback
        
        if hasattr(other_participant, 'client'):
            name = other_participant.client.company_name or other_participant.username
            if other_participant.client.profile_image:
                avatar_url = other_participant.client.profile_image.url
        elif hasattr(other_participant, 'freelancer'):
            name = other_participant.freelancer.full_name or other_participant.username
            if other_participant.freelancer.profile_image:
                avatar_url = other_participant.freelancer.profile_image.url
        
        data.append({
            'id': conv.id,
            'other_user_id': other_participant.id,
            'name': name,
            'avatar': avatar_url,
            'last_message': last_message.content if last_message else '',
            'last_message_time': last_message.created_at.isoformat() if last_message else conv.created_at.isoformat(),
            'is_muted': p.is_muted
        })
        
    # Sort by updated_at (or last message time)
    data.sort(key=lambda x: x['last_message_time'], reverse=True)
    return JsonResponse(data, safe=False)

@login_required
def api_get_messages(request, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id)
    if not conversation.participants.filter(id=request.user.id).exists():
        return JsonResponse({'error': 'Unauthorized'}, status=403)
        
    messages_qs = conversation.messages.select_related('sender').all()
    data = []
    
    for msg in messages_qs:
        sender_name = "Me"
        if msg.sender != request.user:
            if hasattr(msg.sender, 'client'):
                 sender_name = msg.sender.client.company_name
            elif hasattr(msg.sender, 'freelancer'):
                 sender_name = msg.sender.freelancer.full_name
                 
        sender_avatar = '/static/core/images/default_profile.png'
        if hasattr(msg.sender, 'client') and msg.sender.client.profile_image:
             sender_avatar = msg.sender.client.profile_image.url
        elif hasattr(msg.sender, 'freelancer') and msg.sender.freelancer.profile_image:
             sender_avatar = msg.sender.freelancer.profile_image.url
             
        data.append({
            'id': msg.id,
            'sender_id': msg.sender.id,
            'is_me': msg.sender == request.user,
            'sender_name': sender_name,
            'sender_avatar': sender_avatar,
            'content': msg.content,
            'created_at': msg.created_at.isoformat(),
            'is_read': msg.is_read
        })
        
    return JsonResponse(data, safe=False)

@login_required
def api_send_message(request, conversation_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
        
    import json
    try:
        data = json.loads(request.body)
        content = data.get('content')
        
        if not content:
             return JsonResponse({'error': 'Content is required'}, status=400)
             
        conversation = get_object_or_404(Conversation, id=conversation_id)
        if not conversation.participants.filter(id=request.user.id).exists():
            return JsonResponse({'error': 'Unauthorized'}, status=403)
            
        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            content=content
        )
        # Touch updated_at
        conversation.save()
        
        return JsonResponse({'status': 'success', 'message_id': message.id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
def api_toggle_mute(request, conversation_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
        
    participant = get_object_or_404(ChatParticipant, conversation_id=conversation_id, user=request.user)
    participant.is_muted = not participant.is_muted
    participant.save()
    
    return JsonResponse({'status': 'success', 'is_muted': participant.is_muted})

