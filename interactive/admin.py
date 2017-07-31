from django.contrib import admin
from .models import Trigger, GroupConfig, Membership


class TriggerAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "lower", "upper", "function", "is_active",
                    "entry", "start_dt", "end_dt")
    ordering = ['order', 'name']
    list_filter = ['entry']
admin.site.register(Trigger, TriggerAdmin)


class GroupConfigAdmin(admin.ModelAdmin):
    list_display = ("group_name", "course",)
    ordering = ['course', '-group_name']
admin.site.register(GroupConfig, GroupConfigAdmin)


class MembershipAdmin(admin.ModelAdmin):
    list_display = ("group", "learner", "role")
    #ordering = ['course', '-group_name']
admin.site.register(Membership, MembershipAdmin)


