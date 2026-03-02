"""
views/__init__.py – re-exports all view functions so urls.py
can continue using `from . import views` without changes.
"""
from core.views.auth import (
    login,
    admin_login,
    logout,
    registerSelection,
    register_client,
    register_freelancer,
    verify_email,
)

from core.views.common import home, aboutUS

from core.views.client import (
    client_home,
    client_search,
    client_freelancerProfile,
    client_support,
    client_settings,
    client_profile,
    client_editProfile,
    client_wallet,
    topUp,
    payment_success,
    payment_cancel,
    payment_cancel_pending,
    payment_continue,
    withdraw,
    client_transaction,
    toggle_balance_privacy,
    client_project,
    client_projectCreate,
    client_projectInfo,
    client_projectMatches,
    client_projectEdit,
    client_projectDelete,
    client_projectPublish,
    client_confirmPayment,
    client_invite_freelancer,
    accept_application,
    reject_application,
    client_request_revision,
    client_release_milestone_payment,
    submit_review,
)

from core.views.freelancer import (
    freelancer_home,
    freelancer_search_job,
    freelancer_track_project,
    freelancer_apply_project,
    freelancer_submit_milestone,
    freelancer_wallet,
    freelancer_settings,
    freelancer_profile,
)

from core.views.chat import (
    chat_view,
    start_chat,
    api_get_conversations,
    api_get_messages,
    api_download_attachment,
    api_send_message,
    api_toggle_mute,
)

from core.views.admin import (
    admin_dashboard,
    admin_support,
    admin_update_ticket,
    admin_user_management,
    admin_update_user,
    admin_activity_log,
    admin_reference_data,
)
