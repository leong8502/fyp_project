import uuid
from django.db import transaction
from django.conf import settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.contrib.auth.models import User
from core.models import Client, Freelancer, Wallet, UserSecurity

class AuthService:
    @staticmethod
    def register_client(request, form):
        """Register a new client, create wallet, and send verification email."""
        with transaction.atomic():
            # Save form (creates User and Client)
            client = form.save()

            # Create Wallet for the new client
            wallet_number = str(uuid.uuid4()).replace('-', '')[:16].upper()
            Wallet.objects.create(
                user=client.user,
                wallet_number=wallet_number,
                balance=0.00,
                currency='RM',
                status='active'
            )
            
            # Send email verification
            AuthService.send_verification_email(request, client)
            return client

    @staticmethod
    def register_freelancer(username, email, password, full_name, skills):
        """Register a new freelancer and create a wallet."""
        with transaction.atomic():
            user = User.objects.create_user(username=username, email=email, password=password)
            freelancer = Freelancer.objects.create(
                user=user,
                full_name=full_name,
                skills=skills
            )
            
            # Create Wallet for the new freelancer
            wallet_number = str(uuid.uuid4()).replace('-', '')[:16].upper()
            Wallet.objects.create(
                user=user,
                wallet_number=wallet_number,
                balance=0.00,
                currency='RM',
                status='active'
            )
            return freelancer

    @staticmethod
    def send_verification_email(request, client):
        """Send verification email to a client."""
        from django.contrib.sites.shortcuts import get_current_site
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

    @staticmethod
    def verify_email(uidb64, token):
        """Verify client email using token."""
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
                return True, "Email verified successfully! You can now log in."
            return False, "Invalid or expired verification link."
        except (TypeError, ValueError, OverflowError, User.DoesNotExist, Client.DoesNotExist):
            return False, "Invalid verification link."
