import uuid
import decimal
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from core.models import (
    Project, Milestone, ProjectApplication,
    ProjectActivity, Escrow, Transaction, Wallet,
    CancellationRequest
)


class ProjectService:

    @staticmethod
    def create_project(client, form, post_data):
        """Create a draft project with milestones."""
        with transaction.atomic():
            project = form.save(commit=False)
            project.client = client
            project.status = 'draft'

            m_titles = post_data.getlist('milestone_title[]')
            m_descriptions = post_data.getlist('milestone_description[]')
            m_amounts = post_data.getlist('milestone_amount[]')
            m_deadlines = post_data.getlist('milestone_deadline[]')

            project.save()

            valid_milestones_count = 0
            for i in range(len(m_titles)):
                if m_titles[i] and m_amounts[i] and m_deadlines[i]:
                    Milestone.objects.create(
                        project=project,
                        title=m_titles[i],
                        description=m_descriptions[i] if i < len(m_descriptions) else '',
                        amount=m_amounts[i],
                        deadline=m_deadlines[i],
                        order=i + 1
                    )
                    valid_milestones_count += 1
            
            if valid_milestones_count == 0:
                raise ValueError("At least one valid milestone is required.")
        return project

    @staticmethod
    def update_project(project, client, form, post_data, remove_attachment=False):
        """Update a draft project including its milestones."""
        with transaction.atomic():
            project = form.save(commit=False)
            project.client = client
            project.status = 'draft'

            m_titles = post_data.getlist('milestone_title[]')
            m_descriptions = post_data.getlist('milestone_description[]')
            m_amounts = post_data.getlist('milestone_amount[]')
            m_deadlines = post_data.getlist('milestone_deadline[]')

            project.save()

            if remove_attachment and project.attachment:
                project.attachment.delete(save=False)
                project.attachment = None
                project.save()

            project.milestones.all().delete()

            valid_milestones_count = 0
            for i in range(len(m_titles)):
                if m_titles[i] and m_amounts[i] and m_deadlines[i]:
                    Milestone.objects.create(
                        project=project,
                        title=m_titles[i],
                        description=m_descriptions[i] if i < len(m_descriptions) else '',
                        amount=m_amounts[i],
                        deadline=m_deadlines[i],
                        order=i + 1
                    )
                    valid_milestones_count += 1
            
            if valid_milestones_count == 0:
                raise ValueError("At least one valid milestone is required.")
        return project

    @staticmethod
    def publish_project(project, wallet):
        """Pay from wallet, create escrow, and publish the project."""
        from core.services import NotificationService
        with transaction.atomic():
            platform_fee = round(project.budget * decimal.Decimal('0.10'), 2)
            total_deduction = project.budget + platform_fee
            
            wallet.balance -= total_deduction
            wallet.save()

            Transaction.objects.create(
                wallet=wallet,
                amount=total_deduction,
                direction='debit',
                transaction_type='payment',
                status='completed',
                description=f"Payment for project: {project.title}",
                reference_id=str(uuid.uuid4()).replace('-', '')[:12].upper(),
                related_project=project
            )

            Escrow.objects.create(
                project=project,
                total_amount=project.budget,
                released_amount=decimal.Decimal('0.00'),
                remaining_amount=project.budget,
                platform_fee=platform_fee,
                status='active'
            )

            project.status = 'open'
            project.published_at = timezone.now()
            project.save()

            NotificationService.create_notification(
                recipient=project.client.user,
                notification_type='project_published',
                title='Project Published',
                message=f"Your project '{project.title}' is now live!",
                link=reverse('client_projectInfo', kwargs={'project_id': project.id})
            )

    @staticmethod
    def accept_application(application, actor_user):
        """Accept a project application."""
        from core.services import NotificationService
        with transaction.atomic():
            project = application.project
            
            # Check if we've already reached max freelancers
            accepted_count = project.applications.filter(status='accepted').count()
            if accepted_count >= project.max_freelancers:
                raise ValueError(f"This project already has the maximum of {project.max_freelancers} freelancers accepted.")

            application.status = 'accepted'
            application.save()
            
            accepted_count += 1 # Update count for notification

            ProjectActivity.objects.create(
                project=project,
                user=actor_user,
                activity_type='proposal_accepted',
                description=(
                    f"Proposal from {application.freelancer.full_name or application.freelancer.user.username} "
                    "was accepted."
                )
            )

            # If project is now full, cancel all remaining pending invitations/applications
            if accepted_count >= project.max_freelancers:
                pending_apps = project.applications.filter(status='pending')
                for pending_app in pending_apps:
                    NotificationService.create_notification(
                        recipient=pending_app.freelancer.user,
                        notification_type='proposal_received',
                        title='Invitation Cancelled',
                        message=f"Unfortunately, the project '{project.title}' is now full. Your invitation has been cancelled.",
                        link=reverse('freelancer_track_project')
                    )
                pending_apps.update(status='rejected')

            # Notify Freelancer
            NotificationService.create_notification(
                recipient=application.freelancer.user,
                notification_type='proposal_received',
                title='Application Accepted',
                message=f"Your application for '{project.title}' was accepted! Waiting for client to start the project.",
                link=reverse('freelancer_track_project')
            )
            # Notify Client
            NotificationService.create_notification(
                recipient=project.client.user,
                notification_type='proposal_received',
                title='Application Accepted',
                message=f"You accepted {application.freelancer.full_name or application.freelancer.user.username} for '{project.title}'. ({accepted_count}/{project.max_freelancers} hired)",
                link=reverse('client_projectInfo', kwargs={'project_id': project.id})
            )

    @staticmethod
    def start_project(project, actor_user):
        """Start project with accepted freelancers, rejecting other proposals."""
        from core.services import NotificationService
        with transaction.atomic():
            accepted_apps = project.applications.filter(status='accepted')
            if not accepted_apps.exists():
                raise ValueError("Cannot start project without accepted freelancers.")
            
            project.status = 'in_progress'
            project.save()

            ProjectApplication.objects.filter(
                project=project, status='pending'
            ).update(status='rejected')

            first_milestone = project.milestones.order_by('order').first()
            if first_milestone:
                first_milestone.status = 'in_progress'
                first_milestone.save()

            ProjectActivity.objects.create(
                project=project,
                user=actor_user,
                activity_type='status_updated',
                description=(
                    f"Project '{project.title}' has been started with {accepted_apps.count()} freelancer(s)."
                )
            )

            for app in accepted_apps:
                NotificationService.create_notification(
                    recipient=app.freelancer.user,
                    notification_type='project_started',
                    title='Project Started',
                    message=f"Project '{project.title}' has officially started! Time to get to work.",
                    link=reverse('freelancer_track_project')
                )
                
            NotificationService.create_notification(
                recipient=project.client.user,
                notification_type='project_started',
                title='Project Started',
                message=f"You have explicitly started project '{project.title}'.",
                link=reverse('client_projectInfo', kwargs={'project_id': project.id})
            )

    @staticmethod
    def reject_application(application, actor_user):
        """Reject a project application."""
        application.status = 'rejected'
        application.save()

        ProjectActivity.objects.create(
            project=application.project,
            user=actor_user,
            activity_type='proposal_rejected',
            description=(
                f"Proposal from {application.freelancer.full_name or application.freelancer.user.username} "
                "was rejected."
            )
        )

    @staticmethod
    def submit_milestone(milestone, files, actor_user):
        """Submit a milestone with optional attachments."""
        from core.models import MilestoneAttachment
        from core.services import NotificationService
        if files:
            milestone.attachments.all().delete()
            for f in files:
                MilestoneAttachment.objects.create(milestone=milestone, file=f)

        milestone.status = 'completed'
        milestone.completed_at = timezone.now()
        milestone.revision_requested = False
        milestone.save()

        ProjectActivity.objects.create(
            project=milestone.project,
            user=actor_user,
            activity_type='milestone_submitted',
            description=f"Milestone '{milestone.title}' was submitted by the freelancer."
        )

        freelancer_name = milestone.assigned_to.full_name or milestone.assigned_to.user.username if milestone.assigned_to else "A freelancer"

        # Notify Client
        NotificationService.create_notification(
            recipient=milestone.project.client.user,
            notification_type='milestone_submitted',
            title='Milestone Submitted',
            message=f"Freelancer {freelancer_name} has submitted milestone '{milestone.title}' for project '{milestone.project.title}'.",
            link=reverse('client_projectInfo', kwargs={'project_id': milestone.project.id})
        )

    @staticmethod
    def request_revision(milestone, reason, actor_user):
        """Request a revision from the freelancer on a submitted milestone."""
        from core.services import NotificationService
        milestone.status = 'in_progress'
        milestone.revision_requested = True
        milestone.revision_count += 1
        milestone.revision_reason = reason
        milestone.save()

        ProjectActivity.objects.create(
            project=milestone.project,
            user=actor_user,
            activity_type='revision_requested',
            description=f"Revision requested for milestone '{milestone.title}'. Reason: {reason}"
        )

        # Notify Freelancer
        if milestone.assigned_to:
            NotificationService.create_notification(
                recipient=milestone.assigned_to.user,
                notification_type='project_started', # Re-using or could add revision_requested
                title='Revision Requested',
                message=f"Revision requested for milestone '{milestone.title}' in '{milestone.project.title}'.",
                link=reverse('freelancer_track_project')
            )

    @staticmethod
    def release_milestone_payment(milestone, actor_user):
        """Release escrow funds to freelancer for an approved milestone."""
        from core.services import NotificationService
        with transaction.atomic():
            project = milestone.project
            
            if not milestone.assigned_to:
                raise ValueError("Milestone is not assigned to any freelancer.")

            freelancer_wallet, _ = Wallet.objects.get_or_create(
                user=milestone.assigned_to.user
            )
            escrow = project.escrow

            escrow.remaining_amount -= milestone.amount
            escrow.released_amount += milestone.amount
            if escrow.remaining_amount <= 0:
                escrow.status = 'released'
            escrow.save()

            freelancer_wallet.balance += milestone.amount
            freelancer_wallet.save()

            Transaction.objects.create(
                wallet=freelancer_wallet,
                amount=milestone.amount,
                direction='credit',
                transaction_type='payout',
                status='completed',
                description=f"Payment for milestone: {milestone.title}",
                reference_id=str(uuid.uuid4()).replace('-', '')[:12].upper(),
                related_project=project,
                related_milestone=milestone
            )

            milestone.status = 'approved'
            milestone.save()

            ProjectActivity.objects.create(
                project=project,
                user=actor_user,
                activity_type='payment_released',
                description=(
                    f"Milestone '{milestone.title}' was approved and "
                    f"payment of RM{milestone.amount} was released."
                )
            )

            # Notify Freelancer
            NotificationService.create_notification(
                recipient=milestone.assigned_to.user,
                notification_type='payment_released',
                title='Payment Received',
                message=f"Payment of RM{milestone.amount} released for milestone '{milestone.title}'.",
                link=reverse('freelancer_wallet')
            )

            next_milestone = project.milestones.filter(
                order__gt=milestone.order
            ).order_by('order').first()

            if next_milestone:
                next_milestone.status = 'in_progress'
                next_milestone.save()
                return next_milestone, False  # (next_milestone, is_project_complete)
            else:
                project.status = 'completed'
                project.save()
                ProjectActivity.objects.create(
                    project=project,
                    user=actor_user,
                    activity_type='status_updated',
                    description="All milestones completed. Project status updated to 'Completed'."
                )
                return None, True  # (next_milestone, is_project_complete)

    @staticmethod
    def cancel_open_project(project, actor_user):
        """Cancel an open project and refund the full escrow back to the client."""
        from core.services import NotificationService
        with transaction.atomic():
            escrow = project.escrow
            client_wallet, _ = Wallet.objects.get_or_create(
                user=project.client.user
            )
            refund_amount = escrow.remaining_amount

            # Refund escrow to client wallet
            client_wallet.balance += refund_amount
            client_wallet.save()

            # Record refund transaction
            Transaction.objects.create(
                wallet=client_wallet,
                amount=refund_amount,
                direction='credit',
                transaction_type='refund',
                status='completed',
                description=f"Refund for cancelled project: {project.title}",
                reference_id=str(uuid.uuid4()).replace('-', '')[:12].upper(),
                related_project=project
            )

            # Update escrow
            escrow.remaining_amount = 0
            escrow.status = 'refunded'
            escrow.save()

            # Cancel project, milestones and pending applications
            project.status = 'cancelled'
            project.milestones.all().update(status='cancelled')
            project.applications.filter(status='pending').update(status='rejected')
            project.save()

            ProjectActivity.objects.create(
                project=project,
                user=actor_user,
                activity_type='status_updated',
                description=f"Project cancelled by client. RM{refund_amount} refunded from escrow."
            )

            NotificationService.create_notification(
                recipient=project.client.user,
                notification_type='project_cancelled',
                title='Project Cancelled',
                message=f"Your project '{project.title}' has been cancelled. RM{refund_amount:.2f} has been refunded to your wallet.",
                link=reverse('client_projectInfo', kwargs={'project_id': project.id})
            )

    @staticmethod
    def cancel_expired_open_projects():
        """Auto-cancel open projects whose deadline has passed, refunding escrow to client.
        
        Returns the number of projects cancelled.
        """
        from core.services import NotificationService
        from django.utils import timezone

        today = timezone.now().date()
        expired_projects = Project.objects.filter(status='open', deadline__lt=today)
        count = 0

        for project in expired_projects:
            try:
                with transaction.atomic():
                    escrow = project.escrow
                    client_wallet, _ = Wallet.objects.get_or_create(user=project.client.user)
                    refund_amount = escrow.remaining_amount

                    client_wallet.balance += refund_amount
                    client_wallet.save()

                    Transaction.objects.create(
                        wallet=client_wallet,
                        amount=refund_amount,
                        direction='credit',
                        transaction_type='refund',
                        status='completed',
                        description=f"Auto-refund for expired project: {project.title}",
                        reference_id=str(uuid.uuid4()).replace('-', '')[:12].upper(),
                        related_project=project
                    )

                    escrow.remaining_amount = 0
                    escrow.status = 'refunded'
                    escrow.save()

                    project.status = 'cancelled'
                    project.milestones.all().update(status='cancelled')
                    project.applications.filter(status='pending').update(status='rejected')
                    project.save()

                    from core.models import ProjectActivity
                    ProjectActivity.objects.create(
                        project=project,
                        user=None,
                        activity_type='status_updated',
                        description=f"Project auto-cancelled: deadline ({project.deadline}) has passed. RM{refund_amount} refunded from escrow."
                    )

                    NotificationService.create_notification(
                        recipient=project.client.user,
                        notification_type='project_auto_cancelled',
                        title='Project Auto-Cancelled',
                        message=(
                            f"Your project '{project.title}' was automatically cancelled because its deadline "
                            f"({project.deadline.strftime('%d %b %Y')}) has passed. "
                            f"RM{refund_amount:.2f} has been refunded to your wallet."
                        ),
                        link=f"/client/projects/{project.id}/"
                    )
                    count += 1
            except Exception as e:
                # Log but continue processing other projects
                import logging
                logging.getLogger(__name__).error(
                    f"Failed to auto-cancel project {project.id} ('{project.title}'): {e}"
                )

        return count

    @staticmethod
    def notify_expired_in_progress_projects():
        """Send a one-time notification to both client and freelancer when an
        in-progress project's deadline has passed. Does NOT cancel the project.
        
        Returns the number of projects notified.
        """
        from core.services import NotificationService
        from django.utils import timezone

        today = timezone.now().date()
        expired_projects = Project.objects.filter(
            status='in_progress',
            deadline__lt=today,
            deadline_notified=False
        )
        count = 0

        for project in expired_projects:
            try:
                with transaction.atomic():
                    deadline_str = project.deadline.strftime('%d %b %Y')

                    # Notify client
                    NotificationService.create_notification(
                        recipient=project.client.user,
                        notification_type='project_deadline_expired',
                        title='Project Deadline Passed',
                        message=(
                            f"The deadline ({deadline_str}) for your in-progress project '{project.title}' has passed. "
                            f"Please communicate with your freelancer to agree on next steps, or use the cancellation flow if needed."
                        ),
                        link=f"/client/projects/{project.id}/"
                    )

                    # Notify freelancer
                    if project.assigned_freelancer:
                        NotificationService.create_notification(
                            recipient=project.assigned_freelancer.user,
                            notification_type='project_deadline_expired',
                            title='Project Deadline Passed',
                            message=(
                                f"The deadline ({deadline_str}) for project '{project.title}' has passed. "
                                f"Please communicate with your client to agree on next steps."
                            ),
                            link='/freelancer/track-project/'
                        )

                    project.deadline_notified = True
                    project.save(update_fields=['deadline_notified'])
                    count += 1
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(
                    f"Failed to send deadline notification for project {project.id} ('{project.title}'): {e}"
                )

        return count

    @staticmethod
    def request_project_cancellation(project, actor_user, reason):
        """Creates a pending CancellationRequest for each active freelancer."""
        from core.services import NotificationService
        
        active_freelancers = project.applications.filter(status='accepted')
        
        with transaction.atomic():
            for app in active_freelancers:
                CancellationRequest.objects.update_or_create(
                    project=project,
                    freelancer=app.freelancer,
                    defaults={
                        'requested_by': actor_user,
                        'reason': reason,
                        'status': 'pending'
                    }
                )
                
                NotificationService.create_notification(
                    recipient=app.freelancer.user,
                    notification_type='cancellation_request',
                    title='Project Cancellation Request',
                    message=f"Client has requested to cancel the project '{project.title}'. Please review and respond.",
                    link=reverse('freelancer_track_project')
                )
                
            ProjectActivity.objects.create(
                project=project,
                user=actor_user,
                activity_type='cancellation_requested',
                description=f"Client requested project cancellation. Waiting for responses from {active_freelancers.count()} freelancer(s)."
            )

    @staticmethod
    def confirm_cancellation(cancellation_request, actor_user):
        """A freelancer agrees to cancellation. If all agree, cancel project."""
        from core.services import NotificationService
        project = cancellation_request.project
        current_freelancer = cancellation_request.freelancer
        
        with transaction.atomic():
            cancellation_request.status = 'agreed'
            cancellation_request.save()
            
            # Check if any pending requests remain for this project
            remaining_pending = project.cancellation_requests.filter(status='pending').exists()
            
            if not remaining_pending:
                # Everyone has agreed! Cancel the project.
                escrow = getattr(project, 'escrow', None)
                refund_amount = decimal.Decimal('0.00')
                if escrow and escrow.remaining_amount > 0:
                    client_wallet, _ = Wallet.objects.get_or_create(user=project.client.user)
                    refund_amount = escrow.remaining_amount
                    
                    client_wallet.balance += refund_amount
                    client_wallet.save()
                    
                    Transaction.objects.create(
                        wallet=client_wallet,
                        amount=refund_amount,
                        direction='credit',
                        transaction_type='refund',
                        status='completed',
                        description=f"Refund for cancelled project: {project.title}",
                        reference_id=str(uuid.uuid4()).replace('-', '')[:12].upper(),
                        related_project=project
                    )
                    
                    escrow.remaining_amount = 0
                    escrow.status = 'refunded'
                    escrow.save()
                    
                project.milestones.filter(status__in=['pending', 'in_progress', 'completed']).update(status='cancelled')
                project.status = 'cancelled'
                project.save()
                
                ProjectActivity.objects.create(
                    project=project,
                    user=actor_user,
                    activity_type='status_updated',
                    description=f"All active freelancers agreed. Project cancelled. RM{refund_amount} refunded."
                )
                
                # Notify client
                NotificationService.create_notification(
                    recipient=project.client.user,
                    notification_type='project_cancelled',
                    title='Project Cancelled',
                    message=f"All freelancers agreed to cancel '{project.title}'. RM{refund_amount:.2f} refunded to your wallet.",
                    link=reverse('client_projectInfo', kwargs={'project_id': project.id})
                )
                
                # Notify all involved freelancers
                all_requests = project.cancellation_requests.all()
                for req in all_requests:
                    if req.freelancer != current_freelancer:
                        NotificationService.create_notification(
                            recipient=req.freelancer.user,
                            notification_type='project_cancelled',
                            title='Project Cancelled',
                            message=f"All parties agreed. Project '{project.title}' is now cancelled.",
                            link=reverse('freelancer_track_project')
                        )
            else:
                # Not everyone has agreed yet
                ProjectActivity.objects.create(
                    project=project,
                    user=actor_user,
                    activity_type='cancellation_progress',
                    description=f"Freelancer {current_freelancer.user.username} agreed to cancellation."
                )
                
                NotificationService.create_notification(
                    recipient=project.client.user,
                    notification_type='cancellation_agreed',
                    title='Cancellation Agreement',
                    message=f"Freelancer {current_freelancer.user.username} agreed to cancel '{project.title}'. Waiting for others.",
                    link=reverse('client_projectInfo', kwargs={'project_id': project.id})
                )

    @staticmethod
    def decline_cancellation(cancellation_request, actor_user):
        """A freelancer declines cancellation. This calls off the cancellation for everyone."""
        from core.services import NotificationService
        project = cancellation_request.project
        declining_freelancer = cancellation_request.freelancer
        
        with transaction.atomic():
            # Mark this request as declined
            cancellation_request.status = 'declined'
            cancellation_request.save()
            
            # Dismiss all other pending requests so others don't keep seeing the banner
            project.cancellation_requests.filter(status='pending').update(status='declined')
            
            ProjectActivity.objects.create(
                project=project,
                user=actor_user,
                activity_type='cancellation_declined',
                description=f"Freelancer {declining_freelancer.user.username} declined cancellation. Project continues."
            )
            
            # Notify Client
            NotificationService.create_notification(
                recipient=project.client.user,
                notification_type='cancellation_request',
                title='Cancellation Declined',
                message=f"Freelancer {declining_freelancer.user.username} declined your cancellation request for '{project.title}'. The project continues.",
                link=reverse('client_projectInfo', kwargs={'project_id': project.id})
            )


    @staticmethod
    def admin_cancel_project(project, actor_user):
        """Admin forces cancellation of a project and refunds remaining escrow to the client."""
        from core.services import NotificationService
        with transaction.atomic():
            escrow = getattr(project, 'escrow', None)
            refund_amount = decimal.Decimal('0.00')
            
            if escrow and escrow.remaining_amount > 0:
                client_wallet, _ = Wallet.objects.get_or_create(user=project.client.user)
                refund_amount = escrow.remaining_amount

                # Refund remaining escrow to client
                client_wallet.balance += refund_amount
                client_wallet.save()

                Transaction.objects.create(
                    wallet=client_wallet,
                    amount=refund_amount,
                    direction='credit',
                    transaction_type='refund',
                    status='completed',
                    description=f"Admin refund for cancelled project: {project.title}",
                    reference_id=str(uuid.uuid4()).replace('-', '')[:12].upper(),
                    related_project=project
                )

                escrow.remaining_amount = 0
                escrow.status = 'refunded'
                escrow.save()

            # Cancel all pending/in-progress milestones and pending applications
            project.milestones.filter(status__in=['pending', 'in_progress']).update(status='cancelled')
            project.applications.filter(status='pending').update(status='rejected')

            old_status = project.status
            project.status = 'cancelled'
            project.save()

            ProjectActivity.objects.create(
                project=project,
                user=actor_user,
                activity_type='status_updated',
                description=f"Project cancelled by Administrator. Status changed from '{old_status}' to 'cancelled'. RM{refund_amount} refunded to client."
            )

            NotificationService.create_notification(
                recipient=project.client.user,
                notification_type='project_cancelled',
                title='Project Cancelled by Admin',
                message=f"Your project '{project.title}' has been cancelled by an administrator. RM{refund_amount:.2f} has been refunded to your wallet.",
                link=reverse('client_projectInfo', kwargs={'project_id': project.id})
            )
            
            target_apps = project.applications.filter(status='accepted')
            for app in target_apps:
                NotificationService.create_notification(
                    recipient=app.freelancer.user,
                    notification_type='project_cancelled',
                    title='Project Cancelled by Admin',
                    message=f"Project '{project.title}' has been cancelled by an administrator.",
                    link=reverse('freelancer_track_project')
                )
