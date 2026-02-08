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

    def generate_project_corpus(self, project):
        """
        Aggregates Project data: Title, Description, Skills, Milestones
        """
        corpus = [project.title, project.description, project.required_skills, project.preferred_language]
        
        # Add Milestones
        for milestone in project.milestones.all():
            corpus.append(milestone.title)
            if milestone.description:
                corpus.append(milestone.description)
                
        return " ".join(filter(None, corpus))

    def generate_freelancer_corpus(self, freelancer):
        """
        Aggregates Freelancer data: Tagline, Bio, Skills, Experience, Languages, Reviews
        """
        corpus = [freelancer.tagline, freelancer.bio, freelancer.skills]
        
        # Add Work Experience
        for exp in freelancer.work_experiences.all():
            corpus.append(f"{exp.job_title} at {exp.company}")
            corpus.append(exp.description)
            
        # Add Languages
        for lang in freelancer.languages.all():
            corpus.append(f"{lang.language} ({lang.proficiency})")
            
        # Add Recent Reviews (limit to last 5 to avoid noise)
        for review in freelancer.user.received_reviews.order_by('-created_at')[:5]:
            corpus.append(review.comment)
            
        return " ".join(filter(None, corpus))

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
            text_corpus = self.generate_project_corpus(project)
            # Ensure generate_embedding returns a list, not numpy array
            embedding = self.generate_embedding(text_corpus)
            if embedding:
                 project.project_embedding = embedding
                 project.save(update_fields=['project_embedding'])

        if project.project_embedding is None:
            return 0

        # Fetch candidates using pgvector CosineDistance
        from pgvector.django import CosineDistance

        # We want similarity, which is 1 - CosineDistance
        # Order by distance ascending (closest first)
        candidates = Freelancer.objects.exclude(freelancer_embedding__isnull=True) \
            .annotate(distance=CosineDistance('freelancer_embedding', project.project_embedding)) \
            .order_by('distance')[:50] # Get top 50 semantic matches to re-rank
        
        matches = []
        
        for freelancer in candidates:
            # Re-calculate hybrid score
            score_data = self.calculate_hybrid_score(project, freelancer, distance=getattr(freelancer, 'distance', None))
            
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
        ProjectMatch.objects.filter(project=project).delete()
        ProjectMatch.objects.bulk_create(matches)
        
        return len(matches)

    def calculate_hybrid_score(self, project, freelancer, distance=None):
        reasons = []

        # 1. Semantic Similarity (50%)
        sim_score = 0.0
        
        if distance is not None:
            # Derived from pgvector
            sim_score = 1 - distance
        elif project.project_embedding is not None and freelancer.freelancer_embedding is not None:
            # Fallback for manual calc
            if HAS_AI_LIBS:
                p_vec = np.array(project.project_embedding).reshape(1, -1)
                f_vec = np.array(freelancer.freelancer_embedding).reshape(1, -1)
                sim_score = float(cosine_similarity(p_vec, f_vec)[0][0])
        
        # Clamp sim_score
        sim_score = max(0.0, min(sim_score, 1.0))
        if sim_score > 0.6:
            reasons.append(f"Strong semantic match ({int(sim_score*100)}%)")

        # 2. Skill Overlap (20%)
        # Explicit check of required skills vs freelancer skills
        skill_score = 0.0
        if project.required_skills and freelancer.skills:
            req_skills = set(s.strip().lower() for s in project.required_skills.split(',') if s.strip())
            free_skills = set(s.strip().lower() for s in freelancer.skills.split(',') if s.strip())
            
            if req_skills:
                overlap = req_skills.intersection(free_skills)
                skill_score = len(overlap) / len(req_skills)
                if skill_score > 0.5:
                    reasons.append(f"high skill overlap ({len(overlap)}/{len(req_skills)} skills)")
                elif skill_score > 0:
                     reasons.append(f"Matches {len(overlap)} required skills")

        # 3. Experience Match (10%)
        exp_score = 0.0
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
            
        # 4. Reputation (10%)
        rep_score = 0.0
        avg_rating = 0.0
        try:
             # Try to get from annotates or related
             if hasattr(freelancer, 'user') and hasattr(freelancer.user, 'rating_summary'):
                 avg_rating = float(freelancer.user.rating_summary.average_rating)
        except Exception:
             pass

        if avg_rating:
            rep_score = avg_rating / 5.0
            if avg_rating >= 4.5:
                 reasons.append(f"Top-rated freelancer ({avg_rating} ⭐)")

        # 5. Language Match (5%)
        lang_score = 0.0
        if project.preferred_language:
            pref_lang = project.preferred_language.lower().strip()
            # Check freelancer languages
            # Optimization: could preload languages, but for 50 candidates it's okay-ish given we need accuracy
            # A better way is to pass annotated data, but let's query for now or rely on text corpus if strictly semantic.
            # Ideally we check the Relation. For now, let's look at the 'languages' text logic if we had it, 
            # OR check the ManyToMany relation.
            # Since we have freelancer object, let's use the relation if available, else skip.
             
            # Using the related manager
            has_lang = freelancer.languages.filter(language__icontains=pref_lang).exists()
            if has_lang:
                lang_score = 1.0
                reasons.append(f"Speaks {project.preferred_language}")

        # 6. Availability (5%)
        avail_score = 0.0
        if freelancer.availability_status == 'full_time':
            avail_score = 1.0
        elif freelancer.availability_status == 'part_time':
            avail_score = 0.7
        elif freelancer.availability_status == 'contract':
            avail_score = 0.9
        else:
            avail_score = 0.3
            
        avail_score = min(avail_score, 1.0)
        
        # Weighted Sum
        final_score = (
            (sim_score * 0.50) +
            (skill_score * 0.20) +
            (exp_score * 0.10) +
            (rep_score * 0.10) +
            (lang_score * 0.05) +
            (avail_score * 0.05)
        )
        
        return {
            'similarity_score': sim_score,
            'final_score': final_score,
            'breakdown': {
                'semantic': sim_score,
                'skill_overlap': skill_score,
                'experience': exp_score,
                'reputation': rep_score,
                'language': lang_score,
                'availability': avail_score,
                'reasons': reasons
            }
        }
