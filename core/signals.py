from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Project, Freelancer
from .ai_matching import MatchEngine
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Project)
def trigger_project_matching(sender, instance, created, **kwargs):
    # Only run matching if project is published/open
    if instance.status == 'open':
        # Check if we need to run matching
        # If created or just turned to open, or if critical fields changed
        # For simplicity, we run if it's open. 
        # In production, check for field changes to avoid re-running on trivial edits.
        
        # We need to make sure we don't recurse infinitely if we save the project inside matching
        # MatchEngine updates 'project_embedding' -> save() -> signal -> loop
        # But MatchEngine uses update_fields=['project_embedding'] which might still trigger signals 
        # depending on how it's called.
        # Alternatively, MatchEngine.compute_matches handles the saving safely?
        # Let's ensure MatchEngine only saves specific fields and we can check here.
        
        # Basic debounce: if update_fields contains 'project_embedding', skip
        if kwargs.get('update_fields') and 'project_embedding' in kwargs['update_fields']:
            return

        logger.info(f"Triggering matching for Project {instance.id}")
        engine = MatchEngine()
        engine.compute_matches(instance.id)

@receiver(post_save, sender=Freelancer)
def update_freelancer_embedding(sender, instance, created, **kwargs):
    # Avoid recursion
    if kwargs.get('update_fields') and 'freelancer_embedding' in kwargs['update_fields']:
        return

    # Check if text fields updated
    # Ideally compare with old instance, but post_save doesn't have old instance easily
    # We'll just run it. It's not too expensive for one user save.
    
    logger.info(f"Updating embedding for Freelancer {instance.id}")
    engine = MatchEngine()
    
    text_corpus = f"{instance.tagline} {instance.bio} {instance.skills}"
    embedding = engine.generate_embedding(text_corpus)
    keywords = engine.extract_keywords(text_corpus)
    
    # Update without triggering signal loop
    Freelancer.objects.filter(id=instance.id).update(
        freelancer_embedding=embedding,
        extracted_keywords=keywords,
        last_active=timezone.now()
    )
