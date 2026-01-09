# core/urls.py
from django.urls import path
from .views import match_jobs, login
from . import views  # for home view

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login, name='login'),
    path('register/client/', views.register_client, name='register_client'),
    path('verify-email/<str:uidb64>/<str:token>/', views.verify_email, name='verify_email'),
    path('match/', match_jobs, name='match_jobs'),
    path('client_home/', views.client_home, name='client_home'),
    path('client_profile/', views.client_profile, name='client_profile'),
    path('client_editProfile/', views.client_editProfile, name='client_editProfile'),
    path('client_project/', views.client_project, name='client_project'),
    path('client_projectCreate/', views.client_projectCreate, name='client_projectCreate'),
    path('client_projectInfo/', views.client_projectInfo, name='client_projectInfo'),
    path('about-us/', views.client_about, name='client_about'),
    path('client_chat/', views.client_chat, name='client_chat'),
    path('logout/', views.logout, name='logout'),
]