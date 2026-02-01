import json
import logging
from django.utils import timezone
from datetime import timedelta
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    HAS_AI_LIBS = True
except ImportError:
    HAS_AI_LIBS = False

from .models import Project, Freelancer, ProjectMatch

logger = logging.getLogger(__name__)

class MatchEngine:
    def __init__(self):
        if HAS_AI_LIBS:
            try:
                # Load a lightweight model
                self.model = SentenceTransformer('all-MiniLM-L6-v2')
            except Exception as e:
                logger.error(f"Failed to load sentence-transformers model: {e}")
                self.model = None
        else:
            self.model = None
            logger.warning("sentence-transformers not installed. AI matching will be disabled/mocked.")

    def generate_embedding(self, text):
        if not self.model or not text:
            return []
        
        # Normalize text
        text = text.lower().strip()
        
        # Generate embedding
        embedding = self.model.encode(text)
        return embedding.tolist()

    def extract_keywords(self, text):
        # Basic keyword extraction (placeholder for more advanced NLP)
        if not text:
            return []
        
        # Simple stopword removal and splitting
        stopwords = set(['the', 'and', 'is', 'in', 'to', 'for', 'with', 'a', 'of'])
        words = text.lower().replace('.', '').replace(',', '').split()
        keywords = [w for w in words if w not in stopwords and len(w) > 2]
        
        # Get unique top keywords (naive frequency)
        from collections import Counter
        counts = Counter(keywords)
        return [word for word, count in counts.most_common(10)]

    def compute_matches(self, project_id):
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return

        if True: # ALWAYS refresh embedding to capture edits!
            # Generate embedding if missing
            text_corpus = f"{project.title} {project.description} {project.required_skills}"
            project.project_embedding = self.generate_embedding(text_corpus)
            project.save(update_fields=['project_embedding'])

        # Fetch all candidates
        # TODO: Optimize with vector DB or pre-filtering in DB
        # candidates = Freelancer.objects.filter(availability_status__in=['full_time', 'part_time', 'contract'])
        candidates = Freelancer.objects.all()
        
        matches = []
        
        for freelancer in candidates:
            score_data = self.calculate_hybrid_score(project, freelancer)
            if score_data['final_score'] > 0.1: # Threshold to save
                matches.append(ProjectMatch(
                    project=project,
                    freelancer=freelancer,
                    similarity_score=score_data['similarity_score'],
                    final_score=score_data['final_score'],
                    score_breakdown=score_data['breakdown']
                ))
        
        # Sort by final score descending
        matches.sort(key=lambda x: x.final_score, reverse=True)
        
        # Keep top 5
        matches = matches[:5]

        # Bulk create/update
        # Clear old matches for this project to refresh
        ProjectMatch.objects.filter(project=project).delete()
        ProjectMatch.objects.bulk_create(matches)
        
        return len(matches)

    def calculate_hybrid_score(self, project, freelancer):
        reasons = []

        # 1. Semantic Similarity (55%)
        sim_score = 0.0
        if project.project_embedding and freelancer.freelancer_embedding:
            # Convert to numpy arrays
            p_vec = np.array(project.project_embedding).reshape(1, -1)
            f_vec = np.array(freelancer.freelancer_embedding).reshape(1, -1)
            if HAS_AI_LIBS:
                sim_score = float(cosine_similarity(p_vec, f_vec)[0][0])
            else:
                sim_score = 0.0 # Mock or fallback
        
        if sim_score > 0.45:
            reasons.append(f"Strong match with project requirements ({int(sim_score*100)}% match)")

        # 2. Experience Match (20%)
        exp_score = 0.0
        # Simple heuristic: if freelancer years >= project years -> full score
        # Using project.level to map to years if needed, or simple string match
        # Mapping level to approx years: Entry=0, Intermediate=2, Expert=5
        req_years = 0
        if project.experience_level == 'intermediate':
            req_years = 2
        elif project.experience_level == 'expert':
            req_years = 5
            
        if freelancer.experience_years >= req_years:
            exp_score = 1.0
            reasons.append(f"Exceeds experience requirement ({freelancer.experience_years} years)")
        else:
            exp_score = 0.5 # Partial credit
            
        # 3. Reputation (15%)
        rep_score = 0.0
        # Normalize rating 0-5 to 0-1
        if freelancer.average_rating:
            rep_score = float(freelancer.average_rating) / 5.0
            if freelancer.average_rating >= 4.5:
                 reasons.append(f"Top-rated freelancer ({freelancer.average_rating} ⭐)")
            
        # 4. Availability & Freshness (10%)
        avail_score = 0.0
        if freelancer.availability_status == 'full_time':
            avail_score = 1.0
            reasons.append("Available for Full-time work")
        elif freelancer.availability_status == 'part_time':
            avail_score = 0.7
            reasons.append("Available Part-time")
        elif freelancer.availability_status == 'contract':
            avail_score = 0.9
            reasons.append("Open for Contract work")
        else:
            avail_score = 0.3
            
        # Freshness: Boost if active within last 30 days
        # We need a last_active field on Freelancer, assuming it exists
        # if freelancer.last_active > timezone.now() - timedelta(days=30):
        #     avail_score += 0.1
        # (capping at 1.0)
        avail_score = min(avail_score, 1.0)
        
        # Weighted Sum
        final_score = (
            (sim_score * 0.55) +
            (exp_score * 0.20) +
            (rep_score * 0.15) +
            (avail_score * 0.10)
        )
        
        return {
            'similarity_score': sim_score,
            'final_score': final_score,
            'breakdown': {
                'semantic': sim_score,
                'experience': exp_score,
                'reputation': rep_score,
                'availability': avail_score,
                'reasons': reasons
            }
        }
