import os
import logging
from django.core.management.base import BaseCommand
from core.models import Project, Freelancer
from core.ai_matching import MatchEngine

class Command(BaseCommand):
    help = 'Rebuilds AI embeddings for all Freelancers and open Projects'

    def handle(self, *args, **options):
        self.stdout.write("Initializing Match Engine...")
        engine = MatchEngine()
        
        # 1. Update Freelancers
        freelancers = Freelancer.objects.all()
        count_f = 0
        self.stdout.write(f"Found {freelancers.count()} freelancers. Updating...")
        
        for f in freelancers:
            try:
                text_corpus = f"{f.tagline} {f.bio} {f.skills}"
                # Generate embedding
                f.freelancer_embedding = engine.generate_embedding(text_corpus)
                f.extracted_keywords = engine.extract_keywords(text_corpus)
                # Save only specific fields to avoid overhead (and potential recursion if signals weren't handled)
                f.save(update_fields=['freelancer_embedding', 'extracted_keywords'])
                count_f += 1
                if count_f % 10 == 0:
                    self.stdout.write(f"Processed {count_f} freelancers...")
            except Exception as e:
                self.stderr.write(f"Error processing freelancer {f.id}: {e}")

        self.stdout.write(self.style.SUCCESS(f"Successfully updated {count_f} freelancers."))

        # 2. Update Projects
        projects = Project.objects.filter(status='open')
        count_p = 0
        self.stdout.write(f"Found {projects.count()} open projects. Updating...")
        
        for p in projects:
            try:
                text_corpus = f"{p.title} {p.description} {p.required_skills}"
                p.project_embedding = engine.generate_embedding(text_corpus)
                p.save(update_fields=['project_embedding'])
                count_p += 1
            except Exception as e:
                self.stderr.write(f"Error processing project {p.id}: {e}")

        self.stdout.write(self.style.SUCCESS(f"Successfully updated {count_p} projects."))
