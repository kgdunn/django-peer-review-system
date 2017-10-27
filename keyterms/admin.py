from django.contrib import admin
from .models import KeyTerm, KeyTermTask, Thumbs


class KeyTermAdmin(admin.ModelAdmin):
    list_display = ("keyterm", "entry_point", "max_thumbs", "terms_per_page",
                    "min_submissions_before_voting", "deadline_for_voting")
admin.site.register(KeyTerm, KeyTermAdmin)


class KeyTermTaskAdmin(admin.ModelAdmin):
    list_display = ("keyterm", "learner",
                    "last_edited", "allow_to_share", "is_in_draft",
                    "is_finalized", "is_submitted", )
admin.site.register(KeyTermTask, KeyTermTaskAdmin)


class ThumbsAdmin(admin.ModelAdmin):
    list_display = ("keytermtask", "voter", "awarded",
                    "last_edited", )
admin.site.register(Thumbs, ThumbsAdmin)

