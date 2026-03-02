import decimal
from django.db import transaction
from core.models import Review, RatingSummary


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

            summary, _ = RatingSummary.objects.get_or_create(user=reviewee)

            rating = review.rating
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
