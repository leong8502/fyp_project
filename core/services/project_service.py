import uuid
import decimal
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from core.models import (
    Project, Milestone, ProjectApplication,
    ProjectActivity, Escrow, Transaction, Wallet
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
            wallet.balance -= project.budget
            wallet.save()

            Transaction.objects.create(
                wallet=wallet,
                amount=project.budget,
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
        """Accept a project application, start first milestone, reject others."""
        from core.services import NotificationService
        with transaction.atomic():
            application.status = 'accepted'
            application.save()

            project = application.project
            project.assigned_freelancer = application.freelancer
            project.status = 'in_progress'
            project.save()

            ProjectApplication.objects.filter(
                project=project, status='pending'
            ).exclude(id=application.id).update(status='rejected')

            first_milestone = project.milestones.order_by('order').first()
            if first_milestone:
                first_milestone.status = 'in_progress'
                first_milestone.save()

            ProjectActivity.objects.create(
                project=project,
                user=actor_user,
                activity_type='proposal_accepted',
                description=(
                    f"Proposal from {application.freelancer.full_name or application.freelancer.user.username} "
                    "was accepted. Project is now 'In Progress'."
                )
            )

            # Notify Freelancer
            NotificationService.create_notification(
                recipient=application.freelancer.user,
                notification_type='project_started',
                title='Project Started',
                message=f"Your application for '{project.title}' was accepted! Time to get to work.",
                link=reverse('freelancer_track_project')
            )
            # Notify Client
            NotificationService.create_notification(
                recipient=project.client.user,
                notification_type='project_started',
                title='Project Started',
                message=f"Project '{project.title}' has officially started with {application.freelancer.full_name or application.freelancer.user.username}.",
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

        # Notify Client
        NotificationService.create_notification(
            recipient=milestone.project.client.user,
            notification_type='milestone_submitted',
            title='Milestone Submitted',
            message=f"Freelancer {milestone.project.assigned_freelancer.full_name or milestone.project.assigned_freelancer.user.username} has submitted milestone '{milestone.title}' for project '{milestone.project.title}'.",
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
        NotificationService.create_notification(
            recipient=milestone.project.assigned_freelancer.user,
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
            freelancer_wallet, _ = Wallet.objects.get_or_create(
                user=project.assigned_freelancer.user
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
                recipient=project.assigned_freelancer.user,
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

            # Cancel project
            project.status = 'cancelled'
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
    def confirm_cancellation(cancellation_request, actor_user):
        """Freelancer agrees to cancellation. Cancel project and refund remaining escrow."""
        from core.services import NotificationService
        project = cancellation_request.project
        with transaction.atomic():
            escrow = project.escrow
            client_wallet, _ = Wallet.objects.get_or_create(
                user=project.client.user
            )
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
                description=f"Partial refund for cancelled in-progress project: {project.title}",
                reference_id=str(uuid.uuid4()).replace('-', '')[:12].upper(),
                related_project=project
            )

            escrow.remaining_amount = 0
            escrow.status = 'refunded'
            escrow.save()

            # Cancel all pending/in-progress milestones
            project.milestones.filter(status__in=['pending', 'in_progress']).update(status='cancelled')

            project.status = 'cancelled'
            project.save()

            cancellation_request.status = 'agreed'
            cancellation_request.save()

            ProjectActivity.objects.create(
                project=project,
                user=actor_user,
                activity_type='status_updated',
                description=f"Freelancer agreed to cancellation. Project cancelled. RM{refund_amount} refunded."
            )

            NotificationService.create_notification(
                recipient=project.client.user,
                notification_type='project_cancelled',
                title='Project Cancelled',
                message=f"Freelancer agreed to cancel '{project.title}'. RM{refund_amount:.2f} refunded to your wallet.",
                link=reverse('client_projectInfo', kwargs={'project_id': project.id})
            )
