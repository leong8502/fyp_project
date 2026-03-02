import decimal
from django.db import transaction
from django.urls import reverse
from core.models import Review, RatingSummary
from core.services.notification_service import NotificationService


class ReviewService:

    @staticmethod
    def submit_review(project, reviewer, reviewee, form, tags):
        """Save a review and update the reviewee's rating summary."""
        with transaction.atomic():
            review = form.save(commit=False)
            review.project = project
            review.reviewer = reviewer
            review.reviewee = reviewee
            review.feedback_tags = tags
            review.save()

            rating = review.rating # Moved this line up to be available for notification
            
            NotificationService.create_notification(
                recipient=reviewee,
                notification_type='review_submitted',
                title='New Review Received',
                message=f"You have received a {rating}-star review for project '{project.title}'.",
                link=reverse('client_profile') if hasattr(reviewee, 'client') else reverse('freelancer_profile')
            )

            summary, _ = RatingSummary.objects.get_or_create(user=reviewee)

            if rating == 5:
                summary.five_star_count += 1
            elif rating == 4:
                summary.four_star_count += 1
            elif rating == 3:
                summary.three_star_count += 1
            elif rating == 2:
                summary.two_star_count += 1
            elif rating == 1:
                summary.one_star_count += 1

            current_total_score = decimal.Decimal(str(summary.average_rating)) * summary.total_reviews
            summary.total_reviews += 1
            new_total_score = current_total_score + decimal.Decimal(rating)
            summary.average_rating = new_total_score / summary.total_reviews
            summary.save()

        return review
