import os
import json
import logging
from django.utils import timezone
from core.models import AIApiUsage
from django.conf import settings
import google.generativeai as genai

logger = logging.getLogger(__name__)

class AIGenerationService:
    DAILY_QUOTA_LIMIT = 250

    @classmethod
    def _check_and_increment_quota(cls):
        """
        Checks if we have hit the daily quota. If not, increments it.
        Returns True if allowed, False if quota exceeded.
        """
        today = timezone.now().date()
        usage, created = AIApiUsage.objects.get_or_create(date=today)
        
        if usage.request_count >= cls.DAILY_QUOTA_LIMIT:
            return False
            
        usage.request_count += 1
        usage.save()
        return True
        
    @classmethod
    def get_current_quota_usage(cls):
        """Returns the number of requests made today."""
        today = timezone.now().date()
        usage_record = AIApiUsage.objects.filter(date=today).first()
        return usage_record.request_count if usage_record else 0

    @classmethod
    def generate_project_scope(cls, prompt_text):
        """
        Sends the user's prompt to Gemini to generate a structured project scope.
        Enforces the defined DAILY_QUOTA_LIMIT.
        """
        if not cls._check_and_increment_quota():
            raise Exception(f"Daily AI Generation quota ({cls.DAILY_QUOTA_LIMIT} requests) exceeded. Please try again tomorrow.")
            
        api_key = os.environ.get("GEMINI_API_KEY", getattr(settings, "GEMINI_API_KEY", None))
        if not api_key:
            raise Exception("GEMINI_API_KEY is not configured in the environment.")
            
        genai.configure(api_key=api_key)
        
        # We use flash because it's fast and handles JSON generation well
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        today = timezone.now().date()
        system_instruction = f"""
        You are an expert project scoping assistant for a freelancer marketplace platform.
        Today's date is {today}.
        The user will give you a rough idea of what they want to build or achieve.
        You must structure this idea into a clear, professional project listing.
        
        Return ONLY a JSON object with the following schema, and absolutely no markdown formatting or markdown code blocks (do not wrap in ```json). Just the raw JSON string:
        
        {{
          "title": "A short, professional title for the project",
          "category": "One of: Development, Design, Marketing, Writing, Legal",
          "description": "A detailed, professional description expanding on their prompt",
          "budget": 5000, 
          "experience_level": "entry, intermediate, or expert",
          "year_of_experience": 2, 
          "preferred_languages": ["English", "Mandarin"], // Array of languages mentioned. Empty array if none.
          "deadline": "YYYY-MM-DD", // The final project completion date
          "required_skills": ["Skill 1", "Skill 2"], 
          "milestones": [
            {{
              "title": "Milestone name",
              "description": "Short description",
              "amount": 2000, 
              "deadline": "YYYY-MM-DD" // The specific deadline for this milestone. MUST be <= project deadline.
            }}
          ]
        }}
        
        IMPORTANT RULES:
        1. All dates MUST be in YYYY-MM-DD format.
        2. Today's date is {today}. If the user provides a specific deadline (e.g. "5 May 2026"), you MUST use that exact date for the project "deadline".
        3. Milestone deadlines MUST be sequential and the final milestone deadline MUST match the project "deadline".
        4. Budget: The sum of all milestone amounts MUST equal the total budget.
        5. Experience: Less than 2 years = entry, 2-4 years = intermediate, 5+ years = expert.
        """
        
        try:
            # We can pass the prompt along with the system instruction
            full_prompt = f"{system_instruction}\n\nUSER PROMPT: {prompt_text}"
            
            response = model.generate_content(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json",
                )
            )
            
            response_text = response.text.strip()
            # Failsafe: Remove markdown block if model ignored instructions
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
                
            json_data = json.loads(response_text)
            return json_data
            
        except Exception as e:
            logger.error(f"Gemini API Error: {str(e)}")
            raise Exception("Failed to generate project scope with AI. Please try again.")
