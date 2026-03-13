from django.db import models  
from pgvector.django import VectorField 
from django.contrib.auth.models import User 
from django.utils import timezone  

class Industry(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Industries"

class Client(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='client')
    company_name = models.CharField(max_length=255)
    tagline = models.CharField(max_length=150, blank=True)
    profile_image = models.ImageField(upload_to='client_profiles/', default='client_profiles/default_profile.png', blank=True, null=True)
    background_image = models.ImageField(upload_to='client_backgrounds/', default='client_backgrounds/default_background.jpg', blank=True, null=True)
    description = models.TextField(blank=True)
    achievements = models.TextField(blank=True)
    languages = models.TextField(blank=True, help_text="Comma-separated languages")
    tags = models.TextField(blank=True, help_text="Comma-separated tags")
    phone = models.CharField(max_length=20)
    address = models.TextField(blank=True)
    industry_type = models.ForeignKey(Industry, on_delete=models.PROTECT, null=True, blank=True, related_name='clients')
    company_size = models.CharField(max_length=50, choices=[
        ('1-10', '1-10 employees'),
        ('11-50', '11-50 employees'),
        ('51-200', '51-200 employees'),
        ('201-500', '201-500 employees'),
        ('500+', '500+ employees'),
    ])
    year_founded = models.PositiveIntegerField(null=True, blank=True)
    website_url = models.URLField(blank=True)
    linkedIn_url = models.URLField(blank=True, null=True)
    instagram_url = models.URLField(blank=True, null=True)
    facebook_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Email verification fields
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=100, blank=True)

    @property
    def tags_list(self):
        if self.tags:
            return [tag.strip() for tag in self.tags.split(',') if tag.strip()]
        return []

    @property
    def average_rating(self):
        if hasattr(self.user, 'rating_summary'):
            return self.user.rating_summary.average_rating
        return 0.0

    @property
    def total_reviews(self):
        if hasattr(self.user, 'rating_summary'):
             return self.user.rating_summary.total_reviews
        return 0

    def __str__(self):
        return self.company_name or self.user.email

class Job(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    posted_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class ProjectCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Project Categories"

class Project(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),  # Created but not published
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    EXPERIENCE_LEVEL_CHOICES = [
        ('entry', 'Entry Level'),
        ('intermediate', 'Intermediate'),
        ('expert', 'Expert'),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='projects')
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey('ProjectCategory', on_delete=models.PROTECT, null=True, related_name='projects')
    budget = models.DecimalField(max_digits=10, decimal_places=2)
    deadline = models.DateField()
    required_skills = models.TextField(help_text="Comma-separated skills")
    experience_level = models.CharField(max_length=20, choices=EXPERIENCE_LEVEL_CHOICES, default='entry')
    year_of_experience = models.PositiveIntegerField(default=0)
    preferred_language = models.CharField(max_length=100, blank=True)
    max_freelancers = models.PositiveIntegerField(default=1, help_text="Maximum number of freelancers allowed on this project")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    attachment = models.FileField(upload_to='project_attachments/', blank=True, null=True, help_text="Single PDF attachment")
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
    deadline_notified = models.BooleanField(default=False, help_text="True after deadline-expired notification sent for in_progress projects")
    def __str__(self):
        return self.title

    @property
    def hired_freelancers(self):
        """Returns a list of freelancers whose applications have been accepted."""
        return [app.freelancer for app in self.applications.filter(status='accepted')]

    @property
    def has_hired_freelancers(self):
        """Returns True if at least one freelancer has been accepted."""
        return self.applications.filter(status='accepted').exists()

class ProjectApplication(models.Model):
    APPLICATION_TYPES = [
        ('apply', 'Application'),
        ('invite', 'Invitation'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='applications')
    freelancer = models.ForeignKey('Freelancer', on_delete=models.CASCADE, related_name='applications')
    application_type = models.CharField(max_length=10, choices=APPLICATION_TYPES)
    message = models.TextField(blank=True, help_text="Cover letter or invitation message")
    attachment = models.FileField(upload_to='application_attachments/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('project', 'freelancer')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_application_type_display()} - {self.freelancer.user.username} for {self.project.title}"


class Milestone(models.Model):

    STATUS_CHOICES = [
        ('pending', 'Pending'), # before start
        ('in_progress', 'In Progress'), # working
        ('completed', 'Completed'), # freelancer submit but befero payment
        ('approved', 'Approved'), # client accept and payment release
        ('cancelled', 'Cancelled'), # cancel when dispute
    ]

    project = models.ForeignKey('Project', on_delete=models.CASCADE, related_name='milestones')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Payment for this milestone")
    deadline = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    order = models.PositiveIntegerField(help_text="Milestone sequence order")
    assigned_to = models.ForeignKey(
        'Freelancer', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_milestones',
        help_text="Freelancer responsible for this milestone"
    )
    # Revision Support
    revision_requested = models.BooleanField(default=False, help_text="Indicates whether client requested a revision")
    revision_count = models.PositiveIntegerField(default=0, help_text="Number of revisions requested")
    revision_reason = models.TextField(blank=True, help_text="Reason for the latest revision request")


    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.project.title} - {self.title}"

    @property
    def is_late(self):
        """Returns True if the milestone is in_progress and past its deadline."""
        if self.status == 'in_progress' and self.deadline:
            from django.utils import timezone 
            return self.deadline < timezone.now().date()
        return False

    @property
    def was_completed_late(self):
        """Returns True if the milestone is completed/approved after its deadline."""
        if self.status in ['completed', 'approved'] and self.deadline and self.completed_at:
            return self.completed_at.date() > self.deadline
        return False

    class Meta:
        ordering = ['order']

class MilestoneAttachment(models.Model):
    milestone = models.ForeignKey(Milestone, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='milestone_attachments/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attachment for {self.milestone.title}"



class Freelancer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='freelancer')
    
    # Basic profile info
    full_name = models.CharField(max_length=255, blank=True)
    tagline = models.CharField(max_length=150, blank=True, help_text="Short professional headline")
    phone = models.CharField(max_length=20, blank=True)
    profile_image = models.ImageField(
        upload_to='freelancer_profiles/',
        default='freelancer_profiles/default_profile.png',
        blank=True,
        null=True
    )
    background_image = models.ImageField(
        upload_to='freelancer_backgrounds/',
        default='freelancer_backgrounds/default_background.jpg',
        blank=True,
        null=True
    )
    
    # Professional information
    bio = models.TextField(blank=True, verbose_name="About Me")
    skills = models.TextField(
        blank=True,
        help_text="Comma-separated list of your main skills (e.g., Python, Django, React, UI/UX)"
    )
    experience_years = models.PositiveIntegerField(default=0, blank=True)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                     help_text="Your expected hourly rate in USD")
    portfolio_url = models.URLField(blank=True, null=True, verbose_name="Portfolio / GitHub")
    linkedin_url = models.URLField(blank=True, null=True)
    github_url = models.URLField(blank=True, null=True)
    
    # Location & availability
    location = models.CharField(max_length=255, blank=True)
    availability_status = models.CharField(
        max_length=50,
        choices=[
            ('full_time', 'Full-time'),
            ('part_time', 'Part-time'),
            ('contract', 'Contract'),
            ('not_available', 'Not Available Now'),
        ],
        default='full_time',
        blank=True
    )
    
    # Ratings & stats
    total_jobs_completed = models.PositiveIntegerField(default=0)
    total_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, blank=True)
    
    # Verification & timestamps
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=100, blank=True)
    last_active = models.DateTimeField(default=timezone.now)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def skills_list(self):
        if self.skills:
            return [skill.strip() for skill in self.skills.split(',') if skill.strip()]
        return []

    def __str__(self):
        return self.full_name or self.user.username or self.user.email

    class Meta:
        verbose_name = "Freelancer"
        verbose_name_plural = "Freelancers"
        ordering = ['-created_at']

class Wallet(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('frozen', 'Frozen'),
        ('closed', 'Closed'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    wallet_number = models.CharField(max_length=30, unique=True, help_text="Public wallet identifier")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    currency = models.CharField(max_length=10, default='RM')
    is_hidden = models.BooleanField(default=False, help_text="Hide balance in UI")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s Wallet ({self.currency} {self.balance})"

class PaymentMethod(models.Model):
    METHOD_TYPES = [
        ('credit_card', 'Credit Card'),
        ('bank', 'Online Banking'),
        ('e_wallet', 'E-wallet'),
    ]

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='payment_methods')
    method_name = models.CharField(max_length=100, help_text="e.g. Visa") # Common display name
    method_type = models.CharField(max_length=20, choices=METHOD_TYPES)
    provider_id = models.CharField(max_length=255, blank=True, help_text="Token ID from payment provider (Stripe, PayPal, etc.)")
    provider_reference = models.CharField(max_length=255, blank=True, help_text="Token or reference ID from provider")
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.method_name} ({self.get_method_type_display()})"

class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('top_up', 'Top Up'),
        ('withdrawal', 'Withdrawal'),
        ('payment', 'Payment'), # Payment for a project/milestone
        ('refund', 'Refund'),
        ('payout', 'Payout'), # Freelancer receive money
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    DIRECTION_CHOICES = [
        ('credit', 'Credit'), # money goes in
        ('debit', 'Debit'), # money goes out
    ]

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    description = models.TextField(blank=True)
    reference_id = models.CharField(max_length=255, blank=True, null=True, unique=True, help_text="External Transaction ID")
    related_project = models.ForeignKey('Project', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions', help_text="Link to Project if applicable")
    related_milestone = models.ForeignKey('Milestone', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions', help_text="Link to Milestone if applicable")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type} - {self.amount} ({self.status})"

class UserSecurity(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='security')
    secure_pin = models.CharField(max_length=128, blank=True, null=True, help_text="Hashed secure PIN")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s Security Settings"

class Escrow(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),       # Funds held
        ('released', 'Released'),   # All funds released
        ('refunded', 'Refunded'),   # Funds returned to client
    ]
    
    project = models.OneToOneField('Project', on_delete=models.CASCADE, related_name='escrow')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Total amount held in escrow")
    released_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Amount released to freelancer")
    remaining_amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Amount still in escrow")
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="10% platform fee allocated from project")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Escrow for {self.project.title} - {self.status}"

    class Meta:
        verbose_name = "Escrow Account"
        verbose_name_plural = "Escrow Accounts"


class CancellationRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('agreed', 'Agreed'),
        ('declined', 'Declined'),
    ]

    project = models.ForeignKey('Project', on_delete=models.CASCADE, related_name='cancellation_requests')
    # Always targets a specific freelancer — one request per freelancer per project
    freelancer = models.ForeignKey(
        'Freelancer', on_delete=models.CASCADE, null=True, blank=True,
        related_name='received_cancellation_requests',
        help_text="The freelancer this cancellation request is addressed to"
    )
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cancellation_requests')
    reason = models.TextField(blank=True, help_text="Optional reason for cancellation")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # One active request per project per freelancer at a time
        unique_together = ('project', 'freelancer')

    def __str__(self):
        return f"Cancellation Request for {self.project.title} ({self.freelancer.user.username}) - {self.status}"


class ProjectMatch(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='matches')
    freelancer = models.ForeignKey(Freelancer, on_delete=models.CASCADE, related_name='project_matches')
    similarity_score = models.FloatField(help_text="Raw Cosine Similarity Score")
    final_score = models.FloatField(help_text="Weighted Hybrid Score")
    score_breakdown = models.JSONField(help_text="Detailed breakdown of scoring components")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-final_score']
        unique_together = ('project', 'freelancer')

    def __str__(self):
        return f"{self.project.title} - {self.freelancer.user.username} ({self.final_score:.2f})"

class Conversation(models.Model):
    participants = models.ManyToManyField(User, through='ChatParticipant', related_name='conversations')
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Conversation {self.id}"

class ChatParticipant(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    is_muted = models.BooleanField(default=False)
    is_removed = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'conversation')

class Message(models.Model):
    ATTACHMENT_TYPES = [
        ('image', 'Image'),
        ('pdf', 'PDF'),
        ('document', 'Document'),
    ]
    
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    content = models.TextField(blank=True)
    attachment = models.FileField(upload_to='chat_attachments/', blank=True, null=True)
    original_filename = models.CharField(max_length=255, blank=True, null=True)
    attachment_type = models.CharField(max_length=20, choices=ATTACHMENT_TYPES, blank=True, null=True)
    attachment_size = models.IntegerField(blank=True, null=True, help_text="File size in bytes")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Message from {self.sender.username} at {self.created_at}"

class FreelancerPortfolio(models.Model):
    freelancer = models.ForeignKey(Freelancer, on_delete=models.CASCADE, related_name='portfolios')
    title = models.CharField(max_length=200)
    description = models.TextField()
    project_file = models.FileField(upload_to='portfolio_files/', help_text="Upload your project (ZIP/PDF)", blank=True, null=True)
    project_link = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class FreelancerWorkExperience(models.Model):
    freelancer = models.ForeignKey(Freelancer, on_delete=models.CASCADE, related_name='work_experiences')
    company = models.CharField(max_length=200)
    job_title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.job_title} at {self.company}"

class FreelancerCertification(models.Model):
    freelancer = models.ForeignKey(Freelancer, on_delete=models.CASCADE, related_name='certifications')
    name = models.CharField(max_length=200)
    issuing_organization = models.CharField(max_length=200)
    issue_date = models.DateField()
    certificate_file = models.FileField(upload_to='certifications/', help_text="Upload certificate image/pdf")
    is_verified = models.BooleanField(default=False)
    verification_date = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name

class FreelancerLanguage(models.Model):
    PROFICIENCY_CHOICES = [
        ('Basic', 'Basic'),
        ('Conversational', 'Conversational'),
        ('Fluent', 'Fluent'),
        ('Native', 'Native'),
    ]

    freelancer = models.ForeignKey(Freelancer, on_delete=models.CASCADE, related_name='languages')
    language = models.CharField(max_length=100)
    proficiency = models.CharField(max_length=50, choices=PROFICIENCY_CHOICES, default='Basic')
    
    def __str__(self):
        return f"{self.language} ({self.proficiency})"

class RatingSummary(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='rating_summary')
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_reviews = models.PositiveIntegerField(default=0)
    
    # Optional detailed breakdown
    five_star_count = models.PositiveIntegerField(default=0)
    four_star_count = models.PositiveIntegerField(default=0)
    three_star_count = models.PositiveIntegerField(default=0)
    two_star_count = models.PositiveIntegerField(default=0)
    one_star_count = models.PositiveIntegerField(default=0)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.average_rating} ({self.total_reviews} reviews)"

class Review(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='reviews')
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='given_reviews')
    reviewee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_reviews')
    
    rating = models.PositiveIntegerField(choices=[(i, i) for i in range(1, 6)])
    comment = models.TextField(blank=True)
    feedback_tags = models.JSONField(default=list, blank=True, help_text="List of selected feedback tags")
    is_hidden = models.BooleanField(default=False, help_text="Hide the review from public display")
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # One review per reviewer per reviewee per project
        # Allows client to review each freelancer individually on a multi-freelancer project
        unique_together = ('project', 'reviewer', 'reviewee')

    def __str__(self):
        return f"Review by {self.reviewer.username} for {self.reviewee.username} - {self.rating} stars"

class FreelancerAIProfile(models.Model):
    """
    AI-generated profile for freelancers.
    Stores aggregated, AI-processed data for matching and recommendations.
    """
    freelancer = models.OneToOneField(Freelancer, on_delete=models.CASCADE, related_name='ai_profile')
    
    # AI-generated summaries
    professional_summary = models.TextField(blank=True, help_text="AI-generated summary of freelancer's profile")
    strengths = models.JSONField(default=list, blank=True, help_text="List of key strengths")
    weaknesses = models.JSONField(default=list, blank=True, help_text="List of areas for improvement")
    
    # Extracted expertise
    top_skills = models.JSONField(default=list, blank=True, help_text="Top skills extracted from profile")
    domain_expertise = models.JSONField(default=list, blank=True, help_text="Domain/industry expertise areas")
    
    # Cached metrics
    avg_rating = models.FloatField(default=0.0, help_text="Cached average rating")
    reliability_score = models.FloatField(default=0.0, help_text="Calculated reliability metric (0.0-1.0)")
    
    # AI matching
    semantic_embedding = VectorField(dimensions=384, null=True, blank=True, help_text="Vector embedding for semantic matching")
    extracted_keywords = models.JSONField(default=list, blank=True, help_text="Keywords extracted for fast filtering")
    
    # Metadata
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"AI Profile for {self.freelancer.full_name or self.freelancer.user.username}"
    
    class Meta:
        verbose_name = "Freelancer AI Profile"
        verbose_name_plural = "Freelancer AI Profiles"

class ProjectAIProfile(models.Model):
    """
    AI-generated profile for projects.
    Stores aggregated, AI-processed data for matching freelancers.
    """
    COMPLEXITY_CHOICES = [
        ('simple', 'Simple'),
        ('moderate', 'Moderate'),
        ('complex', 'Complex'),
    ]
    
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name='ai_profile')
    
    # AI-generated analysis
    summary_text = models.TextField(blank=True, help_text="AI-generated project summary")
    complexity_level = models.CharField(max_length=20, choices=COMPLEXITY_CHOICES, default='moderate', help_text="Assessed complexity level")
    required_expertise = models.JSONField(default=list, blank=True, help_text="List of required expertise areas")
    estimated_duration = models.PositiveIntegerField(null=True, blank=True, help_text="AI-estimated duration in days")
    risk_factors = models.JSONField(default=list, blank=True, help_text="Potential project risks identified by AI")
    
    # AI matching
    semantic_embedding = VectorField(dimensions=384, null=True, blank=True, help_text="Vector embedding for semantic matching")
    extracted_keywords = models.JSONField(default=list, blank=True, help_text="Keywords extracted for fast filtering")
    
    # Metadata
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"AI Profile for {self.project.title}"
    
    class Meta:
        verbose_name = "Project AI Profile"
        verbose_name_plural = "Project AI Profiles"

class Ticket(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]
    
    CATEGORY_CHOICES = [
        ('account', 'Account & Profile'),
        ('projects', 'Projects & Jobs'),
        ('billing', 'Billing & Payments'),
        ('disputes', 'Disputes & Reports'),
        ('reviews', 'Reviews & Ratings'),
        ('messages', 'Messaging & Notifications'),
        ('technical', 'Technical Issues / Bugs'),
        ('feedback', 'Feedback & Suggestions'),
        ('other', 'Other / General Inquiry'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tickets')
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.title} - {self.get_status_display()}"
    
    class Meta:
        ordering = ['-created_at']

class ProjectActivity(models.Model):
    ACTIVITY_TYPES = [
        ('proposal_accepted', 'Proposal Accepted'),
        ('proposal_rejected', 'Proposal Rejected'),
        ('milestone_submitted', 'Milestone Submitted'),
        ('milestone_approved', 'Milestone Approved'),
        ('revision_requested', 'Revision Requested'),
        ('payment_released', 'Payment Released'),
        ('status_updated', 'Status Updated'),
        ('other', 'Other'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='activities')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='project_activities')
    activity_type = models.CharField(max_length=50, choices=ACTIVITY_TYPES)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.project.title} - {self.get_activity_type_display()} - {self.created_at}"


class AdminLog(models.Model):
    ACTION_CHOICES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('login', 'Login'),
        ('logout', 'Logout'),
    ]
    
    admin_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='admin_logs')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    target_model = models.CharField(max_length=100, blank=True, help_text="Model name that was affected")
    target_id = models.CharField(max_length=100, blank=True, help_text="ID of the affected object")
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.admin_user.username} - {self.action} - {self.created_at}"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Admin Activity Log"
        verbose_name_plural = "Admin Activity Logs"

class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('project_published', 'Project Published'),
        ('proposal_received', 'Proposal Received'),
        ('project_started', 'Project Started'),
        ('milestone_submitted', 'Milestone Submitted'),
        ('topup_success', 'Top-up Success'),
        ('topup_cancelled', 'Top-up Cancelled'),
        ('withdrawal_processed', 'Withdrawal Processed'),
        ('payment_released', 'Payment Released'),
        ('review_submitted', 'Review Submitted'),
        ('project_cancelled', 'Project Cancelled'),
        ('cancellation_request', 'Cancellation Request'),
        ('project_auto_cancelled', 'Project Auto Cancelled'),
        ('project_deadline_expired', 'Project Deadline Expired'),
    ]

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=255)
    message = models.TextField()
    link = models.CharField(max_length=255, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.notification_type} for {self.recipient.username}"

class NotificationSetting(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='notification_settings')
    project_updates = models.BooleanField(default=True)
    payment_notifications = models.BooleanField(default=True)
    review_notifications = models.BooleanField(default=True)

    def __str__(self):
        return f"Settings for {self.user.username}"


class AIApiUsage(models.Model):
    """
    Tracks daily API requests to generative AI models to enforce quotas.
    """
    date = models.DateField(unique=True, default=timezone.now, help_text="Date of API usage")
    request_count = models.PositiveIntegerField(default=0, help_text="Number of requests made on this date")
    
    def __str__(self):
        return f"API Usage on {self.date}: {self.request_count} requests"

    class Meta:
        ordering = ['-date']


class MatchScore(models.Model):
    """
    Stores the Jaccard-based AI match score between a freelancer and a project.
    Used for displaying sorted results, info popups, and suitability sentences.
    """
    freelancer = models.ForeignKey(Freelancer, on_delete=models.CASCADE, related_name='match_scores')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='match_scores')
    score = models.FloatField(default=0.0, help_text="Match score 0-100")
    calculation_logic = models.TextField(blank=True, help_text="Human-readable breakdown of scoring")
    suitability_sentence = models.TextField(blank=True, help_text="Short sentence explaining suitability")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('freelancer', 'project')
        ordering = ['-score']

    def __str__(self):
        return f"{self.freelancer} ↔ {self.project.title}: {self.score:.1f}%"


class ChatMessage(models.Model):
    """Stores per-user Ami chatbox conversation history."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ami_messages')
    message = models.TextField()
    response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.user.username}] {self.message[:40]}"
