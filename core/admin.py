from django.contrib import admin
from .models import Freelancer, Project, ProjectCategory, Industry

# Register your models here.
admin.site.register(Freelancer)
admin.site.register(Project)
admin.site.register(ProjectCategory)
admin.site.register(Industry)
