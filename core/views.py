import uuid
import decimal
import stripe
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, FileResponse, Http404
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .forms import SkillsForm, ProjectForm, ClientRegistrationForm, ClientProfileForm, TopUpForm, WithdrawForm, SecurePinForm, PaymentPinForm, FreelancerProfileForm, FreelancerPortfolioForm, FreelancerWorkExperienceForm, FreelancerCertificationForm, FreelancerHeaderForm, FreelancerRateForm, FreelancerBackgroundForm, FreelancerSocialForm, FreelancerBioForm, FreelancerSkillsForm, FreelancerLanguageForm, ReviewForm, SupportForm
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
from .models import Client, Freelancer, Project, Milestone, ProjectCategory, Industry, Wallet, Transaction, UserSecurity, Escrow, ProjectMatch, Conversation, ChatParticipant, Message, FreelancerPortfolio, FreelancerWorkExperience, FreelancerCertification, Review, RatingSummary, Ticket, AdminLog
from django.contrib.auth.hashers import make_password, check_password
from django.db import transaction
from django.db.models import Q, ProtectedError
from .decorators import client_required, freelancer_required, guest_required, admin_required
from django.utils import timezone
from .ai_utils import AISearchManager, get_recommendations

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

def admin_login(request):
    """Admin login - for superusers and staff"""
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
                
                # Log admin login
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
    freelancers = Freelancer.objects.select_related('user__rating_summary').all()

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
            freelancers = freelancers.filter(user__rating_summary__average_rating__gte=min_rating)
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
def client_support(request):
    if request.method == 'POST':
        form = SupportForm(request.POST, user=request.user)
        if form.is_valid():
            # Create a ticket in the database
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

    return render(request, 'core/client_support.html', {'form': form})


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
    stripe.api_key = settings.STRIPE_SECRET_KEY

    # Determine user role and base template
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
            
            with transaction.atomic():
                wallet, created = Wallet.objects.get_or_create(user=request.user)
                if created:
                    wallet.wallet_number = str(uuid.uuid4()).replace('-', '')[:16].upper()
                    wallet.save()

                reference_id = str(uuid.uuid4()).replace('-', '')[:12].upper()
                
                # Create pending transaction
                txn = Transaction.objects.create(
                    wallet=wallet,
                    amount=amount,
                    direction='credit',
                    transaction_type='top_up',
                    status='pending',
                    description="Wallet Top Up via Stripe",
                    reference_id=reference_id
                )
            
            # Create Stripe Checkout Session
            domain_url = request.build_absolute_uri('/')[:-1] # Remove trailing slash
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'myr',
                        'product_data': {
                            'name': 'Wallet Top Up',
                            'description': 'Add funds to your TalentSync Wallet',
                        },
                        'unit_amount': int(amount * 100), # Amount in cents
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=domain_url + reverse('payment_success') + '?session_id={CHECKOUT_SESSION_ID}',
                cancel_url=domain_url + reverse('payment_cancel'),
                client_reference_id=txn.reference_id,
            )
            return redirect(session.url)
            
        except Exception as e:
            messages.error(request, f"An error occurred: {str(e)}")
            return redirect('topUp')

    return render(request, 'core/topUp.html', {'base_template': base_template})

@login_required
def payment_success(request):
    session_id = request.GET.get('session_id')
    
    if session_id:
        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            client_reference_id = session.get('client_reference_id')
            
            # If the session is complete and paid, fulfill the order
            if session.payment_status == 'paid' and client_reference_id:
                try:
                    txn = Transaction.objects.get(reference_id=client_reference_id, status='pending')
                    with transaction.atomic():
                        txn.status = 'completed'
                        txn.save()
                        
                        wallet = txn.wallet
                        wallet.balance += txn.amount
                        wallet.save()
                    messages.success(request, "Payment successful! Your wallet balance has been updated.")
                except Transaction.DoesNotExist:
                    # Transaction already processed or doesn't exist
                    messages.success(request, "Payment successful!")
            else:
                messages.warning(request, "Payment is still processing.")
        except Exception as e:
            messages.error(request, "Could not verify payment status.")
    else:
        messages.success(request, "Payment successful!")
        
    if hasattr(request.user, 'client'):
        return redirect('client_wallet')
    else:
        return redirect('freelancer_wallet')

@login_required
def payment_cancel(request):
    messages.warning(request, "Payment is pending. Please continue to pay for the transaction.")
    return redirect('topUp')

@login_required
def payment_cancel_pending(request, transaction_id):
    if request.method == 'POST':
        wallet = get_object_or_404(Wallet, user=request.user)
        txn = get_object_or_404(Transaction, id=transaction_id, wallet=wallet)
        
        if txn.status == 'pending' and txn.transaction_type == 'top_up':
            txn.status = 'cancelled'
            txn.save()
            messages.success(request, "Pending top up has been cancelled.")
        else:
            messages.error(request, "This transaction cannot be cancelled.")
            
    # Redirect back to where they came from, or wallet default
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
        
    if hasattr(request.user, 'client'):
        return redirect('client_wallet')
    else:
        return redirect('freelancer_wallet')

@login_required
def payment_continue(request, transaction_id):
    stripe.api_key = settings.STRIPE_SECRET_KEY
    wallet = get_object_or_404(Wallet, user=request.user)
    txn = get_object_or_404(Transaction, id=transaction_id, wallet=wallet)
    
    if txn.status != 'pending' or txn.transaction_type != 'top_up':
        messages.error(request, "This transaction cannot be continued.")
        if hasattr(request.user, 'client'):
            return redirect('client_wallet')
        else:
            return redirect('freelancer_wallet')
            
    try:
        domain_url = request.build_absolute_uri('/')[:-1]
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'myr',
                    'product_data': {
                        'name': 'Wallet Top Up',
                        'description': 'Add funds to your TalentSync Wallet',
                    },
                    'unit_amount': int(txn.amount * 100),
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=domain_url + reverse('payment_success') + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=domain_url + reverse('payment_cancel'),
            client_reference_id=txn.reference_id,
        )
        return redirect(session.url)
    except Exception as e:
        messages.error(request, f"An error occurred with the payment gateway: {str(e)}")
        if hasattr(request.user, 'client'):
            return redirect('client_wallet')
        else:
            return redirect('freelancer_wallet')

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
            messages.error(request, "Please correct the errors below.")
    else:
        form = ProjectForm()

    return render(request, 'core/client_projectCreate.html', {
        'form': form
    })

@client_required
def client_projectInfo(request, project_id):
    project = Project.objects.get(id=project_id, client=request.user.client)
    
    review = None
    if project.status == 'completed':
        review = Review.objects.filter(project=project, reviewer=request.user).first()
        
    return render(request, 'core/client_projectInfo.html', {
        'project': project,
        'review': review
    })

@client_required
def client_projectMatches(request, project_id):
    project = get_object_or_404(Project, id=project_id, client=request.user.client)
    
    if request.GET.get('refresh'):
         from .ai_matching import MatchEngine
         engine = MatchEngine()
         engine.compute_matches(project.id)
         # Redirect to base path to clean url
         return redirect('client_projectMatches', project_id=project.id)

    matches = project.matches.select_related('freelancer__user__rating_summary').all()
    
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

# Freelancer part

@freelancer_required
def freelancer_home(request):
    freelancer = request.user.freelancer
    recommendations = get_recommendations(freelancer, limit=4)
    
    context = {
        'recommendations': recommendations
    }
    return render(request, 'core/freelancer_home.html', context)

@freelancer_required
def freelancer_search_job(request):
    query = request.GET.get('q', '').strip()
    freelancer = request.user.freelancer
    
    # Get all open projects
    projects = list(Project.objects.filter(status='open'))
    
    manager = AISearchManager()
    
    # Calculate scores based on query and/or freelancer skills
    scored_projects = manager.calculate_match_scores(projects, freelancer=freelancer, query=query)
    
    # Sort by score descending
    scored_projects.sort(key=lambda x: x[1], reverse=True)
    
    # Pre-process skills for template
    for project, score in scored_projects:
        if project.required_skills:
            project.skills_list = [s.strip() for s in project.required_skills.split(',') if s.strip()]
        else:
            project.skills_list = []
    
    context = {
        'query': query,
        'scored_projects': scored_projects,
    }
    return render(request, 'core/freelancer_searchJob.html', context)

@freelancer_required
def freelancer_track_project(request):
    freelancer = request.user.freelancer
    # Fetch active projects
    current_projects = Project.objects.filter(assigned_freelancer=freelancer, status__in=['in_progress', 'reviewing'])
    # Fetch passed/completed projects
    pass_projects = Project.objects.filter(assigned_freelancer=freelancer, status='completed')

    context = {
        'current_projects': current_projects,
        'pass_projects': pass_projects,
    }
    return render(request, 'core/freelancer_trackProject.html', context)

@freelancer_required
def freelancer_wallet(request):
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    recent_transactions = Transaction.objects.filter(wallet=wallet).order_by('-created_at')[:5]
    
    context = {
        'wallet': wallet,
        'recent_transactions': recent_transactions,
    }
    return render(request, 'core/freelancer_wallet.html', context)

@freelancer_required
def freelancer_settings(request):
    user_security, created = UserSecurity.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = SecurePinForm(request.POST, user_security=user_security)
        if form.is_valid():
            new_pin = form.cleaned_data['new_pin']
            user_security.secure_pin = make_password(new_pin)
            user_security.save()
            messages.success(request, "Secure PIN updated successfully.")
            return redirect('freelancer_settings')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = SecurePinForm(user_security=user_security)

    return render(request, 'core/freelancer_settings.html', {'form': form})


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
        
        # Calculate unread count (messages not sent by current user and not read)
        unread_count = conv.messages.filter(is_read=False).exclude(sender=request.user).count()
        
        # Determine name, avatar, role, and tagline based on role
        name = other_participant.username
        avatar_url = '/static/core/images/default_profile.png' # Fallback
        role = ''
        tagline = ''
        
        if hasattr(other_participant, 'client'):
            name = other_participant.client.company_name or other_participant.username
            role = 'Client'
            tagline = other_participant.client.tagline or ''
            if other_participant.client.profile_image:
                avatar_url = other_participant.client.profile_image.url
        elif hasattr(other_participant, 'freelancer'):
            name = other_participant.freelancer.full_name or other_participant.username
            role = 'Freelancer'
            tagline = other_participant.freelancer.tagline or ''
            if other_participant.freelancer.profile_image:
                avatar_url = other_participant.freelancer.profile_image.url
        
        # Format last message preview
        last_msg_preview = ''
        if last_message:
            if last_message.attachment:
                if last_message.attachment_type == 'image':
                    last_msg_preview = "📷 Photo"
                else:
                    filename = last_message.original_filename or last_message.attachment.name.split('/')[-1]
                    last_msg_preview = f'<i class="fas fa-paperclip"></i> {filename}'
            else:
                last_msg_preview = last_message.content
        
        data.append({
            'id': conv.id,
            'other_user_id': other_participant.id,
            'name': name,
            'avatar': avatar_url,
            'role': role,
            'tagline': tagline,
            'last_message': last_msg_preview,
            'last_message_time': last_message.created_at.isoformat() if last_message else conv.created_at.isoformat(),
            'is_muted': p.is_muted,
            'unread_count': unread_count
        })
        
    # Sort by updated_at (or last message time)
    data.sort(key=lambda x: x['last_message_time'], reverse=True)
    return JsonResponse(data, safe=False)

@login_required
def api_get_messages(request, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id)
    if not conversation.participants.filter(id=request.user.id).exists():
        return JsonResponse({'error': 'Unauthorized'}, status=403)
        
    # Mark all unread messages from other users as read
    conversation.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)
    
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
             
        # Handle attachments
        attachment_url = msg.attachment.url if msg.attachment else None
        
        data.append({
            'id': msg.id,
            'sender_id': msg.sender.id,
            'is_me': msg.sender == request.user,
            'sender_name': sender_name,
            'sender_avatar': sender_avatar,
            'content': msg.content,
            'attachment': attachment_url,
            'original_filename': msg.original_filename,
            'attachment_type': msg.attachment_type,
            'attachment_size': msg.attachment_size,
            'created_at': msg.created_at.isoformat(),
            'is_read': msg.is_read
        })
        
    return JsonResponse(data, safe=False)

@login_required
def api_download_attachment(request, message_id):
    message = get_object_or_404(Message, id=message_id)
    if not message.attachment:
         raise Http404("No attachment")
    
    # Check permission
    if not message.conversation.participants.filter(id=request.user.id).exists():
         return JsonResponse({'error': 'Unauthorized'}, status=403)

    filename = message.original_filename or message.attachment.name.split('/')[-1]
    
    # Open file and return FileResponse
    try:
        response = FileResponse(message.attachment.open('rb'))
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except FileNotFoundError:
        raise Http404("File not found")

@login_required
def api_send_message(request, conversation_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
        
    try:
        conversation = get_object_or_404(Conversation, id=conversation_id)
        if not conversation.participants.filter(id=request.user.id).exists():
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        
        # Handle both text and file uploads
        content = request.POST.get('content', '')
        attachment = request.FILES.get('attachment')
        
        # Validate that at least one of content or attachment is provided
        if not content and not attachment:
            return JsonResponse({'error': 'Content or attachment is required'}, status=400)
        
        # Validate file if attachment is provided
        attachment_type = None
        attachment_size = None
        original_filename = None
        if attachment:
            original_filename = attachment.name
            # Check file size (10MB max)
            max_size = 10 * 1024 * 1024  # 10MB in bytes
            if attachment.size > max_size:
                return JsonResponse({'error': 'File size exceeds 10MB limit'}, status=400)
            
            # Determine attachment type based on file extension
            file_ext = attachment.name.split('.')[-1].lower()
            if file_ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                attachment_type = 'image'
            elif file_ext == 'pdf':
                attachment_type = 'pdf'
            elif file_ext in ['doc', 'docx', 'txt', 'zip']:
                attachment_type = 'document'
            else:
                return JsonResponse({'error': 'Unsupported file type'}, status=400)
            
            attachment_size = attachment.size
            
        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            content=content,
            attachment=attachment,
            original_filename=original_filename,
            attachment_type=attachment_type,
            attachment_size=attachment_size
        )
        # Touch updated_at
        conversation.save()
        
        # Prepare message data for response and WebSocket
        sender_name = "Me"
        if hasattr(request.user, 'client'):
            sender_name = request.user.client.company_name
        elif hasattr(request.user, 'freelancer'):
            sender_name = request.user.freelancer.full_name
            
        sender_avatar = '/static/core/images/default_profile.png'
        if hasattr(request.user, 'client') and request.user.client.profile_image:
            sender_avatar = request.user.client.profile_image.url
        elif hasattr(request.user, 'freelancer') and request.user.freelancer.profile_image:
            sender_avatar = request.user.freelancer.profile_image.url
        
        message_data = {
            'id': message.id,
            'sender_id': request.user.id,
            'sender_name': sender_name,
            'sender_avatar': sender_avatar,
            'content': message.content,
            'attachment': message.attachment.url if message.attachment else None,
            'original_filename': message.original_filename,
            'attachment_type': message.attachment_type,
            'attachment_size': message.attachment_size,
            'created_at': message.created_at.isoformat(),
            'is_read': message.is_read
        }
        
        # Broadcast to WebSocket group (current conversation)
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        channel_layer = get_channel_layer()
        
        # Send message to current conversation room
        async_to_sync(channel_layer.group_send)(
            f'chat_{conversation_id}',
            {
                'type': 'chat_message',
                'message': message_data
            }
        )
        
        # Notify ALL participants to refresh their conversation list
        # This ensures the conversation list updates even if they're in a different conversation
        for participant in conversation.participants.all():
            async_to_sync(channel_layer.group_send)(
                f'user_{participant.id}',
                {
                    'type': 'conversation_updated'
                }
            )

        return JsonResponse({
            'status': 'success',
            'message_id': message.id,
            'message': message_data
        })
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

# Review functionality (for both client and freelancer)

@login_required
def submit_review(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    reviewer = request.user

    # Identify reviewee (the other party)
    reviewee = None
    if hasattr(reviewer, 'client') and project.client == reviewer.client:
        # Client reviewing Freelancer
        if project.assigned_freelancer:
            reviewee = project.assigned_freelancer.user
    elif hasattr(reviewer, 'freelancer') and project.assigned_freelancer == reviewer.freelancer:
        # Freelancer reviewing Client
        reviewee = project.client.user
        
    if not reviewee:
        messages.error(request, "You cannot review this project.")
        return redirect('client_project')

    # Check if already reviewed
    existing_review = Review.objects.filter(project=project, reviewer=reviewer).first()
    if existing_review:
        messages.info(request, "You have already reviewed this project.")
        # Redirect back to project info
        if hasattr(reviewer, 'client'): 
            return redirect('client_projectInfo', project_id=project.id)
        else:
            # waiting for freelancer page
            return redirect('freelancer_home') 

    # Determine base template
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
                with transaction.atomic():
                    review = form.save(commit=False)
                    review.project = project
                    review.reviewer = reviewer
                    review.reviewee = reviewee
                    # feedback_tags handling:
                    # If using ModelForm with JSONField, Django might handle list automatically if widget is correct,
                    # but since we use custom checkbox list in template, we might need to explicit getlist if form doesn't catch it.
                    # Standard Django behavior for custom list inputs might need explicit handling or widget config.
                    # However, let's trust form.cleaned_data for now if input names match.
                    # Actually, for JSONField and custom list checkboxes, we might need to help it.
                    tags = request.POST.getlist('feedback_tags')
                    review.feedback_tags = tags
                    
                    review.save()
                    
                    # 2. Update Rating Summary
                    summary, created = RatingSummary.objects.get_or_create(user=reviewee)
                    
                    # Update specific star counts
                    rating = review.rating
                    if rating == 5: summary.five_star_count += 1
                    elif rating == 4: summary.four_star_count += 1
                    elif rating == 3: summary.three_star_count += 1
                    elif rating == 2: summary.two_star_count += 1
                    elif rating == 1: summary.one_star_count += 1
                    
                    # Recalculate average
                    current_total_score = decimal.Decimal(str(summary.average_rating)) * summary.total_reviews
                    summary.total_reviews += 1
                    new_total_score = current_total_score + decimal.Decimal(rating)
                    summary.average_rating = new_total_score / summary.total_reviews
                    
                    summary.save()
                    
                messages.success(request, "Review submitted successfully!")
                
                # Redirect based on role
                if hasattr(reviewer, 'client'):
                     return redirect('client_projectInfo', project_id=project.id)
                else:
                     return redirect('freelancer_home') # Or specific project view

            except Exception as e:
                print(e)
                messages.error(request, f"Error submitting review: {str(e)}")
        else:
             for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    
    # Define available tags based on role being reviewed
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
        'form': form 
    })

@freelancer_required
def freelancer_profile(request):
    freelancer = request.user.freelancer
    is_owner = True # For now, assuming accessing own profile via this URL. 
    # If we want public profile, we might need a separate view or param. 
    # But usually /freelancer/profile/ is own profile.
    
    portfolios = freelancer.portfolios.all().order_by('-created_at')
    work_experiences = freelancer.work_experiences.all().order_by('-start_date')
    certifications = freelancer.certifications.all().order_by('-issue_date')
    languages = freelancer.languages.all()
    
    # Platform Employment History (Completed Projects)
    completed_projects = Project.objects.filter(assigned_freelancer=freelancer, status='completed').order_by('-created_at')
    
    # Testimonials (Reviews from completed projects)
    # Since Review is OneToOne to Project, we can access via project or reverse query
    reviews = Review.objects.filter(reviewee=freelancer.user).order_by('-created_at')

    # Forms
    profile_for_view = FreelancerProfileForm(instance=freelancer) # Keep full one
    
    header_form = FreelancerHeaderForm(instance=freelancer)
    rate_form = FreelancerRateForm(instance=freelancer)
    background_form = FreelancerBackgroundForm(instance=freelancer)
    social_form = FreelancerSocialForm(instance=freelancer)
    bio_form = FreelancerBioForm(instance=freelancer)
    skills_form = FreelancerSkillsForm(instance=freelancer)
    
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
                 return redirect('freelancer_profile')
             else:
                 messages.error(request, "No image selected.")

        # Granular Contextual Updates
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
                return redirect('freelancer_profile')
            else:
                 messages.error(request, "No background image selected.")

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

        # Legacy / Full Update (Optional, keeping for compatibility if older modal used)
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
                 # Basic 'verification' logic stub (e.g. check if PDF)
                 if cert.certificate_file.name.lower().endswith('.pdf'):
                     cert.is_verified = True # Dummy verification
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
        'is_owner': is_owner,
        
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
        'languages': languages
    })


# Admin Part
@admin_required
def admin_dashboard(request):
    """Admin Dashboard with platform statistics"""
    from django.db.models import Sum, Count
    
    # Platform Statistics
    total_users = User.objects.count()
    total_clients = Client.objects.count()
    total_freelancers = Freelancer.objects.count()
    total_projects = Project.objects.count()
    open_projects = Project.objects.filter(status='open').count()
    completed_projects = Project.objects.filter(status='completed').count()
    
    # Earnings Calculation (sum of all completed transactions)
    total_earnings = Transaction.objects.filter(
        status='completed',
        transaction_type='payment'
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    # Calculate platform fee (assuming 10% of earnings)
    platform_revenue = total_earnings * decimal.Decimal('0.10')
    
    # Recent activity
    recent_users = User.objects.order_by('-date_joined')[:5]
    recent_projects = Project.objects.order_by('-created_at')[:5]
    
    context = {
        'total_users': total_users,
        'total_clients': total_clients,
        'total_freelancers': total_freelancers,
        'total_projects': total_projects,
        'open_projects': open_projects,
        'completed_projects': completed_projects,
        'total_earnings': total_earnings,
        'platform_revenue': platform_revenue,
        'recent_users': recent_users,
        'recent_projects': recent_projects,
    }
    
    return render(request, 'core/admin/admin_dashboard.html', context)

@admin_required
def admin_support(request):
    """Admin Support Ticket Management"""
    # Get all tickets
    tickets = Ticket.objects.select_related('user').all()
    
    # Search functionality
    search = request.GET.get('search', '')
    if search:
        from django.db.models import Q
        tickets = tickets.filter(
            Q(title__icontains=search) |
            Q(user__username__icontains=search) |
            Q(user__email__icontains=search)
        )
    
    # Filter by category
    category_filter = request.GET.get('category', '')
    if category_filter:
        tickets = tickets.filter(category=category_filter)
    
    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter:
        tickets = tickets.filter(status=status_filter)
    
    # Pagination
    paginator = Paginator(tickets, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'tickets': page_obj,
        'search': search,
        'category_filter': category_filter,
        'status_filter': status_filter,
        'category_choices': Ticket.CATEGORY_CHOICES,
        'status_choices': Ticket.STATUS_CHOICES,
    }
    
    return render(request, 'core/admin/admin_support.html', context)

@admin_required
def admin_user_management(request):
    """Admin User Management"""
    # Get all users
    users = User.objects.all().order_by('-date_joined')
    
    # Search functionality
    search = request.GET.get('search', '')
    if search:
        from django.db.models import Q
        users = users.filter(
            Q(username__icontains=search) |
            Q(email__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search)
        )
    
    # Filter by role
    role_filter = request.GET.get('role', '')
    if role_filter == 'client':
        users = users.filter(client__isnull=False)
    elif role_filter == 'freelancer':
        users = users.filter(freelancer__isnull=False)
    elif role_filter == 'admin':
        users = users.filter(is_superuser=True)
    
    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)
    
    # Pagination
    paginator = Paginator(users, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'users': page_obj,
        'search': search,
        'role_filter': role_filter,
        'status_filter': status_filter,
    }
    
    return render(request, 'core/admin/admin_user.html', context)

@admin_required
def admin_activity_log(request):
    """Admin Activity Log"""
    # Get all logs
    logs = AdminLog.objects.select_related('admin_user').all()
    
    # Filter by action
    action_filter = request.GET.get('action', '')
    if action_filter:
        logs = logs.filter(action=action_filter)
    
    # Filter by admin user
    admin_filter = request.GET.get('admin', '')
    if admin_filter:
        logs = logs.filter(admin_user__username__icontains=admin_filter)
    
    # Pagination
    paginator = Paginator(logs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'logs': page_obj,
        'action_filter': action_filter,
        'admin_filter': admin_filter,
        'action_choices': AdminLog.ACTION_CHOICES,
    }
    
    return render(request, 'core/admin/admin_activityLog.html', context)

@admin_required
def admin_reference_data(request):
    """Manage reference data like Industries and Project Categories"""
    industries = Industry.objects.all().order_by('name')
    categories = ProjectCategory.objects.all().order_by('name')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        type = request.POST.get('type')
        name = request.POST.get('name')
        pk = request.POST.get('pk')
        
        try:
            if action == 'add':
                if type == 'industry':
                    Industry.objects.create(name=name)
                    messages.success(request, f"Industry Type '{name}' added successfully.")
                else:
                    ProjectCategory.objects.create(name=name)
                    messages.success(request, f"Project Category '{name}' added successfully.")
                
            elif action == 'edit':
                if type == 'industry':
                    obj = Industry.objects.get(pk=pk)
                    old_name = obj.name
                    obj.name = name
                    obj.save()
                    messages.success(request, f"Industry Type updated from '{old_name}' to '{name}'.")
                else:
                    obj = ProjectCategory.objects.get(pk=pk)
                    old_name = obj.name
                    obj.name = name
                    obj.save()
                    messages.success(request, f"Project Category updated from '{old_name}' to '{name}'.")
                
            elif action == 'toggle_status':
                if type == 'industry':
                    obj = Industry.objects.get(pk=pk)
                    obj.is_active = not obj.is_active
                    obj.save()
                    status = "activated" if obj.is_active else "deactivated"
                    messages.success(request, f"Industry Type '{obj.name}' {status}.")
                else:
                    obj = ProjectCategory.objects.get(pk=pk)
                    obj.is_active = not obj.is_active
                    obj.save()
                    status = "activated" if obj.is_active else "deactivated"
                    messages.success(request, f"Project Category '{obj.name}' {status}.")
                    
            elif action == 'delete':
                # Attempt hard delete, but catch ProtectedError
                if type == 'industry':
                    obj = Industry.objects.get(pk=pk)
                    name = obj.name
                    try:
                        obj.delete()
                        messages.success(request, f"Industry Type '{name}' permanently deleted.")
                    except ProtectedError:
                        # If protected, suggest deactivation instead
                        messages.error(request, f"Cannot delete '{name}' because it is linked to existing clients. Please deactivate it instead.")
                else:
                    obj = ProjectCategory.objects.get(pk=pk)
                    name = obj.name
                    try:
                        obj.delete()
                        messages.success(request, f"Project Category '{name}' permanently deleted.")
                    except ProtectedError:
                        messages.error(request, f"Cannot delete '{name}' because it is linked to existing projects. Please deactivate it instead.")
                     # Log admin action
            display_type = "Industry Type" if type == 'industry' else "Project Category"
            action_map = {
                'add': 'Added',
                'edit': 'Edited',
                'delete': 'Deleted',
                'toggle_status': 'Activated' if locals().get('status') == 'activated' else 'Deactivated'
            }
            
            # Log admin action
            display_type = "Industry Type" if type == 'industry' else "Project Category"
            action_map = {
                'add': 'Added',
                'edit': 'Edited',
                'delete': 'Deleted',
                'toggle_status': 'Activated' if locals().get('status') == 'activated' else 'Deactivated'
            }
            
            # Action type for the model choice
            log_action_type = 'update'
            if action == 'add':
                log_action_type = 'create'
            elif action == 'delete':
                log_action_type = 'delete'
            
            friendly_action = action_map.get(action, action)
            

            log_item_name = name if name else locals().get('name', '')
            if not log_item_name and 'obj' in locals():
                log_item_name = obj.name
                
            log_description = f"Managed reference data: {friendly_action} {display_type} {log_item_name}"

            AdminLog.objects.create(
                admin_user=request.user,
                action=log_action_type,
                target_model='Industry' if type == 'industry' else 'ProjectCategory',
                target_id=pk if pk else 'new',
                description=log_description,
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
            
        return redirect('admin_reference_data')

    context = {
        'industries': industries,
        'categories': categories,
        'active_menu': 'reference'
    }
    return render(request, 'core/admin/admin_reference.html', context)

