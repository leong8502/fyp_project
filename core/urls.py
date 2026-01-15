# core/urls.py
from django.urls import path
from .views import match_jobs, login
from . import views  # for home view

urlpatterns = [
    # both part
    path('', views.home, name='home'),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    # register part
    path('register/selection/', views.registerSelection, name='registerSelection'),
    path('register/freelancer/', views.register_freelancer, name='register_freelancer'),
    path('register/client/', views.register_client, name='register_client'),
    path('verify-email/<str:uidb64>/<str:token>/', views.verify_email, name='verify_email'),
    # idk what is this part
    path('match/', match_jobs, name='match_jobs'),
    # client part
    path('client/home/', views.client_home, name='client_home'),
    path('client/profile/', views.client_profile, name='client_profile'),
    path('client/edit_profile/', views.client_editProfile, name='client_editProfile'),
    path('client/wallet/', views.client_wallet, name='client_wallet'),
    path('client/wallet/transaction/', views.client_transaction, name='client_transaction'),
    path('client/project/', views.client_project, name='client_project'),
    path('client/project/create/', views.client_projectCreate, name='client_projectCreate'),
    path('client/project/info/<int:project_id>/', views.client_projectInfo, name='client_projectInfo'),
    path('client/about-us/', views.client_about, name='client_about'),
    path('client/chat/', views.client_chat, name='client_chat'),
    # freelancer part
]