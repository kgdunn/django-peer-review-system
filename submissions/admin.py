from django.contrib import admin
from submissions.models import Submission

class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("submitted_by", "status", "is_valid", "file_upload",
                    "submitted_file_name", "group_submitted", "trigger",
                    "entry_point", "datetime_submitted")
    list_filter = ['entry_point']
admin.site.register(Submission, SubmissionAdmin)