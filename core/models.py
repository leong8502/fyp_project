from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Client(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='client')
    company_name = models.CharField(max_length=255)
    profile_image = models.CharField(max_length=500, blank=True, null=True, help_text="core/media/clients/profiles")
    background_image = models.CharField(max_length=500, blank=True, null=True, help_text="core/media/clients/backgrounds")
    description = models.TextField(blank=True)
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
    created_at = models.DateTimeField(auto_now_add=True)

    # Email verification fields
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.company_name or self.user.email

class Job(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    posted_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title