from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Project, Freelancer, Milestone, FreelancerWorkExperience, FreelancerLanguage, Review, FreelancerAIProfile, ProjectAIProfile
from .ai_matching import MatchEngine
from django.utils import timezone
import logging
import inspect

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Project)
def trigger_project_matching(sender, instance, created, **kwargs):
    # Only run matching if project is published/open
    if instance.status == 'open':
        logger.info(f"Triggering matching for Project {instance.id}")
        engine = MatchEngine()
        engine.compute_matches(instance.id)

@receiver(post_save, sender=Milestone)
@receiver(post_delete, sender=Milestone)
def trigger_project_matching_milestone(sender, instance, **kwargs):
    # Avoid matching during cascade deletes
    # Check if 'delete' is in the call stack
    for frame in inspect.stack():
        if 'delete' in frame.function:
            return

    # When milestone changes, update project embedding and re-match
    try:
        project = instance.project
    except Project.DoesNotExist:
        return # Project already gone
        
    if project.status == 'open':
        logger.info(f"Triggering matching for Project {project.id} (Milestone change)")
        engine = MatchEngine()
        try:
            # compute_matches refetches project and regenerates embedding via generate_project_corpus
            engine.compute_matches(project.id)
        except Exception as e:
            logger.warning(f"Error matching Project {project.id} (Milestone change): {e}")

@receiver(post_save, sender=Freelancer)
def update_freelancer_embedding(sender, instance, created, **kwargs):
    # Avoid recursion - AI profile updates are handled separately
    # This signal now generates the AI profile
    logger.info(f"Skipping AI profile generation for Freelancer {instance.id} during registration")
    # engine = MatchEngine()
    
    # Generate AI profile (includes embedding, keywords, metrics)
    # engine.generate_freelancer_ai_profile(instance)

@receiver(post_save, sender=FreelancerWorkExperience)
@receiver(post_delete, sender=FreelancerWorkExperience)
@receiver(post_save, sender=FreelancerLanguage)
@receiver(post_delete, sender=FreelancerLanguage)
def trigger_freelancer_update_related(sender, instance, **kwargs):
    # When exp or lang changes, update freelancer embedding
    freelancer = instance.freelancer
    # Call the main handler
    update_freelancer_embedding(sender=Freelancer, instance=freelancer, created=False)


@receiver(post_save, sender=Review)
def trigger_freelancer_update_review(sender, instance, created, **kwargs):
    # If the reviewee is a freelancer, update their embedding (to include review text)
    # Check if reviewee has freelancer profile
    if hasattr(instance.reviewee, 'freelancer'):
        update_freelancer_embedding(sender=Freelancer, instance=instance.reviewee.freelancer, created=False)
