from django.shortcuts import render
from .forms import SkillsForm  # ← Add this (we'll create forms.py next)
from .models import Job        # ← Add this
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Create your views here.
def home(request):
    return render(request, 'core/home.html')

def client_home(request):
    return render(request, 'core/client_home.html')

def client_project(request):
    return render(request, 'core/client_project.html')

def client_about(request):
    return render(request, 'core/client_about.html')

def client_chat(request):
    return render(request, 'core/client_chat.html')

def match_jobs(request):
    """
    AI-Powered Job Matching Demo
    Freelancer enters skills → System returns ranked job matches with relevance scores
    Uses TF-IDF + Cosine Similarity (foundation for future BERT upgrade)
    """
    form = SkillsForm()
    results = []
    query = ""

    if request.method == 'POST':
        form = SkillsForm(request.POST)
        if form.is_valid():
            query = form.cleaned_data['skills'].strip()

            if query:
                # Get all jobs from database
                jobs = Job.objects.all()

                if jobs.exists():
                    # Prepare documents: job descriptions + freelancer skills
                    job_descriptions = [job.description for job in jobs]
                    documents = job_descriptions + [query]

                    # Vectorize using TF-IDF
                    vectorizer = TfidfVectorizer(stop_words='english', lowercase=True)
                    tfidf_matrix = vectorizer.fit_transform(documents)

                    # Compute similarity between freelancer skills (last vector) and all jobs
                    query_vector = tfidf_matrix[-1]  # Last row = user's skills
                    job_vectors = tfidf_matrix[:-1]

                    cosine_similarities = cosine_similarity(query_vector, job_vectors).flatten()

                    # Create results list
                    for idx, job in enumerate(jobs):
                        score = cosine_similarities[idx]
                        if score > 0.05:  # Filter very low matches
                            results.append({
                                'job': job,
                                'score': round(score * 100, 2),  # Convert to percentage
                                'snippet': job.description[:200] + "..." if len(job.description) > 200 else job.description
                            })

                    # Sort by relevance (highest first)
                    results.sort(key=lambda x: x['score'], reverse=True)

    context = {
        'form': form,
        'results': results,
        'query': query,
        'title': 'AI-Powered Job Matching Results'
    }

    return render(request, 'core/match.html', {'form': form, 'results': results})

def login(request):
    if request.method == 'POST':
        role = request.POST.get('role')
        # Simulate successful login (no real check)
        if role == 'freelancer':
            return render(request, 'core/freelancer_home.html')  # New freelancer UI
        else:
            return render(request, 'core/client_home.html')  # Existing client UI
    # GET: Show login page (home.html)
    return render(request, 'core/home.html')