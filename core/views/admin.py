"""
Admin views – dashboard, support tickets, user management, reference data, activity log.
"""
import decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Sum, Q
from django.utils import timezone
from django.db.models import ProtectedError

from core.decorators import admin_required
from core.models import (
    Client, Freelancer, Project, Transaction,
    Ticket, AdminLog, Industry, ProjectCategory
)


@admin_required
def admin_dashboard(request):
    total_users = User.objects.count()
    total_clients = Client.objects.count()
    total_freelancers = Freelancer.objects.count()
    total_projects = Project.objects.count()
    open_projects = Project.objects.filter(status='open').count()
    completed_projects = Project.objects.filter(status='completed').count()

    total_earnings = Transaction.objects.filter(
        status='completed', transaction_type='payment'
    ).aggregate(total=Sum('amount'))['total'] or 0

    platform_revenue = total_earnings * decimal.Decimal('0.10')
    recent_users = User.objects.order_by('-date_joined')[:5]
    recent_projects = Project.objects.order_by('-created_at')[:5]

    return render(request, 'core/admin/admin_dashboard.html', {
        'total_users': total_users,
        'total_clients': total_clients,
        'total_freelancers': total_freelancers,
        'total_projects': total_projects,
        'open_projects': open_projects,
        'completed_projects': completed_projects,
        'total_earnings': total_earnings,
        'platform_revenue': platform_revenue,
        'recent_users': recent_users,
        'recent_projects': recent_projects,
    })


@admin_required
def admin_support(request):
    tickets = Ticket.objects.select_related('user').all()

    search = request.GET.get('search', '')
    if search:
        tickets = tickets.filter(
            Q(title__icontains=search) |
            Q(user__username__icontains=search) |
            Q(user__email__icontains=search)
        )

    category_filter = request.GET.get('category', '')
    if category_filter:
        tickets = tickets.filter(category=category_filter)

    status_filter = request.GET.get('status', '')
    if status_filter:
        tickets = tickets.filter(status=status_filter)

    paginator = Paginator(tickets, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'core/admin/admin_support.html', {
        'tickets': page_obj,
        'search': search,
        'category_filter': category_filter,
        'status_filter': status_filter,
        'category_choices': Ticket.CATEGORY_CHOICES,
        'status_choices': Ticket.STATUS_CHOICES,
    })


@admin_required
def admin_update_ticket(request, ticket_id):
    if request.method == 'POST':
        ticket = get_object_or_404(Ticket, id=ticket_id)
        status = request.POST.get('status')
        old_status = ticket.status

        if status and status in dict(Ticket.STATUS_CHOICES):
            ticket.status = status
            if status in ['resolved', 'closed'] and not ticket.resolved_at:
                ticket.resolved_at = timezone.now()
            ticket.save()

            AdminLog.objects.create(
                admin_user=request.user,
                action='update',
                target_model='Ticket',
                target_id=str(ticket.id),
                description=f"Updated ticket status from '{old_status}' to '{status}' for ticket '{ticket.title}' (ID: {ticket.id})."
            )
            return JsonResponse({'status': 'success', 'message': 'Ticket updated successfully.'})
        return JsonResponse({'status': 'error', 'message': 'Invalid status provided.'}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=400)


@admin_required
def admin_user_management(request):
    users = User.objects.all().order_by('-date_joined')

    search = request.GET.get('search', '')
    if search:
        users = users.filter(
            Q(username__icontains=search) |
            Q(email__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search)
        )

    role_filter = request.GET.get('role', '')
    if role_filter == 'client':
        users = users.filter(client__isnull=False)
    elif role_filter == 'freelancer':
        users = users.filter(freelancer__isnull=False)
    elif role_filter == 'admin':
        users = users.filter(is_superuser=True)

    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)

    paginator = Paginator(users, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'core/admin/admin_user.html', {
        'users': page_obj,
        'search': search,
        'role_filter': role_filter,
        'status_filter': status_filter,
    })


@admin_required
def admin_update_user(request, user_id):
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id)
        username = request.POST.get('username')
        status = request.POST.get('status')
        phone = request.POST.get('phone')

        if username:
            user.username = username
        if status:
            user.is_active = (status == 'active')
        user.save()

        target_model = 'User'
        if hasattr(user, 'client') and user.client:
            user.client.phone = phone
            user.client.save()
            target_model = 'Client'
        elif hasattr(user, 'freelancer') and user.freelancer:
            user.freelancer.phone = phone
            user.freelancer.save()
            target_model = 'Freelancer'

        AdminLog.objects.create(
            admin_user=request.user,
            action='update',
            target_model=target_model,
            target_id=str(user.id),
            description=f"Updated user details for '{user.email}' (ID: {user.id})."
        )
        return JsonResponse({'status': 'success', 'message': 'User updated successfully.'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=400)


@admin_required
def admin_activity_log(request):
    logs = AdminLog.objects.select_related('admin_user').all()

    action_filter = request.GET.get('action', '')
    if action_filter:
        logs = logs.filter(action=action_filter)

    admin_filter = request.GET.get('admin', '')
    if admin_filter:
        logs = logs.filter(admin_user__username__icontains=admin_filter)

    paginator = Paginator(logs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'core/admin/admin_activityLog.html', {
        'logs': page_obj,
        'action_filter': action_filter,
        'admin_filter': admin_filter,
        'action_choices': AdminLog.ACTION_CHOICES,
    })


@admin_required
def admin_reference_data(request):
    industries = Industry.objects.all().order_by('name')
    categories = ProjectCategory.objects.all().order_by('name')

    if request.method == 'POST':
        action = request.POST.get('action')
        ref_type = request.POST.get('type')
        name = request.POST.get('name')
        pk = request.POST.get('pk')

        try:
            obj_name = name  # track for logging
            if action == 'add':
                if ref_type == 'industry':
                    Industry.objects.create(name=name)
                    messages.success(request, f"Industry Type '{name}' added successfully.")
                else:
                    ProjectCategory.objects.create(name=name)
                    messages.success(request, f"Project Category '{name}' added successfully.")

            elif action == 'edit':
                if ref_type == 'industry':
                    obj = Industry.objects.get(pk=pk)
                    old_name = obj.name
                    obj.name = name
                    obj.save()
                    messages.success(request, f"Industry Type updated from '{old_name}' to '{name}'.")
                else:
                    obj = ProjectCategory.objects.get(pk=pk)
                    old_name = obj.name
                    obj.name = name
                    obj.save()
                    messages.success(request, f"Project Category updated from '{old_name}' to '{name}'.")

            elif action == 'toggle_status':
                if ref_type == 'industry':
                    obj = Industry.objects.get(pk=pk)
                    obj.is_active = not obj.is_active
                    obj.save()
                    status_word = "activated" if obj.is_active else "deactivated"
                    messages.success(request, f"Industry Type '{obj.name}' {status_word}.")
                else:
                    obj = ProjectCategory.objects.get(pk=pk)
                    obj.is_active = not obj.is_active
                    obj.save()
                    status_word = "activated" if obj.is_active else "deactivated"
                    messages.success(request, f"Project Category '{obj.name}' {status_word}.")

            elif action == 'delete':
                if ref_type == 'industry':
                    obj = Industry.objects.get(pk=pk)
                    obj_name = obj.name
                    try:
                        obj.delete()
                        messages.success(request, f"Industry Type '{obj_name}' permanently deleted.")
                    except ProtectedError:
                        messages.error(request, f"Cannot delete '{obj_name}' because it is linked to existing clients. Please deactivate it instead.")
                else:
                    obj = ProjectCategory.objects.get(pk=pk)
                    obj_name = obj.name
                    try:
                        obj.delete()
                        messages.success(request, f"Project Category '{obj_name}' permanently deleted.")
                    except ProtectedError:
                        messages.error(request, f"Cannot delete '{obj_name}' because it is linked to existing projects. Please deactivate it instead.")

            log_action_type = {'add': 'create', 'delete': 'delete'}.get(action, 'update')
            display_type = "Industry Type" if ref_type == 'industry' else "Project Category"
            action_map = {'add': 'Added', 'edit': 'Edited', 'delete': 'Deleted', 'toggle_status': 'Toggled'}
            friendly_action = action_map.get(action, action)

            AdminLog.objects.create(
                admin_user=request.user,
                action=log_action_type,
                target_model='Industry' if ref_type == 'industry' else 'ProjectCategory',
                target_id=pk if pk else 'new',
                description=f"Managed reference data: {friendly_action} {display_type} {obj_name}",
                ip_address=request.META.get('REMOTE_ADDR')
            )

        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

        return redirect('admin_reference_data')

    return render(request, 'core/admin/admin_reference.html', {
        'industries': industries,
        'categories': categories,
        'active_menu': 'reference',
    })
