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

from .models import Project, Freelancer, ProjectMatch, FreelancerAIProfile, ProjectAIProfile

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
        
        # Add Work Experience (External)
        for exp in freelancer.work_experiences.all():
            corpus.append(f"{exp.job_title} at {exp.company}")
            corpus.append(exp.description)
            
        # Add Platform Experience (Completed Projects)
        for project in Project.objects.filter(applications__freelancer=freelancer, applications__status='accepted', status='completed').distinct():
            corpus.append(f"Completed Project on Platform: {project.title}")
            corpus.append(project.description)
            
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

    def calculate_reliability_score(self, freelancer):
        """
        Calculate reliability score based on multiple factors.
        Returns a score between 0.0 and 1.0.
        """
        score = 0.5  # Base score
        
        # Factor 1: Average rating (40%)
        try:
            if hasattr(freelancer.user, 'rating_summary'):
                avg_rating = float(freelancer.user.rating_summary.average_rating)
                score += (avg_rating / 5.0) * 0.4
        except Exception:
            pass
        
        # Factor 2: Completion rate (30%)
        assigned_projects = Project.objects.filter(applications__freelancer=freelancer, applications__status='accepted').distinct()
        total_projects = assigned_projects.count()
        if total_projects > 0:
            completed = assigned_projects.filter(status='completed').count()
            completion_rate = completed / total_projects
            score += completion_rate * 0.3
        
        # Factor 3: Activity (15%)
        days_since_active = (timezone.now() - freelancer.last_active).days
        if days_since_active < 7:
            score += 0.15
        elif days_since_active < 30:
            score += 0.10
        elif days_since_active < 90:
            score += 0.05
        
        # Factor 4: Profile completeness (15%)
        completeness = 0
        if freelancer.bio: completeness += 0.25
        if freelancer.skills: completeness += 0.25
        if freelancer.work_experiences.exists(): completeness += 0.25
        if freelancer.portfolios.exists(): completeness += 0.25
        score += completeness * 0.15
        
        return min(1.0, max(0.0, score))

    def assess_project_complexity(self, project):
        """
        Assess project complexity based on various factors.
        Returns 'simple', 'moderate', or 'complex'.
        """
        complexity_score = 0
        
        # Factor 1: Budget
        budget = float(project.budget)
        if budget > 10000:
            complexity_score += 3
        elif budget > 5000:
            complexity_score += 2
        else:
            complexity_score += 1
        
        # Factor 2: Number of milestones
        milestone_count = project.milestones.count()
        if milestone_count > 5:
            complexity_score += 3
        elif milestone_count > 2:
            complexity_score += 2
        else:
            complexity_score += 1
        
        # Factor 3: Required skills count
        if project.required_skills:
            skill_count = len([s for s in project.required_skills.split(',') if s.strip()])
            if skill_count > 5:
                complexity_score += 3
            elif skill_count > 3:
                complexity_score += 2
            else:
                complexity_score += 1
        
        # Factor 4: Experience level
        if project.experience_level == 'expert':
            complexity_score += 3
        elif project.experience_level == 'intermediate':
            complexity_score += 2
        else:
            complexity_score += 1
        
        # Determine complexity
        if complexity_score >= 10:
            return 'complex'
        elif complexity_score >= 6:
            return 'moderate'
        else:
            return 'simple'

    def generate_freelancer_ai_profile(self, freelancer):
        """
        Generate or update AI profile for a freelancer.
        """
        # Generate corpus and embedding
        text_corpus = self.generate_freelancer_corpus(freelancer)
        embedding = self.generate_embedding(text_corpus)
        keywords = self.extract_keywords(text_corpus)
        
        # Calculate metrics
        reliability = self.calculate_reliability_score(freelancer)
        
        # Extract top skills
        top_skills = []
        if freelancer.skills:
            top_skills = [s.strip() for s in freelancer.skills.split(',') if s.strip()][:5]
        
        # Get average rating
        avg_rating = 0.0
        total_reviews = 0
        try:
            if hasattr(freelancer.user, 'rating_summary'):
                avg_rating = float(freelancer.user.rating_summary.average_rating)
                total_reviews = freelancer.user.rating_summary.total_reviews
        except Exception:
            pass
        
        # Generate professional summary
        summary_parts = []
        if freelancer.tagline:
            summary_parts.append(freelancer.tagline)
        if freelancer.experience_years > 0:
            summary_parts.append(f"{freelancer.experience_years} years of experience")
        if top_skills:
            summary_parts.append(f"Skilled in {', '.join(top_skills[:3])}")
        
        professional_summary = ". ".join(summary_parts) if summary_parts else "Professional freelancer"
        
        # Extract strengths based on data
        strengths = []
        if avg_rating >= 4.5:
            strengths.append("Consistently high client satisfaction")
        if freelancer.experience_years >= 5:
            strengths.append("Extensive industry experience")
        elif freelancer.experience_years >= 2:
            strengths.append("Solid professional experience")
        if reliability >= 0.8:
            strengths.append("Highly reliable and active")
        if len(top_skills) >= 4:
            strengths.append("Diverse skill set")
        if freelancer.portfolios.count() >= 3:
            strengths.append("Strong portfolio of work")
        if freelancer.certifications.filter(is_verified=True).exists():
            strengths.append("Verified professional certifications")
        if total_reviews >= 10:
            strengths.append("Proven track record with multiple clients")
        
        # Extract weaknesses/areas for improvement
        weaknesses = []
        if avg_rating > 0 and avg_rating < 3.5:
            weaknesses.append("Room for improvement in client satisfaction")
        if freelancer.experience_years < 1:
            weaknesses.append("Limited professional experience")
        if reliability < 0.5:
            weaknesses.append("Inconsistent activity or availability")
        if not freelancer.portfolios.exists():
            weaknesses.append("No portfolio items to showcase")
        if total_reviews < 3:
            weaknesses.append("Limited client feedback history")
        if not freelancer.bio:
            weaknesses.append("Incomplete profile information")
        
        # Extract domain expertise from work experience and skills
        domain_expertise = []
        # From work experience
        for exp in freelancer.work_experiences.all()[:5]:
            if exp.job_title:
                # Extract domain from job title (e.g., "Senior Web Developer" -> "Web Development")
                title_lower = exp.job_title.lower()
                if 'web' in title_lower or 'frontend' in title_lower or 'backend' in title_lower:
                    if "Web Development" not in domain_expertise:
                        domain_expertise.append("Web Development")
                elif 'mobile' in title_lower or 'ios' in title_lower or 'android' in title_lower:
                    if "Mobile Development" not in domain_expertise:
                        domain_expertise.append("Mobile Development")
                elif 'data' in title_lower or 'analyst' in title_lower:
                    if "Data Analysis" not in domain_expertise:
                        domain_expertise.append("Data Analysis")
                elif 'design' in title_lower or 'ui' in title_lower or 'ux' in title_lower:
                    if "UI/UX Design" not in domain_expertise:
                        domain_expertise.append("UI/UX Design")
                elif 'market' in title_lower:
                    if "Digital Marketing" not in domain_expertise:
                        domain_expertise.append("Digital Marketing")
        
        # From skills - infer domains
        if freelancer.skills:
            skills_lower = freelancer.skills.lower()
            if any(s in skills_lower for s in ['python', 'django', 'flask', 'java', 'node']):
                if "Backend Development" not in domain_expertise:
                    domain_expertise.append("Backend Development")
            if any(s in skills_lower for s in ['react', 'vue', 'angular', 'javascript', 'html', 'css']):
                if "Frontend Development" not in domain_expertise:
                    domain_expertise.append("Frontend Development")
            if any(s in skills_lower for s in ['photoshop', 'illustrator', 'figma', 'sketch']):
                if "Graphic Design" not in domain_expertise:
                    domain_expertise.append("Graphic Design")
            if any(s in skills_lower for s in ['seo', 'google ads', 'social media', 'content']):
                if "Digital Marketing" not in domain_expertise:
                    domain_expertise.append("Digital Marketing")
        
        # Limit to top 5 domains
        domain_expertise = domain_expertise[:5]
        
        # Create or update AI profile
        ai_profile, created = FreelancerAIProfile.objects.update_or_create(
            freelancer=freelancer,
            defaults={
                'professional_summary': professional_summary,
                'strengths': strengths,
                'weaknesses': weaknesses,
                'top_skills': top_skills,
                'domain_expertise': domain_expertise,
                'avg_rating': avg_rating,
                'reliability_score': reliability,
                'semantic_embedding': embedding,
                'extracted_keywords': keywords,
            }
        )
        
        return ai_profile

    def generate_project_ai_profile(self, project):
        """
        Generate or update AI profile for a project.
        """
        # Generate corpus and embedding
        text_corpus = self.generate_project_corpus(project)
        embedding = self.generate_embedding(text_corpus)
        keywords = self.extract_keywords(text_corpus)
        
        # Assess complexity
        complexity = self.assess_project_complexity(project)
        
        # Extract required expertise
        required_expertise = []
        if project.required_skills:
            required_expertise = [s.strip() for s in project.required_skills.split(',') if s.strip()]
        
        # Estimate duration (based on deadline)
        estimated_duration = None
        if project.deadline:
            delta = project.deadline - timezone.now().date()
            estimated_duration = max(1, delta.days)
        
        # Generate summary
        summary_parts = [project.title]
        if project.category:
            summary_parts.append(f"Category: {project.category.name}")
        if project.experience_level:
            summary_parts.append(f"Experience: {project.get_experience_level_display()}")
        
        summary_text = ". ".join(summary_parts)
        
        # Identify risk factors
        risk_factors = []
        
        # Budget-related risks
        budget = float(project.budget)
        if budget < 500:
            risk_factors.append("Low budget may limit qualified freelancer availability")
        elif budget > 50000:
            risk_factors.append("High-value project requires experienced oversight")
        
        # Timeline risks
        if estimated_duration and estimated_duration < 7:
            risk_factors.append("Tight deadline may require immediate availability")
        elif estimated_duration and estimated_duration > 180:
            risk_factors.append("Long-term project requires sustained commitment")
        
        # Complexity risks
        if complexity == 'complex':
            risk_factors.append("Complex project scope may require multiple iterations")
            if project.experience_level == 'entry':
                risk_factors.append("Complexity mismatch: Complex project with entry-level requirement")
        
        # Skill requirements risks
        skill_count = len(required_expertise)
        if skill_count > 7:
            risk_factors.append("Diverse skill requirements may need multiple specialists")
        elif skill_count == 0:
            risk_factors.append("Unclear skill requirements may cause matching issues")
        
        # Milestone risks
        milestone_count = project.milestones.count()
        if milestone_count == 0:
            risk_factors.append("No milestones defined - unclear project structure")
        elif milestone_count > 10:
            risk_factors.append("Many milestones require detailed project management")
        
        # Experience level risks
        if project.experience_level == 'expert' and budget < 2000:
            risk_factors.append("Expert-level requirement with limited budget")
        
        # Status risks
        if project.status == 'draft':
            risk_factors.append("Project not yet published")
        
        # Limit to top 5 most relevant risks
        risk_factors = risk_factors[:5]
        
        # Create or update AI profile
        ai_profile, created = ProjectAIProfile.objects.update_or_create(
            project=project,
            defaults={
                'summary_text': summary_text,
                'complexity_level': complexity,
                'required_expertise': required_expertise,
                'estimated_duration': estimated_duration,
                'risk_factors': risk_factors,
                'semantic_embedding': embedding,
                'extracted_keywords': keywords,
            }
        )
        
        return ai_profile

    def compute_matches(self, project_id):
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return

        # Generate or update project AI profile
        project_ai_profile = self.generate_project_ai_profile(project)

        if project_ai_profile.semantic_embedding is None:
            return 0

        # Fetch candidates using pgvector CosineDistance
        from pgvector.django import CosineDistance

        # Query FreelancerAIProfile instead of Freelancer
        # We want similarity, which is 1 - CosineDistance
        # Order by distance ascending (closest first)
        ai_profiles = FreelancerAIProfile.objects.exclude(semantic_embedding__isnull=True) \
            .annotate(distance=CosineDistance('semantic_embedding', project_ai_profile.semantic_embedding)) \
            .select_related('freelancer', 'freelancer__user') \
            .order_by('distance')[:50] # Get top 50 semantic matches to re-rank
        
        matches = []
        
        for ai_profile in ai_profiles:
            freelancer = ai_profile.freelancer
            # Re-calculate hybrid score
            score_data = self.calculate_hybrid_score(project, freelancer, distance=getattr(ai_profile, 'distance', None))
            
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
        else:
            # Fallback for manual calc or when distance isn't provided (e.g. testing)
            p_profile = getattr(project, 'ai_profile', None)
            f_profile = getattr(freelancer, 'ai_profile', None)
            
            if p_profile and f_profile and p_profile.semantic_embedding is not None and f_profile.semantic_embedding is not None:
                if HAS_AI_LIBS:
                    p_vec = np.array(p_profile.semantic_embedding).reshape(1, -1)
                    f_vec = np.array(f_profile.semantic_embedding).reshape(1, -1)
                    sim_score = float(cosine_similarity(p_vec, f_vec)[0][0])
        
        # Clamp sim_score
        sim_score = max(0.0, min(sim_score, 1.0))
        
        # Tiered reasons for better transparency
        if sim_score >= 0.8:
            reasons.append("<strong>Context Match:</strong> Profile and background strongly align with the project's strategic goals.")
        elif sim_score >= 0.6:
            reasons.append("<strong>Good Context Match:</strong> Professional experience and profile details align well with the project requirements.")
        elif sim_score >= 0.4:
            reasons.append("<strong>Moderate Context Match:</strong> Some aspects of your professional background relate to the project's scope.")

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
        total_reviews = 0
        try:
             # Try to get from annotates or related
             if hasattr(freelancer, 'user') and hasattr(freelancer.user, 'rating_summary'):
                 avg_rating = float(freelancer.user.rating_summary.average_rating)
                 total_reviews = freelancer.user.rating_summary.total_reviews
        except Exception:
             pass

        if avg_rating:
            rep_score = avg_rating / 5.0
            
            # Multi-condition reasons based on rating and volume
            if avg_rating >= 4.8 and total_reviews >= 10:
                reasons.append(f"<strong>Top-Tier Performer:</strong> Exceptional {avg_rating} ⭐ rating across {total_reviews} projects indicates consistently elite quality.")
            elif avg_rating >= 4.5 and total_reviews >= 5:
                reasons.append(f"<strong>Proven Track Record:</strong> Strong {avg_rating} ⭐ rating with multiple successful deliveries highlights high reliability.")
            elif avg_rating >= 4.5:
                reasons.append(f"<strong>Excellent Start:</strong> Maintains a perfect {avg_rating} ⭐ rating, demonstrating high-quality work in initial projects.")
            elif avg_rating >= 4.0 and total_reviews >= 10:
                reasons.append(f"<strong>Experienced Professional:</strong> Solid 4+ star history across {total_reviews} reviews shows stable and dependable performance.")
            elif avg_rating >= 4.0:
                reasons.append(f"<strong>Positive Feedback:</strong> Good ratings ({avg_rating} ⭐) from recent clients highlight quality output.")

        # 4b. Platform History (Deep Integration)
        # Check for similar completed projects in the same category
        if project.category:
            similar_completed_count = Project.objects.filter(
                applications__freelancer=freelancer,
                applications__status='accepted',
                status='completed', 
                category=project.category
            ).distinct().count()
            
            if similar_completed_count > 0:
                category_name = project.category.name
                reasons.append(f"<strong>Proven Expert:</strong> Successfully completed {similar_completed_count} similar project(s) on our platform in the {category_name} category.")


        # 5. Language Match (5%)
        lang_score = 1.0
        lang_match_text = ""
        if project.preferred_language:
            pref_lang = project.preferred_language.lower().strip()
            # Check freelancer languages
            if freelancer.languages.filter(language__icontains=pref_lang).exists():
                lang_score = 1.0
                lang_match_text = f", and is proficient in {project.preferred_language}"
            else:
                lang_score = 0.0

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
