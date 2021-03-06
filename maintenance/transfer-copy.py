# SEN Q2: 50121
# EPA Q2: 49698
# SEN Q3: 67173

# To watch out:
#Students retaking the course from one quarter to the next still use the same
#email address. They may, when taking a later version submit, but it shows them
#enrolled in the earlier course. Can you simply switch them to the latest course?

# ------
# 1. Manually create the cours, and place the label number here.
target_course = '140638'
target_entries = ['1931107264',  # LD1
                  '1475539468',  # LD2
                  '1499960701',  # LD3
                  '370183435',   # LD4
                  '1371427444']  # LD5


# 2. Create entry points
from basic.models import EntryPoint, Course

orig_course = Course.objects.get(label='148884')       # where we will copy from
targ_course = Course.objects.get(label=target_course) # where we will copy to

for entry in orig_course.entrypoint_set.all():
    entry.id = None
    entry.save()
    entry.course=targ_course
    entry.save()

# 3. Manually edit the URL's to have the correct middle section.

# 4a. Create the Triggers for the course, and all entry points.
orig_ep = EntryPoint.objects.get(course=orig_course, LTI_id='1931107264')

for targ_ep in targ_course.entrypoint_set.all():
    print('Processing for {}'.format(targ_ep))
    assert(targ_ep.trigger_set.all().count() == 0)
    count = 0
    for trigger in orig_ep.trigger_set.all():
        trigger.id = None
        trigger.save()
        trigger.entry_point = targ_ep
        trigger.save()
        count += 1
    #
    print('Successfully added {} triggers'.format(count))

# 4b. Remove any triggers that are not needed. e.g. for the Progress Overview
# 4c. Change the dates on the triggers.

# 5. Create a new set of achieveConfigs for all courses, and all entry points.
from rubric.models import RubricTemplate, RItemTemplate
from basic.models import Course, EntryPoint


for target_id in target_entries:
    print('Processing for {}'.format(target_id))
    orig_ep = EntryPoint.objects.get(course=orig_course, LTI_id=target_id)
    targ_ep = EntryPoint.objects.get(course=targ_course, LTI_id=target_id)
    assert(orig_ep.achieveconfig_set.all().count() > 0)
    assert(targ_ep.achieveconfig_set.all().count() == 0)
    count = 0
    for achieve in orig_ep.achieveconfig_set.all():
        achieve.id = None
        achieve.save()
        achieve.entry_point = targ_ep
        achieve.save()
        count += 1
    print('Successfully added {} achievements'.format(count))
#--------------------

# 6. Copy rubric template, items and options from one course to another
# 7. Adjust the dates for the deadlines when finished
from rubric.models import RubricTemplate, RItemTemplate
from interactive.models import Trigger
for target_id in target_entries:
    print('Processing LTI {}'.format(target_id))
    # These have the added complexity that you have a .trigger, .next_trigger and
    # item templates and option templates that depend on them.
    #
    orig_ep = EntryPoint.objects.get(course=orig_course, LTI_id=target_id)
    targ_ep = EntryPoint.objects.get(course=targ_course, LTI_id=target_id)
    #
    src_templates = [t.title for t in orig_ep.rubrictemplate_set.all()]
    print(src_templates)
    #
    for src_template_name in src_templates:
        print('Processing template: {}'.format(src_template_name))
        new_title = src_template_name  # <-- same value because we are copying
                                       # course-to-course; it would a different
                                       # text here if we are copying within a course.
        #
        template = RubricTemplate.objects.get(entry_point=orig_ep,
                                              title=src_template_name)
        current_trigger_name = template.trigger.name
        targ_trigger = Trigger.objects.get(entry_point=targ_ep,
                                           name=template.trigger.name)
        targ_next_trigger = None
        if template.next_trigger:
            targ_next_trigger = Trigger.objects.get(entry_point=targ_ep,
                                                    name=template.next_trigger.name)
        copy_template = RubricTemplate.objects.get(entry_point=orig_ep,
                                                   title=src_template_name)
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
        print('--Done--')
    print('-Klaar-')



# Fix the uncreated assessment
# ----------------------------
from rubric.models import RubricTemplate, RItemTemplate, RItemActual
from interactive.models import EvaluationReport
unique_code = 'PQFBfEUzMKdH2Zbc'
reports = EvaluationReport.objects.filter(unique_code=unique_code)
report = reports[0]

template=RubricTemplate.objects.get(trigger=report.trigger)
r_actual = report.r_actual

# Creates the items (rows) associated with an actual rubric
for r_item in RItemTemplate.objects.filter(r_template=template).order_by('order'):
    r_item_actual = RItemActual(ritem_template = r_item,
                                r_actual = r_actual,
                                comment = '',
                                submitted = False)
    r_item_actual.save()



# How to push a person through to the next step (without waiting for all reviews)
#--------------
#* EPA Q2: https://wepeer.org/course/49698/90004256/
#* SEN Q2: https://wepeer.org/course/50121/90004256/
#* Abroad: https://wepeer.org/course/43639/90004256

#eg. FS is holding up JM. But JM was also reviewed by CG.

#1. Set a manual ``Achievement`` instance for the submitted/learner [JM] (who is being
   #held up) by their reviewer [FS]. Therefore give '[19] out' to JM. Make notes.
#2. Generate an EvaluationReport for the submitter [JM], so they can see their
   #feedback from the reviewer(s) that were able to complete their reviews.

   #Open the review report from the reviewer who has dropped out [FS], and select
   #their peer review in the overview page.
   #Click "Submit", and this will generate their EvaluationReport. Ensure you put a message that this is a blank review.


#2. Set a manual ``Achievement`` instance for the learner in the course:
   #'read_and_evaluated_all_reviews'