# Aim: copy rubric template, items and options from one course to another


from rubric.models import RubricTemplate, RItemTemplate
from basic.models import Course, EntryPoint
from interactive.models import Trigger

#--------------------
# AIM: Create a new set of triggers for all courses, and all entry points.
# Specify the course, and the entry_point manually, via the LTI_ID
# (which is assumed to have been created already)
orig_course = Course.objects.get(label='36957')
orig_ep = EntryPoint.objects.get(course=orig_course, LTI_id='370183435')
targ_course = Course.objects.get(label='43639')
targ_ep = EntryPoint.objects.get(course=targ_course, LTI_id='370183435')

assert(orig_ep.trigger_set.all().count() == 0)
assert(targ_ep.trigger_set.all().count() == 0)

for trigger in orig_ep.trigger_set.all():
    trigger.id = None
    trigger.save()
    trigger.entry_point = targ_ep
    trigger.save()

#--------------------
# AIM: Create a new set of achieveConfigs for all courses, and all entry points.
orig_course = Course.objects.get(name='SEN2321')
orig_ep = EntryPoint.objects.get(course=orig_course,
                                 LTI_id='1931107264')
targ_course = Course.objects.get(name='Prep MSc')
target_entries = ['1931107264', '1475539468',   '1499960701',
                  '370183435', '1371427444']

for target in target_entries:
    targ_ep = EntryPoint.objects.get(course=targ_course,
                                     LTI_id=target)
    assert(orig_ep.achieveconfig_set.all().count() > 0)
    assert(targ_ep.achieveconfig_set.all().count() == 0)

    for achieve in orig_ep.achieveconfig_set.all():
        achieve.id = None
        achieve.save()
        achieve.entry_point = targ_ep
        achieve.save()
#--------------------


# Now you have the triggers. The next step is to create rubric templates.
from rubric.models import RubricTemplate, RItemTemplate
from basic.models import Course, EntryPoint
from interactive.models import Trigger


# These have the added complexity that you have a .trigger, .next_trigger and
# item templates and option templates that depend on them.
orig_course = Course.objects.get(label='36957')
orig_ep = EntryPoint.objects.get(course=orig_course, LTI_id='1371427444')
targ_course = Course.objects.get(label='43639')
targ_ep = EntryPoint.objects.get(course=targ_course, LTI_id='1371427444')

src_template_name = 'LD5 peer review'
src_template_name = 'LD5 evaluation'
src_template_name = 'LD5 rebuttal'
src_template_name = 'LD5 assessment'
new_title = src_template_name  # <-- same value because we are copying
                               # course-to-course; it would a different
                               # text here if we are copying within a course.

template = RubricTemplate.objects.get(entry_point=orig_ep, title=src_template_name)

current_trigger_name = template.trigger.name
targ_trigger = Trigger.objects.get(entry_point=targ_ep, name=template.trigger.name)
targ_next_trigger = None
if template.next_trigger:
    targ_next_trigger = Trigger.objects.get(entry_point=targ_ep, name=template.next_trigger.name)

copy_template = RubricTemplate.objects.get(entry_point=orig_ep, title=src_template_name)


# Now create a new template
template.id = None
template.save()
template.entry_point = targ_ep
template.title = new_title
template.trigger = targ_trigger
template.next_trigger = targ_next_trigger
template.save()
src_items = RItemTemplate.objects.filter(r_template=copy_template)
for item in src_items:
    # First get the associated options
    options = item.roptiontemplate_set.all()
    # Then copy the parent template to the new one
    item.pk = None
    item.r_template = template
    item.save()
    # Then re-parent the options to the newly created/saved item
    for opt in options:
        opt.pk = None
        opt.rubric_item = item
        opt.save()
    # All done with options

# Done with all items