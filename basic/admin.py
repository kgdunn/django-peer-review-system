from django.contrib import admin

from .models import Course, Person
from .models import EntryPoint
from .models import Group, GroupEnrolled



class CourseAdmin(admin.ModelAdmin):
    list_display = ("name", "label", "base_url")
admin.site.register(Course, CourseAdmin)



class PersonAdmin(admin.ModelAdmin):
    list_display = ("email", "display_name", "is_active", "user_ID", "last_lis",
                    "role")
admin.site.register(Person, PersonAdmin)



class EntryPointAdmin(admin.ModelAdmin):
    list_display = ("LTI_title", "course", "order", "uses_groups", "LTI_system",
                    "LTI_id", 'full_URL')
    ordering = ['order',]
    list_filter = ['course']
admin.site.register(EntryPoint, EntryPointAdmin)



class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "course", "description", "capacity", )
admin.site.register(Group, GroupAdmin)



class GroupEnrolledAdmin(admin.ModelAdmin):
    list_display = ("person", "group", "is_enrolled", "created", "modified")
admin.site.register(GroupEnrolled, GroupEnrolledAdmin)


