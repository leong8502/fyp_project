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
    Ticket, AdminLog, Industry, ProjectCategory, Review
)
from core.forms import StaffCreationForm


@admin_required
def admin_dashboard(request):
    total_users = User.objects.count()
    total_clients = Client.objects.count()
    total_freelancers = Freelancer.objects.count()
    total_projects = Project.objects.count()
    open_projects = Project.objects.filter(status='open').count()
    completed_projects = Project.objects.filter(status='completed').count()

    from core.models import Escrow
    # Total earnings = sum of all project budgets (Escrow total_amount)
    total_earnings = Escrow.objects.aggregate(total=Sum('total_amount'))['total'] or decimal.Decimal('0.00')
    
    # Platform revenue = sum of all platform fees stored in Escrow
    platform_revenue = Escrow.objects.aggregate(total_fees=Sum('platform_fee'))['total_fees'] or decimal.Decimal('0.00')
    
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
        search_filter = Q(title__icontains=search) | \
                        Q(user__username__icontains=search) | \
                        Q(user__email__icontains=search)
        
        if search.isdigit():
            search_filter |= Q(pk=search)
            
        tickets = tickets.filter(search_filter)

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
    # Only show clients and freelancers (exclude staff and superusers)
    users = User.objects.filter(is_staff=False, is_superuser=False).order_by('-date_joined')

    search = request.GET.get('search', '')
    if search:
        search_filter = Q(username__icontains=search) | \
                        Q(email__icontains=search) | \
                        Q(first_name__icontains=search) | \
                        Q(last_name__icontains=search)
        
        if search.isdigit():
            search_filter |= Q(pk=search)
            
        users = users.filter(search_filter)

    role_filter = request.GET.get('role', '')
    if role_filter == 'client':
        users = users.filter(client__isnull=False)
    elif role_filter == 'freelancer':
        users = users.filter(freelancer__isnull=False)

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


@admin_required
def admin_staff_management(request):
    if not request.user.is_superuser:
        messages.error(request, "Access denied. Superuser privileges required.")
        return redirect('admin_dashboard')

    staff_users = User.objects.filter(is_staff=True, is_superuser=False).order_by('-date_joined')
    
    if request.method == 'POST':
        form = StaffCreationForm(request.POST)
        if form.is_valid():
            staff = form.save()
            messages.success(request, f"Staff account for {staff.username} created successfully.")
            
            AdminLog.objects.create(
                admin_user=request.user,
                action='create',
                target_model='User',
                target_id=str(staff.id),
                description=f"Created staff account '{staff.username}' ({staff.email})."
            )
            return redirect('admin_staff_management')
        else:
            for field, field_errors in form.errors.items():
                for error in field_errors:
                    field_label = form.fields[field].label if field in form.fields else field.replace('_', ' ').capitalize()
                    messages.error(request, f"{field_label}: {error}")
    else:
        form = StaffCreationForm()

    return render(request, 'core/admin/admin_staff.html', {
        'staff_users': staff_users,
        'form': form,
        'active_menu': 'staff',
    })


@admin_required
def admin_update_staff(request, staff_id):
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Superuser privileges required.'}, status=403)

    staff = get_object_or_404(User, id=staff_id, is_staff=True, is_superuser=False)
    
    if request.method == 'POST':
        is_active = request.POST.get('is_active') == 'true'

        staff.is_active = is_active
        staff.save()

        AdminLog.objects.create(
            admin_user=request.user,
            action='update',
            target_model='User',
            target_id=str(staff.id),
            description=f"Updated status for staff account '{staff.username}' to {'Active' if is_active else 'Inactive'}."
        )

        return JsonResponse({'status': 'success', 'message': f'Status for {staff.username} updated successfully.'})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


@admin_required
def admin_project_management(request):
    projects = Project.objects.all().select_related(
        'client', 'category', 'escrow'
    ).prefetch_related(
        'applications__freelancer__user'
    ).order_by('-created_at')

    search = request.GET.get('search', '')
    if search:
        search_filter = Q(title__icontains=search) | \
                        Q(description__icontains=search) | \
                        Q(client__company_name__icontains=search)
        
        if search.isdigit():
            search_filter |= Q(pk=search)
            
        projects = projects.filter(search_filter)

    status_filter = request.GET.get('status', '')
    if status_filter:
        projects = projects.filter(status=status_filter)

    paginator = Paginator(projects, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'core/admin/admin_project.html', {
        'projects': page_obj,
        'search': search,
        'status_filter': status_filter,
        'active_menu': 'projects',
    })


@admin_required
def admin_update_project_status(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        
        # Validate status choice
        valid_statuses = [choice[0] for choice in Project.STATUS_CHOICES]
        if new_status not in valid_statuses:
            return JsonResponse({'status': 'error', 'message': 'Invalid status choice.'})

        old_status = project.status
        project.status = new_status
        
        # If moving to open, set published_at if not already set
        if new_status == 'open' and not project.published_at:
            project.published_at = timezone.now()
            
        project.save()

        AdminLog.objects.create(
            admin_user=request.user,
            action='update',
            target_model='Project',
            target_id=str(project.id),
            description=f"Updated project '{project.title}' status from '{old_status}' to '{new_status}'."
        )

        return JsonResponse({'status': 'success', 'message': f'Project status updated to {project.get_status_display()} successfully.'})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


@admin_required
def admin_cancel_project(request, project_id):
    """Admin endpoint to cancel a project and refund escrow."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    project = get_object_or_404(Project, id=project_id)
    
    if project.status in ['cancelled', 'completed']:
        return JsonResponse({'status': 'error', 'message': f'Cannot cancel a project that is already {project.status}.'})

    try:
        from core.services.project_service import ProjectService
        ProjectService.admin_cancel_project(project, request.user)
        
        AdminLog.objects.create(
            admin_user=request.user,
            action='update',
            target_model='Project',
            target_id=str(project.id),
            description=f"Admin cancelled project '{project.title}' (ID: {project.id}) and refunded escrow."
        )
        
        return JsonResponse({'status': 'success', 'message': 'Project successfully cancelled and escrow refunded.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Error cancelling project: {str(e)}'})

@admin_required
def admin_remove_freelancer(request, project_id):
    """Admin endpoint to remove a specific freelancer from a project."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    project = get_object_or_404(Project, id=project_id)
    freelancer_id = request.POST.get('freelancer_id')
    
    if not freelancer_id:
        return JsonResponse({'status': 'error', 'message': 'Freelancer ID is required.'}, status=400)
        
    if project.status not in ['open', 'in_progress']:
        return JsonResponse({'status': 'error', 'message': f'Cannot modify a project that is {project.status}.'})

    try:
        from core.models import Freelancer
        freelancer = get_object_or_404(Freelancer, id=freelancer_id)
        
        # Check if freelancer is hired for this project
        if not project.applications.filter(freelancer=freelancer, status='accepted').exists():
            return JsonResponse({'status': 'error', 'message': 'Selected freelancer is not active on this project.'}, status=400)

        from core.services.project_service import ProjectService
        ProjectService.admin_remove_freelancer(project, request.user, freelancer)
        
        AdminLog.objects.create(
            admin_user=request.user,
            action='update',
            target_model='Project',
            target_id=str(project.id),
            description=f"Admin removed freelancer {freelancer.user.username} from project '{project.title}' (ID: {project.id})."
        )
        
        return JsonResponse({'status': 'success', 'message': 'Freelancer successfully removed from project.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Error removing freelancer: {str(e)}'})

@admin_required
def admin_review_management(request):
    reviews = Review.objects.all().select_related(
        'project', 'reviewer', 'reviewee'
    ).order_by('-created_at')

    search = request.GET.get('search', '')
    if search:
        search_filter = Q(project__title__icontains=search) | \
                        Q(reviewer__username__icontains=search) | \
                        Q(reviewee__username__icontains=search) | \
                        Q(comment__icontains=search)
        
        if search.isdigit():
            search_filter |= Q(pk=search)
            
        reviews = reviews.filter(search_filter)

    visibility_filter = request.GET.get('visibility', '')
    if visibility_filter == 'hidden':
        reviews = reviews.filter(is_hidden=True)
    elif visibility_filter == 'visible':
        reviews = reviews.filter(is_hidden=False)

    paginator = Paginator(reviews, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'core/admin/admin_review.html', {
        'reviews': page_obj,
        'search': search,
        'visibility_filter': visibility_filter,
        'active_menu': 'reviews',
    })

@admin_required
def admin_update_review_status(request, review_id):
    review = get_object_or_404(Review, id=review_id)
    
    if request.method == 'POST':
        action = request.POST.get('action') # 'hide' or 'show'
        
        if action == 'hide':
            review.is_hidden = True
            message = f"Review #{review.id} is now hidden."
        elif action == 'show':
            review.is_hidden = False
            message = f"Review #{review.id} is now visible."
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid action.'})
            
        review.save()

        AdminLog.objects.create(
            admin_user=request.user,
            action='update',
            target_model='Review',
            target_id=str(review.id),
            description=f"Admin {action} review '{review.id}' for project '{review.project.title}'."
        )

        return JsonResponse({'status': 'success', 'message': message})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)
