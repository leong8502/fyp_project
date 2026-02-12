import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

class AISearchManager:
    """
    Handles AI-based matching between freelancers, search queries, and projects.
    Uses TF-IDF for fast, real-time matching of skills and descriptions.
    """
    
    def __init__(self):
        self.vectorizer = TfidfVectorizer(stop_words='english', lowercase=True)

    def _get_project_text(self, project):
        """
        Combines project title, description, required skills, and milestones into a single corpus.
        """
        parts = [
            project.title,
            project.description,
            project.required_skills,
            project.preferred_language or ""
        ]
        
        # Add milestone info
        for milestone in project.milestones.all():
            parts.append(milestone.title)
            if milestone.description:
                parts.append(milestone.description)
        
        return " ".join(filter(None, parts))

    def _get_freelancer_text(self, freelancer):
        """
        Combines freelancer tagline, bio, and skills into a single corpus.
        """
        parts = [
            freelancer.tagline or "",
            freelancer.bio or "",
            freelancer.skills or ""
        ]
        return " ".join(filter(None, parts))

    def calculate_match_scores(self, projects, freelancer=None, query=None):
        """
        Calculates match scores for a list of projects against a freelancer and/or a search query.
        Returns a list of (project, score) tuples.
        """
        if not projects:
            return []

        # Prepare target text (Freelancer skills + Query)
        target_parts = []
        if freelancer:
            target_parts.append(self._get_freelancer_text(freelancer))
        if query:
            target_parts.append(query)
        
        target_text = " ".join(target_parts)
        if not target_text:
            return [(p, 0) for p in projects]

        # Prepare project corpora
        project_texts = [self._get_project_text(p) for p in projects]
        
        try:
            # Combine all for vectorization
            all_texts = project_texts + [target_text]
            tfidf_matrix = self.vectorizer.fit_transform(all_texts)
            
            # Target is the last row
            target_vector = tfidf_matrix[-1]
            project_vectors = tfidf_matrix[:-1]
            
            # Calculate cosine similarity
            similarities = cosine_similarity(target_vector, project_vectors).flatten()
            
            results = []
            for i, project in enumerate(projects):
                # Scale to 0-100 and round
                score = round(similarities[i] * 100, 1)
                results.append((project, score))
            
            return results
        except Exception as e:
            print(f"AI Matching Error: {e}")
            return [(p, 0) for p in projects]

def get_recommendations(freelancer, limit=4):
    """
    Convenience function to get top recommended projects for a freelancer.
    """
    from .models import Project
    
    # Get all open projects
    open_projects = list(Project.objects.filter(status='open'))
    if not open_projects:
        return []
    
    manager = AISearchManager()
    scored_projects = manager.calculate_match_scores(open_projects, freelancer=freelancer)
    
    # Sort by score descending
    scored_projects.sort(key=lambda x: x[1], reverse=True)
    
    return scored_projects[:limit]
