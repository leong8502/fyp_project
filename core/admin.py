from django.contrib import admin
from .models import Freelancer, Project, ProjectCategory, Industry, ProjectApplication, Milestone, ProjectActivity, Escrow, Transaction, Wallet, Review

# Register your models here.
admin.site.register(Freelancer)
admin.site.register(Project)
admin.site.register(ProjectCategory)
admin.site.register(Industry)
admin.site.register(ProjectApplication)
admin.site.register(Milestone)
admin.site.register(ProjectActivity)
admin.site.register(Escrow)
admin.site.register(Transaction)
admin.site.register(Wallet)
admin.site.register(Review)
