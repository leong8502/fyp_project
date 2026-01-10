from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

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
    industry_type = models.CharField(max_length=100)
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
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00, help_text="Average client rating")
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



class Freelancer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='freelancer')
    
    # Basic profile info
    full_name = models.CharField(max_length=255, blank=True)
    tagline = models.CharField(max_length=150, blank=True, help_text="Short professional headline")
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
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00, blank=True)
    total_jobs_completed = models.PositiveIntegerField(default=0)
    total_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, blank=True)
    
    # Verification & timestamps
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def skills_list(self):
        """Return skills as a clean list"""
        if self.skills:
            return [skill.strip() for skill in self.skills.split(',') if skill.strip()]
        return []

    def __str__(self):
        return self.full_name or self.user.username or self.user.email

    class Meta:
        verbose_name = "Freelancer"
        verbose_name_plural = "Freelancers"
        ordering = ['-created_at']