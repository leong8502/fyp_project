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
        if sim_score > 0.8:
            reasons.append("<strong>Context Match:</strong> Profile description strongly aligns with your project goals.")

        # 2. Skill Overlap (20%)
        # Explicit check of required skills vs freelancer skills
        skill_score = 0.0
        if project.required_skills and freelancer.skills:
            req_skills = set(s.strip().lower() for s in project.required_skills.split(',') if s.strip())
            free_skills = set(s.strip().lower() for s in freelancer.skills.split(',') if s.strip())
            
            if req_skills:
                overlap = req_skills.intersection(free_skills)
                skill_score = len(overlap) / len(req_skills)
                
                if overlap:
                    # Format standard capitalized skills for display
                    # We can try to find original casing from freelancer.skills if possible, or just capitalize
                    display_skills = [s.title() for s in overlap]
                    skill_str = ", ".join(display_skills[:3]) # Limit to 3
                    reasons.append(f"<strong>Skills Match:</strong> Freelancer has strong experience in {skill_str}, which are key requirements of your project.")

        # 3. Experience Match (10%)
        exp_score = 0.0
        req_years = 0
        if project.experience_level == 'intermediate':
            req_years = 2
        elif project.experience_level == 'expert':
            req_years = 5
            
        if freelancer.experience_years >= req_years:
            exp_score = 1.0
            # Only show reason if they meet the requirement effectively to avoid "0 years" weirdness for entry level
            if freelancer.experience_years > 0:
                 reasons.append(f"<strong>Relevant Experience:</strong> {freelancer.experience_years} years of professional experience.")
        else:
            exp_score = 0.5 # Partial credit
            # Do NOT show reason if under-qualified or 0 years
            
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
                 reasons.append(f"<strong>Proven Track Record:</strong> Consistently high ratings ({avg_rating} ⭐) highlight reliability and quality delivery.")

        # 5. Language Match (5%)
        lang_score = 0.0
        lang_match_text = ""
        if project.preferred_language:
            pref_lang = project.preferred_language.lower().strip()
            # Check freelancer languages
            if freelancer.languages.filter(language__icontains=pref_lang).exists():
                lang_score = 1.0
                lang_match_text = f", and is proficient in {project.preferred_language}"

        # 6. Availability (5%)
        avail_score = 0.0
        if freelancer.availability_status == 'full_time':
            avail_score = 1.0
            reasons.append(f"<strong>Availability:</strong> Freelancer matches for full-time work{lang_match_text}, ensuring your project timeline is met.")
        elif freelancer.availability_status == 'part_time':
            avail_score = 0.7
            if lang_match_text:
                reasons.append(f"<strong>Language Match:</strong> Freelancer is proficient in {project.preferred_language}.")
        elif freelancer.availability_status == 'contract':
            avail_score = 0.9
            reasons.append(f"<strong>Availability:</strong> Freelancer available for contract work{lang_match_text}.")
        else:
            avail_score = 0.3
            if lang_match_text:
                reasons.append(f"<strong>Language Match:</strong> Freelancer is proficient in {project.preferred_language}.")
            
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
