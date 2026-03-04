"""
Management command: python manage.py check_project_deadlines

Run this daily (via cron / task scheduler) to enforce project deadlines:
  - Open projects past deadline  → auto-cancel + refund escrow to client
  - In-progress projects past deadline → one-time notification to both parties
"""

from django.core.management.base import BaseCommand
from core.services.project_service import ProjectService


class Command(BaseCommand):
    help = (
        "Enforce project deadlines: auto-cancel expired open projects "
        "and notify in-progress projects whose deadline has passed."
    )

    def handle(self, *args, **options):
        self.stdout.write("Checking project deadlines...")

        # 1. Auto-cancel open projects that missed their deadline
        cancelled_count = ProjectService.cancel_expired_open_projects()
        self.stdout.write(
            self.style.SUCCESS(
                f"  [OPEN] Cancelled {cancelled_count} project(s) past their deadline."
            )
        )

        # 2. Notify in-progress projects that have passed their deadline
        notified_count = ProjectService.notify_expired_in_progress_projects()
        self.stdout.write(
            self.style.WARNING(
                f"  [IN PROGRESS] Sent deadline-expired notifications for {notified_count} project(s)."
            )
        )

        self.stdout.write(self.style.SUCCESS("Done."))
