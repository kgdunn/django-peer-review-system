from django.contrib import admin
from .models import GradeBook, GradeCategory, GradeItem, LearnerGrade



class GradeBookAdmin(admin.ModelAdmin):
    list_display = ("course", "passing_value", "max_score",)
admin.site.register(GradeBook, GradeBookAdmin)



class GradeCategoryAdmin(admin.ModelAdmin):
    list_display = ("gradebook", "display_name", "order", "max_score", "weight")
    ordering = ['order',]
admin.site.register(GradeCategory, GradeCategoryAdmin)



class GradeItemAdmin(admin.ModelAdmin):
    list_display = ("category", "display_name", "order", "max_score", "link",
                    "weight")
    ordering = ['order',]
admin.site.register(GradeItem, GradeItemAdmin)



class LearnerGradeAdmin(admin.ModelAdmin):
    list_display = ("gitem", "learner", "value")
    ordering = ['learner', 'gitem']
    list_filter = ['learner']
    list_max_show_all = 1000
    list_per_page = 1000
admin.site.register(LearnerGrade, LearnerGradeAdmin)





