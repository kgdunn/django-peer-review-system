from django.contrib import admin
from .models import Trigger, GroupConfig, Membership, ReviewReport
from .models import EvaluationReport, AchieveConfig, Achievement
from .models import ReleaseConditionConfig, ReleaseCondition


class AchieveConfigAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "score", "entry_point")
    ordering = ['entry_point', "score"]
admin.site.register(AchieveConfig, AchieveConfigAdmin)


class AchievementAdmin(admin.ModelAdmin):
    list_display = ("learner", "achieved", "when", "get_ep")

    def get_ep(self, obj):
        return str(obj.achieved.entry_point)

    get_ep.admin_order_field = 'entry_point'
    get_ep.short_description = 'Entry Point'
admin.site.register(Achievement, AchievementAdmin)


class ReleaseConditionConfigAdmin(admin.ModelAdmin):
    list_display = ("name", "entry_point", "all_apply", "any_apply")
    ordering = ['entry_point', ]
admin.site.register(ReleaseConditionConfig, ReleaseConditionConfigAdmin)


class ReleaseConditionAdmin(admin.ModelAdmin):
    list_display = ("rc_config", "achieveconfig",  "order")
    ordering = ['rc_config', "achieveconfig"]
admin.site.register(ReleaseCondition, ReleaseConditionAdmin)


class TriggerAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "function", "is_active",
                    "entry_point", "start_dt", "deadline_dt", )
    ordering = ["-entry_point", 'order', 'name']
    list_filter = ['entry_point']
admin.site.register(Trigger, TriggerAdmin)


class GroupConfigAdmin(admin.ModelAdmin):
    list_display = ("group_name", "entry_point",)
    ordering = ['entry_point', '-group_name']
    list_filter = ['entry_point']
admin.site.register(GroupConfig, GroupConfigAdmin)


class MembershipAdmin(admin.ModelAdmin):
    list_display = ("group", "learner", "role")
admin.site.register(Membership, MembershipAdmin)


class ReviewReportAdmin(admin.ModelAdmin):
    list_display = ("reviewer", "entry_point", "submission", "grpconf",
                    "unique_code",
                    "created", "last_viewed", "order")
    list_filter = ['entry_point']
admin.site.register(ReviewReport, ReviewReportAdmin)


class EvaluationReportAdmin(admin.ModelAdmin):
    list_display = ("evaluator", "peer_reviewer", "unique_code", "prior_code",
                    "sort_report", "submission", "r_actual", "trigger",
                    "created", "last_viewed")
admin.site.register(EvaluationReport, EvaluationReportAdmin)


