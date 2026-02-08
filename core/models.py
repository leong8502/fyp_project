from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Industry(models.Model):
    name = models.CharField(max_length=100, unique=True)
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
    industry_type = models.ForeignKey(Industry, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')
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
    category = models.ForeignKey('ProjectCategory', on_delete=models.SET_NULL, null=True, related_name='projects')
    budget = models.DecimalField(max_digits=10, decimal_places=2)
    deadline = models.DateField()
    required_skills = models.TextField(help_text="Comma-separated skills")
    experience_level = models.CharField(max_length=20, choices=EXPERIENCE_LEVEL_CHOICES, default='entry')
    year_of_experience = models.PositiveIntegerField(default=0)
    preferred_language = models.CharField(max_length=100, blank=True)
    
    # AI Matching Fields
    project_embedding = models.JSONField(null=True, blank=True, help_text="Vector embedding of the project description for AI matching")
    ai_match_score = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True, help_text="AI calculated match score (0.0 to 1.0) for the assigned freelancer")
    extracted_keywords = models.JSONField(null=True, blank=True, help_text="Keywords extracted by AI for fast filtering")
    
    assigned_freelancer = models.ForeignKey('Freelancer', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_projects')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='inactive')
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.title

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
    
    # Revision Support
    revision_requested = models.BooleanField(default=False, help_text="Indicates whether client requested a revision")
    revision_count = models.PositiveIntegerField(default=0, help_text="Number of revisions requested")

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.project.title} - {self.title}"


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
    # AI Matching
    freelancer_embedding = models.JSONField(null=True, blank=True)
    extracted_keywords = models.JSONField(null=True, blank=True)
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
    reference_id = models.CharField(max_length=255, blank=True, unique=True, help_text="External Transaction ID")
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
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Escrow for {self.project.title} - {self.status}"

    class Meta:
        verbose_name = "Escrow Account"
        verbose_name_plural = "Escrow Accounts"

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
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('project', 'reviewer') # One review per project per reviewer

    def __str__(self):
        return f"Review by {self.reviewer.username} for {self.reviewee.username} - {self.rating} stars"
