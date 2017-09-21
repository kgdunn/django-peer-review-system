# To run the scheduled tasks
from django_q.tasks import schedule, Schedule
try:
    import tasks
    if not(Schedule.objects.filter(func='basic.tasks.send_emails__evaluation')):


        schedule('basic.tasks.send_emails__evaluation_and_rebuttal',
                 schedule_type=Schedule.HOURLY)

        schedule('basic.tasks.email__no_reviews_after_submission',
                 schedule_type=Schedule.HOURLY)
except:
    # This is needed to catch errors when running manage.py migrate on a fresh
    # database install.
    print('WARNING: could not create the scheduled tasks')
    pass
# ----- End task scheduling

from django.contrib import admin
from .models import Course, Person
from .models import EntryPoint, Email_Task
from .models import Group_Formation_Process, Group, GroupEnrolled, Token


class CourseAdmin(admin.ModelAdmin):
    list_display = ("name", "label", "base_url")
admin.site.register(Course, CourseAdmin)



class PersonAdmin(admin.ModelAdmin):
    list_display = ("user_ID", "display_name", "initials", "is_validated",
                    "last_lis", "role", "email", "created", "modified")
admin.site.register(Person, PersonAdmin)



class EntryPointAdmin(admin.ModelAdmin):
    list_display = ("LTI_title", "course", "order", "uses_groups", "LTI_system",
                    "LTI_id", 'full_URL')
    ordering = ['order',]
    list_filter = ['course']
admin.site.register(EntryPoint, EntryPointAdmin)



class GroupFormationProcessAdmin(admin.ModelAdmin):
    list_display = ("name", "course",)
admin.site.register(Group_Formation_Process, GroupFormationProcessAdmin)



class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "gfp", "description", "capacity", )
admin.site.register(Group, GroupAdmin)



class GroupEnrolledAdmin(admin.ModelAdmin):
    list_display = ("person", "group", "is_enrolled", "created", "modified")
admin.site.register(GroupEnrolled, GroupEnrolledAdmin)




class TokenAdmin(admin.ModelAdmin):
    list_display = ("person", "was_used", "hash_value", "time_used", "next_uri")
admin.site.register(Token, TokenAdmin)


class Email_Task_Admin(admin.ModelAdmin):
    list_display = ("learner", "entry_point", "subject", "sent_datetime")
admin.site.register(Email_Task, Email_Task_Admin)

# =======
from django.contrib.sessions.models import Session
class SessionAdmin(admin.ModelAdmin):
    def _session_data(self, obj):
        return obj.get_decoded()
    list_display = ['session_key', '_session_data', 'expire_date']
admin.site.register(Session, SessionAdmin)