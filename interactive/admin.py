from django.contrib import admin
from .models import Trigger, GroupConfig, Membership, ReviewReport
from .models import EvaluationReport, AchieveConfig, Achievement



class AchieveConfigAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "order", "entry_point")
    ordering = ['entry_point', "order"]
admin.site.register(AchieveConfig, AchieveConfigAdmin)


class AchievementAdmin(admin.ModelAdmin):
    list_display = ("learner", "achieved", "when")
admin.site.register(Achievement, AchievementAdmin)


class TriggerAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "lower", "upper", "function", "is_active",
                    "entry_point", "start_dt", "end_dt")
    ordering = ['order', 'name']
    list_filter = ['entry_point']
admin.site.register(Trigger, TriggerAdmin)


class GroupConfigAdmin(admin.ModelAdmin):
    list_display = ("group_name", "entry_point",)
    ordering = ['entry_point', '-group_name']
admin.site.register(GroupConfig, GroupConfigAdmin)


class MembershipAdmin(admin.ModelAdmin):
    list_display = ("group", "learner", "role")
admin.site.register(Membership, MembershipAdmin)



class ReviewReportAdmin(admin.ModelAdmin):
    list_display = ("reviewer", "trigger", "submission", "grpconf",
                    "unique_code", "submitter_code",
                    "created", "last_viewed", "order")
admin.site.register(ReviewReport, ReviewReportAdmin)



class EvaluationReportAdmin(admin.ModelAdmin):
    list_display = ("peer_reviewer", "evaluator",
                    "r_actual", "trigger", "submission", "unique_code",
                    "created", "last_viewed")
admin.site.register(EvaluationReport, EvaluationReportAdmin)


