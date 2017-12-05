from django.contrib import admin
from .models import KeyTermSetting, KeyTermTask, Thumbs


class KeyTermSettingAdmin(admin.ModelAdmin):
    list_display = ("keyterm", "entry_point", "max_thumbs", "terms_per_page",
                    "min_submissions_before_voting", "deadline_for_submission",
                    "deadline_for_voting")
admin.site.register(KeyTermSetting, KeyTermSettingAdmin)



class KeyTermTaskAdmin(admin.ModelAdmin):
    list_display = ("keyterm", "learner", "lookup_hash",
                    "last_edited", "is_in_draft", "is_finalized",
                    "is_submitted", )
    list_per_page = 1000
admin.site.register(KeyTermTask, KeyTermTaskAdmin)



class ThumbsAdmin(admin.ModelAdmin):
    list_display = ("keytermtask", "voter", "awarded",
                    "last_edited", )
    list_per_page = 1000
admin.site.register(Thumbs, ThumbsAdmin)

