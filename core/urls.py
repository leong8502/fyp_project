# core/urls.py
from django.urls import path
from .views import match_jobs
from . import views  # for home view

urlpatterns = [
    path('', views.home, name='home'),
    path('match/', match_jobs, name='match_jobs'),
]