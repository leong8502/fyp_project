# core/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # ── Shared / Auth ───────────────────────────────────────────────────────
    path('', views.home, name='home'),
    path('accounts/login/', views.login, name='login'),
    path('panel/login/', views.admin_login, name='admin_login'),
    path('logout/', views.logout, name='logout'),

    # ── Registration / Email ────────────────────────────────────────────────
    path('register/selection/', views.registerSelection, name='registerSelection'),
    path('register/freelancer/', views.register_freelancer, name='register_freelancer'),
    path('register/client/', views.register_client, name='register_client'),
    path('verify-email/<str:uidb64>/<str:token>/', views.verify_email, name='verify_email'),

    # ── Password Reset (Django built-in) ────────────────────────────────────
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

    # ── Wallet / Payments (shared) ──────────────────────────────────────────
    path('top-up/', views.topUp, name='topUp'),
    path('payment-success/', views.payment_success, name='payment_success'),
    path('payment-cancel/', views.payment_cancel, name='payment_cancel'),
    path('payment-continue/<int:transaction_id>/', views.payment_continue, name='payment_continue'),
    path('payment-cancel-pending/<int:transaction_id>/', views.payment_cancel_pending, name='payment_cancel_pending'),
    path('withdraw/', views.withdraw, name='withdraw'),
    path('wallet/toggle-privacy/', views.toggle_balance_privacy, name='toggle_balance_privacy'),

    # ── Reviews (shared) ───────────────────────────────────────────────────
    path('project/review/<int:project_id>/', views.submit_review, name='submit_review'),

    # ── Application / Proposal Actions (shared) ────────────────────────────
    path('project/application/<int:app_id>/accept/', views.accept_application, name='accept_application'),
    path('project/application/<int:app_id>/reject/', views.reject_application, name='reject_application'),

    # ── Milestone Actions (shared) ─────────────────────────────────────────
    path('milestone/<int:milestone_id>/submit/', views.freelancer_submit_milestone, name='freelancer_submit_milestone'),
    path('milestone/<int:milestone_id>/revision/', views.client_request_revision, name='client_request_revision'),
    path('milestone/<int:milestone_id>/release-payment/', views.client_release_milestone_payment, name='client_release_milestone_payment'),

    # ── Client ─────────────────────────────────────────────────────────────
    path('client/home/', views.client_home, name='client_home'),
    path('aboutUS/', views.aboutUS, name='about'),
    path('client/search/', views.client_search, name='client_search'),
    path('client/freelancerProfile/<int:freelancer_id>/', views.client_freelancerProfile, name='client_freelancerProfile'),
    path('client/support/', views.client_support, name='client_support'),
    path('client/settings/', views.client_settings, name='client_settings'),
    path('client/profile/', views.client_profile, name='client_profile'),
    path('client/edit_profile/', views.client_editProfile, name='client_editProfile'),

    path('client/wallet/', views.client_wallet, name='client_wallet'),
    path('client/wallet/transaction/', views.client_transaction, name='client_transaction'),
    path('client/invite/<int:freelancer_id>/', views.client_invite_freelancer, name='client_invite_freelancer'),
    # Client – Projects
    path('client/project/', views.client_project, name='client_project'),
    path('client/project/create/', views.client_projectCreate, name='client_projectCreate'),
    path('client/project/info/<int:project_id>/', views.client_projectInfo, name='client_projectInfo'),
    path('client/project/matches/<int:project_id>/', views.client_projectMatches, name='client_projectMatches'),
    path('client/project/edit/<int:project_id>/', views.client_projectEdit, name='client_projectEdit'),
    path('client/project/delete/<int:project_id>/', views.client_projectDelete, name='client_projectDelete'),
    path('client/project/<int:project_id>/publish/', views.client_projectPublish, name='client_projectPublish'),
    path('client/project/<int:project_id>/confirm-payment/', views.client_confirmPayment, name='client_confirmPayment'),
    path('client/project/<int:project_id>/request-cancel/', views.client_request_cancellation, name='client_request_cancellation'),
    path('client/project/<int:project_id>/report/', views.report_project, name='report_project'),

    # ── Notifications ──────────────────────────────────────────────────────
    path('notifications/', views.notifications, name='notifications'),
    path('api/unread_count/', views.api_unread_notifications_count, name='api_unread_count'),
    path('api/notifications/recent/', views.api_get_recent_notifications, name='api_get_recent_notifications'),
    path('api/notifications/mark-all-read/', views.api_mark_all_notifications_as_read, name='api_mark_all_read'),

    # ── Chat ───────────────────────────────────────────────────────────────
    path('chat/', views.chat_view, name='chat'),
    path('chat/start/<int:user_id>/', views.start_chat, name='start_chat'),
    path('api/chat/conversations/', views.api_get_conversations, name='api_get_conversations'),
    path('api/chat/messages/<int:conversation_id>/', views.api_get_messages, name='api_get_messages'),
    path('api/chat/send/<int:conversation_id>/', views.api_send_message, name='api_send_message'),
    path('api/chat/download/<int:message_id>/', views.api_download_attachment, name='api_download_attachment'),
    path('api/chat/mute/<int:conversation_id>/', views.api_toggle_mute, name='api_toggle_mute'),

    # ── Freelancer ─────────────────────────────────────────────────────────
    path('freelancer/home/', views.freelancer_home, name='freelancer_home'),
    path('freelancer/profile/', views.freelancer_profile, name='freelancer_profile'),
    path('freelancer/search-job/', views.freelancer_search_job, name='freelancer_search_job'),
    path('freelancer/apply/<int:project_id>/', views.freelancer_apply_project, name='freelancer_apply_project'),
    path('freelancer/track-project/', views.freelancer_track_project, name='freelancer_track_project'),
    path('freelancer/wallet/', views.freelancer_wallet, name='freelancer_wallet'),
    path('freelancer/settings/', views.freelancer_settings, name='freelancer_settings'),
    path('freelancer/cancellation/<int:cancellation_id>/respond/', views.freelancer_respond_cancellation, name='freelancer_respond_cancellation'),

    # ── Admin ──────────────────────────────────────────────────────────────
    path('panel/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('panel/support/', views.admin_support, name='admin_support'),
    path('panel/support/update/<int:ticket_id>/', views.admin_update_ticket, name='admin_update_ticket'),
    path('panel/users/', views.admin_user_management, name='admin_user_management'),
    path('panel/projects/', views.admin_project_management, name='admin_project_management'),
    path('panel/projects/update-status/<int:project_id>/', views.admin_update_project_status, name='admin_update_project_status'),
    path('panel/staff/', views.admin_staff_management, name='admin_staff_management'),
    path('panel/staff/update/<int:staff_id>/', views.admin_update_staff, name='admin_update_staff'),
    path('panel/users/<int:user_id>/update/', views.admin_update_user, name='admin_update_user'),
    path('panel/activity-log/', views.admin_activity_log, name='admin_activity_log'),
    path('panel/reference-data/', views.admin_reference_data, name='admin_reference_data'),
]