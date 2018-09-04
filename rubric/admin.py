from django.contrib import admin

from .models import RubricTemplate, RubricActual
from .models import RItemTemplate, RItemActual
from .models import ROptionTemplate, ROptionActual


class RubricTemplateAdmin(admin.ModelAdmin):
    list_display = ("title", "entry_point", "trigger", "maximum_score",
                    "show_order", "hook_function", )
    ordering = ['-entry_point', ]
    list_max_show_all = 500
    list_per_page = 500
    ordering = ['-r_template__entry_point', 'order']

admin.site.register(RubricTemplate, RubricTemplateAdmin)



class RubricActualAdmin(admin.ModelAdmin):
    list_display = ("submission", "submitted", "status", "graded_by",
                    "rubric_code", "next_code", "created", "modified")
    list_max_show_all = 500
    list_per_page = 500
admin.site.register(RubricActual, RubricActualAdmin)



class RItemTemplateAdmin(admin.ModelAdmin):
    list_display = ("r_template", "order", "max_score", "option_type",
                    "criterion",)
    ordering = ['-r_template', 'order']
    list_filter = ['r_template__entry_point']
admin.site.register(RItemTemplate, RItemTemplateAdmin)



class RItemActualAdmin(admin.ModelAdmin):
    list_display = ("ritem_template", "submitted", "comment",
                    "created", "modified",)
admin.site.register(RItemActual, RItemActualAdmin)



class ROptionActualAdmin(admin.ModelAdmin):
    list_display = ("roption_template", "ritem_actual", "submitted",
                    "comment", "created", "modified")
admin.site.register(ROptionActual, ROptionActualAdmin)




class ROptionTemplateAdmin(admin.ModelAdmin):
    list_display = ("rubric_item", "order", "score", 'criterion')
    ordering = ['rubric_item', 'order']

    list_filter = ['rubric_item__r_template',
                   'rubric_item__r_template__entry_point', ]
admin.site.register(ROptionTemplate, ROptionTemplateAdmin)

