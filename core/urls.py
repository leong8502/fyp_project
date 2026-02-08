# core/urls.py
from django.urls import path
from .views import match_jobs, login
from . import views  # for home view
from django.contrib.auth import views as auth_views

urlpatterns = [
    # both part
    path('', views.home, name='home'),
    path('accounts/login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('top-up/', views.topUp, name='topUp'),
    path('withdraw/', views.withdraw, name='withdraw'),
    path('wallet/toggle-privacy/', views.toggle_balance_privacy, name='toggle_balance_privacy'),
    path('project/review/<int:project_id>/', views.submit_review, name='submit_review'),
    # register part
    path('register/selection/', views.registerSelection, name='registerSelection'),
    path('register/freelancer/', views.register_freelancer, name='register_freelancer'),
    path('register/client/', views.register_client, name='register_client'),
    path('verify-email/<str:uidb64>/<str:token>/', views.verify_email, name='verify_email'),
    
    # Password Reset
    path('password-reset/', 
         auth_views.PasswordResetView.as_view(template_name='reset_password/password_reset_form.html'), 
         name='password_reset'),
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(template_name='reset_password/password_reset_done.html'), 
         name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(template_name='reset_password/password_reset_confirm.html'), 
         name='password_reset_confirm'),
    path('password-reset-complete/', 
         auth_views.PasswordResetCompleteView.as_view(template_name='reset_password/password_reset_complete.html'), 
         name='password_reset_complete'),

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
    path('client/project/edit/<int:project_id>/', views.client_projectEdit, name='client_projectEdit'),
    path('client/project/delete/<int:project_id>/', views.client_projectDelete, name='client_projectDelete'),
    path('client/project/info/<int:project_id>/', views.client_projectInfo, name='client_projectInfo'),
    path('client/project/matches/<int:project_id>/', views.client_projectMatches, name='client_projectMatches'),
    path('client/project/<int:project_id>/publish/', views.client_projectPublish, name='client_projectPublish'),
    path('client/project/<int:project_id>/confirm-payment/', views.client_confirmPayment, name='client_confirmPayment'),
    path('client/about-us/', views.client_about, name='client_about'),
    
    # Chat API
    path('chat/', views.chat_view, name='chat'),
    path('chat/start/<int:user_id>/', views.start_chat, name='start_chat'),
    path('api/chat/conversations/', views.api_get_conversations, name='api_get_conversations'),
    path('api/chat/messages/<int:conversation_id>/', views.api_get_messages, name='api_get_messages'),
    path('api/chat/send/<int:conversation_id>/', views.api_send_message, name='api_send_message'),
    path('api/chat/download/<int:message_id>/', views.api_download_attachment, name='api_download_attachment'),
    path('api/chat/mute/<int:conversation_id>/', views.api_toggle_mute, name='api_toggle_mute'),

    path('client/search/', views.client_search, name='client_search'),
    path('client/freelancerProfile/<int:freelancer_id>/', views.client_freelancerProfile, name='client_freelancerProfile'),
    path('client/settings/', views.client_settings, name='client_settings'),
    # freelancer part
    path('freelancer/home/', views.freelancer_home, name='freelancer_home'),
    path('freelancer/profile/', views.freelancer_profile, name='freelancer_profile'),
]