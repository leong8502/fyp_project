# core/urls.py
from django.urls import path
from .views import match_jobs
from . import views  # for home view

urlpatterns = [
    path('', views.home, name='home'),
    path('match/', match_jobs, name='match_jobs'),
    path('client_home/', views.client_home, name='client_home'),
    path('project/', views.client_project, name='client_project'),
    path('about-us/', views.client_about, name='client_about'),
    path('message/', views.client_chat, name='client_chat'),
]