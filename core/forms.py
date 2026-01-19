from django import forms
from django.contrib.auth.models import User
from .models import Client, Project, Industry
from django.core.validators import RegexValidator
from django.utils import timezone
from datetime import datetime

class SkillsForm(forms.Form):
    skills = forms.CharField(
        label="Your Skills",
        widget=forms.Textarea(attrs={
            'rows': 5,
            'placeholder': 'e.g., Python, Django, BERT, Machine Learning, PostgreSQL',
            'class': 'form-control'
        }),
        help_text="Enter your skills to find matching jobs (AI uses semantic similarity)"
    )

class ClientRegistrationForm(forms.ModelForm):
    full_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., John Doe'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'john@company.com'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'At least 8 characters'}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))

    class Meta:
        model = Client
        fields = ['company_name', 'phone', 'industry_type']
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., TechVision Sdn Bhd'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+60 12-345 6789'}),
            'industry_type': forms.Select(attrs={'class': 'form-control', 'id': 'industry'}),
        }

    def __init__(self, *args, **kwargs):
        super(ClientRegistrationForm, self).__init__(*args, **kwargs)
        self.fields['industry_type'].queryset = Industry.objects.all()
        self.fields['industry_type'].empty_label = "Select Industry"

    def clean_email(self):
        email = self.cleaned_data.get('email').lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Email is already registered.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Passwords do not match")
        
        return cleaned_data

    def save(self, commit=True):
        import uuid
        full_name = self.cleaned_data['full_name']
        first_name = full_name.split()[0] if full_name else ''
        last_name = ' '.join(full_name.split()[1:]) if len(full_name.split()) > 1 else ''
        
        user = User.objects.create_user(
            username=self.cleaned_data['email'],
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password'],
            first_name=first_name,
            last_name=last_name,
            is_active=False 
        )
        client = super().save(commit=False)
        client.user = user
        client.email_verification_token = str(uuid.uuid4())
        
        if commit:
            client.save()
        return client

class ClientProfileForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            'company_name', 'tagline', 'description', 'phone', 'address',
            'industry_type', 'company_size', 'year_founded', 'website_url',
            'achievements', 'languages', 'tags', 'linkedIn_url', 'instagram_url',
            'facebook_url', 'profile_image', 'background_image'
        ]
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'form-control', 'id': 'name'}),
            'tagline': forms.TextInput(attrs={'class': 'form-control', 'id': 'tagline', 'placeholder': 'e.g. Innovative Software Solutions for the Modern Enterprise'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'id': 'description'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'id': 'phone', 'placeholder': '+1 234 567 890'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'id': 'address', 'placeholder': 'Street, City, Country'}),
            'industry_type': forms.Select(attrs={'class': 'form-control', 'id': 'industry'}),
            'company_size': forms.Select(attrs={'class': 'form-control', 'id': 'company-size'}),
            'year_founded': forms.NumberInput(attrs={'class': 'form-control', 'id': 'year-founded', 'placeholder': 'e.g., 2020'}),
            'website_url': forms.URLInput(attrs={'class': 'form-control', 'id': 'website', 'placeholder': 'https://example.com'}),
            'achievements': forms.Textarea(attrs={'class': 'form-control', 'id': 'achievements', 'placeholder': 'Key achievements or highlights...'}),
            'languages': forms.HiddenInput(attrs={'id': 'languages-hidden'}),
            'tags': forms.HiddenInput(attrs={'id': 'tags-hidden'}),
            'linkedIn_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://linkedin.com/in/...'}),
            'instagram_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://instagram.com/...'}),
            'facebook_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://facebook.com/...'}),
            'profile_image': forms.FileInput(attrs={'id': 'profile-image-upload'}),
            'background_image': forms.FileInput(attrs={'id': 'background-image-upload'}),
        }

    def __init__(self, *args, **kwargs):
        super(ClientProfileForm, self).__init__(*args, **kwargs)
        self.fields['industry_type'].queryset = Industry.objects.all()
        self.fields['industry_type'].empty_label = "Select Industry..."
        self.fields['industry_type'].required = False
        self.fields['company_size'].required = False

class ProjectForm(forms.ModelForm):
    attachments = forms.FileField(required=False, widget=forms.ClearableFileInput(attrs={'class': 'form-control'}))

    class Meta:
        model = Project
        fields = [
            'title', 'description', 'category', 'budget', 'deadline',
            'required_skills', 'experience_level', 'year_of_experience',
            'preferred_language', 'status'
        ]
        
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Corporate Website Redesign'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Provide a detailed description...'}),
            'category': forms.Select(attrs={'class': 'form-control', 'id': 'category'}), 
            'budget': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 12000', 'min': '1', 'step': '1'}),
            'deadline': forms.DateInput(attrs={'type': 'date', 'class': 'form-control', 'id': 'deadline'}),
            'required_skills': forms.HiddenInput(attrs={'id': 'required_skills'}), # Handled by JS
            'experience_level': forms.Select(attrs={'class': 'form-control', 'id': 'experience_level'}),
            'year_of_experience': forms.Select(attrs={'class': 'form-control', 'id': 'year_of_experience', 'choices': [
                (0, 'Less than 1 year'), (1, '1 Year'), (2, '2 Years'), (3, '3 Years'), (4, '4 Years'), (5, '5+ Years')
            ]}),
            'preferred_language': forms.HiddenInput(attrs={'id': 'preferred_language'}), # Handled by JS
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super(ProjectForm, self).__init__(*args, **kwargs)
        # Custom choices for year_of_experience since it's an IntegerField in model but Select in UI
        YEAR_CHOICES = [
            (0, 'Less than 1 year'),
            (1, '1 Year'),
            (2, '2 Years'),
            (3, '3 Years'),
            (4, '4 Years'),
            (5, '5+ Years')
        ]
        self.fields['year_of_experience'].widget = forms.Select(choices=YEAR_CHOICES)
        self.fields['category'].empty_label = "Select Category..."
        self.fields['required_skills'].required = False
        self.fields['preferred_language'].required = False
        self.fields['status'].required = False # Status defaults to 'draft' in logic

    def clean(self):
        cleaned_data = super().clean()
        
        # 1. Project Deadline Validation
        deadline = cleaned_data.get('deadline')
        today = timezone.now().date()
        
        if deadline and deadline < today:
             self.add_error('deadline', "Project deadline cannot be in the past.")

        # 2. Milestone Validation (Accessing raw data)
        # Note: self.data contains the request.POST data
        m_amounts = self.data.getlist('milestone_amount[]')
        m_deadlines = self.data.getlist('milestone_deadline[]')
        budget = cleaned_data.get('budget')

        if m_amounts and budget:
            total_milestone_amount = sum(float(a) for a in m_amounts if a)
            if abs(float(budget) - total_milestone_amount) > 0.01:
                # Add validation error to non-field error or budget field
                raise forms.ValidationError(f"Total milestone budget (${total_milestone_amount}) must equal project budget (${budget}).")

        prev_deadline = None
        for i, deadline_str in enumerate(m_deadlines):
            if not deadline_str: continue
            try:
                m_deadline = datetime.strptime(deadline_str, '%Y-%m-%d').date()
                
                if deadline and m_deadline > deadline:
                    raise forms.ValidationError(f"Milestone {i+1} deadline cannot be after project deadline.")
                
                if m_deadline < today:
                     raise forms.ValidationError(f"Milestone {i+1} deadline cannot be in the past.")
                     
                if prev_deadline and m_deadline <= prev_deadline:
                     raise forms.ValidationError(f"Milestone {i+1} deadline must be after previous milestone.")
                
                prev_deadline = m_deadline
            except ValueError:
                continue # Skip invalid dates (handled by frontend or basic type checks)

        return cleaned_data

class TopUpForm(forms.Form):
    amount = forms.DecimalField(
        min_value=20,
        decimal_places=2,
        required=True,
        error_messages={'min_value': "Minimum top up amount is RM 20."}
    )
    payment_method = forms.CharField(required=True)

class WithdrawForm(forms.Form):
    amount = forms.DecimalField(
        decimal_places=2,
        required=True,
        min_value=20,
        error_messages={'min_value': "Minimum withdrawal amount is RM 20."}
    )
    bank_name = forms.CharField(required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Select Bank'}))
    
    account_number = forms.CharField(
        required=True, 
        validators=[RegexValidator(r'^\d+$', 'Only numbers are allowed.')],
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Account Number'})
    )
    
    def __init__(self, *args, **kwargs):
        self.user_wallet = kwargs.pop('wallet', None)
        super(WithdrawForm, self).__init__(*args, **kwargs)

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if self.user_wallet and amount > self.user_wallet.balance:
            raise forms.ValidationError(f"Insufficient balance. Your current balance is RM {self.user_wallet.balance}.")
        return amount