"""
Backfill AI profiles for existing freelancers and projects.

This script generates AI profiles for all freelancers and projects
that don't have them yet.
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fyp_project.settings')
django.setup()

from core.models import Freelancer, Project, FreelancerAIProfile, ProjectAIProfile
from core.ai_matching import MatchEngine
from django.db import transaction

def backfill_freelancer_profiles():
    """Generate AI profiles for all freelancers without one"""
    print("\n=== Backfilling Freelancer AI Profiles ===")
    
    # Get freelancers without AI profiles
    freelancers_without_profile = Freelancer.objects.filter(ai_profile__isnull=True)
    total = freelancers_without_profile.count()
    
    if total == 0:
        print("✅ All freelancers already have AI profiles")
        return
    
    print(f"Found {total} freelancers without AI profiles")
    
    engine = MatchEngine()
    success_count = 0
    error_count = 0
    
    for i, freelancer in enumerate(freelancers_without_profile, 1):
        try:
            print(f"[{i}/{total}] Generating AI profile for: {freelancer.full_name or freelancer.user.username}")
            engine.generate_freelancer_ai_profile(freelancer)
            success_count += 1
        except Exception as e:
            print(f"   ❌ Error: {e}")
            error_count += 1
    
    print(f"\n✅ Completed: {success_count} profiles created, {error_count} errors")

def backfill_project_profiles():
    """Generate AI profiles for all projects without one"""
    print("\n=== Backfilling Project AI Profiles ===")
    
    # Get projects without AI profiles
    projects_without_profile = Project.objects.filter(ai_profile__isnull=True)
    total = projects_without_profile.count()
    
    if total == 0:
        print("✅ All projects already have AI profiles")
        return
    
    print(f"Found {total} projects without AI profiles")
    
    engine = MatchEngine()
    success_count = 0
    error_count = 0
    
    for i, project in enumerate(projects_without_profile, 1):
        try:
            print(f"[{i}/{total}] Generating AI profile for: {project.title}")
            engine.generate_project_ai_profile(project)
            success_count += 1
        except Exception as e:
            print(f"   ❌ Error: {e}")
            error_count += 1
    
    print(f"\n✅ Completed: {success_count} profiles created, {error_count} errors")

def regenerate_all_profiles():
    """Regenerate all AI profiles (useful after model changes)"""
    print("\n=== Regenerating All AI Profiles ===")
    
    # Delete existing profiles
    freelancer_count = FreelancerAIProfile.objects.count()
    project_count = ProjectAIProfile.objects.count()
    
    print(f"Deleting {freelancer_count} freelancer AI profiles...")
    FreelancerAIProfile.objects.all().delete()
    
    print(f"Deleting {project_count} project AI profiles...")
    ProjectAIProfile.objects.all().delete()
    
    # Regenerate
    backfill_freelancer_profiles()
    backfill_project_profiles()

if __name__ == '__main__':
    import sys
    
    print("=" * 60)
    print("AI Profile Backfill Script")
    print("=" * 60)
    
    if len(sys.argv) > 1 and sys.argv[1] == '--regenerate':
        regenerate_all_profiles()
    else:
        backfill_freelancer_profiles()
        backfill_project_profiles()
    
    print("\n" + "=" * 60)
    print("✅ Backfill completed!")
    print("=" * 60)
    
    # Show final counts
    print(f"\nFinal counts:")
    print(f"  FreelancerAIProfile: {FreelancerAIProfile.objects.count()}")
    print(f"  ProjectAIProfile: {ProjectAIProfile.objects.count()}")
