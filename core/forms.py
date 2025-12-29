from django import forms

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