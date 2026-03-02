import uuid
import decimal
from django.db import transaction
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
        return project

    @staticmethod
    def publish_project(project, wallet):
        """Pay from wallet, create escrow, and publish the project."""
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

    @staticmethod
    def accept_application(application, actor_user):
        """Accept a project application, start first milestone, reject others."""
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

    @staticmethod
    def request_revision(milestone, reason, actor_user):
        """Request a revision from the freelancer on a submitted milestone."""
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

    @staticmethod
    def release_milestone_payment(milestone, actor_user):
        """Release escrow funds to freelancer for an approved milestone."""
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
