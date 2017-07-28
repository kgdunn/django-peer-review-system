from django.contrib import admin
from submissions.models import Submission

class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("submitted_by", "status", "is_valid", "file_upload",
                    "submitted_file_name", "group_submitted",
                    "datetime_submitted")
admin.site.register(Submission, SubmissionAdmin)