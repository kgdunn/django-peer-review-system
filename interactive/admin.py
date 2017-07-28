from django.contrib import admin
from .models import Trigger


class TriggerAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "lower", "upper", "function", "is_active",
                    "entry", "start_dt", "end_dt")
    ordering = ['order', 'name']
    list_filter = ['entry']
admin.site.register(Trigger, TriggerAdmin)




