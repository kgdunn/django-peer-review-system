# Verbs: Submit, Review, Evaluate, Rebut, Assess

from django.http import HttpResponse
from django.template.context_processors import csrf
from django.template import Context, Template, loader

# Python imports
import sys
import json
import datetime

# This app
from .models import Trigger

# Our other apps
from grades.models import GradeItem, LearnerGrade
from submissions.views import get_submission, upload_submission
from submissions.forms import (UploadFileForm_one_file,
                               UploadFileForm_multiple_file)
from utils import send_email


def starting_point(request, course=None, learner=None, entry_point=None):
    """
    Start the interactive tool here:
    1. push a grade of zero to their gradebook, if the first time visiting.
    2. Call the triggers to process sequentially.
    3. Render the page.
    """

    # Step 1:
    gradeitem = GradeItem.objects.filter(entry=entry_point)
    if gradeitem:
        gitem = gradeitem[0]
    else:
        return HttpResponse('Please create a GradeItem attached to this Entry')

    gitem, first_time = LearnerGrade.objects.get_or_create(gitem=gitem,
                                                           learner=learner)
    if first_time:
        gitem.value = 0.0
        gitem.save()


    # Step 2: Call all triggers:
    triggers = Trigger.objects.filter(entry=entry_point,
                                      is_active=True).order_by('order')
    module = sys.modules[__name__]
    now_time = datetime.datetime.now(datetime.timezone.utc)

    ctx_objects = {'now_time': now_time,
                   'learner': learner,
                   'course': course,
                   'entry_point': entry_point,}
    ctx_objects.update(csrf(request)) # add the csrf; used in forms



    # First run through to ensure all triggers exist
    for trigger in triggers:
        try:
            func = getattr(module, trigger.function)
        except AttributeError:
            return HttpResponse('Please create function {0}'.format(\
                                                             trigger.function))

        kwargs = trigger.kwargs.replace('\r','').replace('\n','').replace(' ', '')
        if kwargs:
            try:
                _ = json.loads(kwargs)
            except json.decoder.JSONDecodeError as err:
                return HttpResponse(('Error parsing the kwargs: {0} [{1}]'
                                     .format(err, kwargs)))



    html = []
    html.append('<h3>Welcome {0}</h3>'.format(learner))
    overall_summary = ''

    global_page = """{% extends "basic/base.html" %}{% block content %}<hr>
    <!--SPLIT HERE-->\n{% endblock %}"""
    template_page = Template(global_page)
    context = Context(ctx_objects)
    page_header_footer = template_page.render(context)
    page_header, page_footer = page_header_footer.split('<!--SPLIT HERE-->')
    html.append(page_header)


    for trigger in triggers:
        # Then actually run each trigger, but only if the requirements are
        # met, and we are within the time range for it.

        run_trigger = True
        if (trigger.start_dt > now_time) and (trigger.end_dt <= now_time):
            run_trigger = False
        if gitem.value > trigger.upper:
            run_trigger = False
        if gitem.value < trigger.lower:
            run_trigger = False
        if not(run_trigger):
            continue

        func = getattr(module, trigger.function)
        args = []
        for item in trigger.args.split(','):
            args.append(item)

        if trigger.kwargs:
            kwargs = json.loads(trigger.kwargs.replace('\r','')\
                                .replace('\n','')\
                                .replace(' ', ''))
        else:
            kwargs = {}

        # Push these ``kwargs`` into trigger (getattr, settattr)
        for key, value in kwargs.items():
            if not(getattr(trigger, key, False)):
                setattr(trigger, key, value)

        # Add self to ctx_objects
        ctx_objects['self'] = trigger

        # Call the function, finally.
        html_template, summary_template = func(trigger,
                                                learner,
                                                args,
                                                ctx_objects=ctx_objects,
                                                entry_point=entry_point,
                                                gitem=gitem,
                                                request=request
                                               )
        html_trigger = Template(html_template).render(Context(ctx_objects))
        html.append(html_trigger)


    return HttpResponse(html)




def kick_off_email(trigger, learner, *args, entry_point=None, gitem=None,
                   request=None, **kwargs):
    """
    Initiates the kick-off email to the student, to encourage an upload.
    """
    subject = 'Upload document for: {}'.format(entry_point.LTI_title)
    template = """Please upload a PDF with N words. Tkank you."""
    template += '<br>kick_off_email'
    send_email(learner.email, subject, messages=template, delay_secs=0)

    # Assume the email is successfully sent. Adjust the ``gitem``:
    gitem.value = 1.0
    gitem.save(push=True)

    return ('', '')

def submitted_doc(trigger, learner, *args, ctx_objects=None,
                  entry_point=None, gitem=None, **kwargs):
    """
    The user has submitted their document:
    * send email to thank them
    * indicate that they can upload a new version
    * however, we wait until a pool of reviewers are available.
    """
    subject = '[{}] Your PDF upload has been received: '.format(\
        entry_point.LTI_title)
    template = """Thank you for your upload. Please wait for N submissions."""
    template += '<br>submitted_doc'
    #send_email(learner.email, subject, messages=template, delay_secs=0)

    # Email is successfully sent. Adjust the ``gitem`` to avoid spamming.
    #gitem.value +1.0
    #gitem.save(push=True)




def submission_form(trigger, learner, *args, entry_point=None, gitem=None,
                   request=None, ctx_objects=dict(), **kwargs):
    """
    Displays the submission form, and handles the upload of it.

    Fields that can be used in the template:
        {{submission}}                The ``Submission`` model instance
        {{submission_error_message}}  Any error message
        {{file_upload_form}}          The HTML for the upload form
        {{allow_submit}}              If submissions are allowed

    Settings possible in the kwargs, with the defaults are shown.
    {  "accepted_file_types_comma_separated": "PDF",
       "max_file_upload_size_MB": <unlimited>,  [specify as 10 (not a string)]
        "allow_multiple_files": "false",
        "send_email_on_success": "true"
    }
    allow_multiple_files

    """
    html_text = summary_line = ''

    # Remove the prior submission from the dict, so that PRs that use
    # multiple submission steps get the correct phase's submission
    #ctx_objects.pop('submission', None)

    # Get the (prior) submission
    submission = prior_submission = get_submission(learner, entry_point)

    # What the admin's see
    if learner.role != 'Learn':
        ctx_objects['self'].admin_overview = 'ADMIN TEXT GOES HERE STILL.'

        #no_submit = dict()
        #all_groups = dict()
        #all_subs = Submission.objects.filter(pr_process=self.pr,
                                             #phase=self, is_valid=True).\
            #order_by('datetime_submitted')
        #if self.pr.uses_groups:
            #all_groups = self.pr.gf_process.group_set.filter()
            #no_submit = all_groups
            #for item in all_subs:
                #no_submit = no_submit.exclude(id=item.group_submitted_id)

        #ctx_objects['no_submit'] = no_submit
        #ctx_objects['all_groups'] = all_groups
        #ctx_objects['all_subs'] = all_subs
        #content = loader.render_to_string('review/admin-submissions.html',
                                          #context=ctx_objects,
                                          #request=request,
                                          #using=None)
        #ctx_objects['self'].admin_overview = content
    if not(getattr(trigger, 'accepted_file_types_comma_separated', False)):
        trigger.accepted_file_types_comma_separated = 'PDF'

    if not(getattr(trigger, 'max_file_upload_size_MB', False)):
        trigger.max_file_upload_size_MB = 10

    if not(hasattr(trigger, 'send_email_on_success')):
        trigger.send_email_on_success = True



    if getattr(trigger, 'allow_multiple_files', False):
        file_upload_form = UploadFileForm_multiple_file()
    else:
        file_upload_form = UploadFileForm_one_file()

    submission_error_message = ''
    if request.FILES:
        submit_inst = upload_submission(request, learner, entry_point, trigger)
        if isinstance(submit_inst, tuple):
            # Problem with the upload
            submission_error_message = submit_inst[1]
            submission = prior_submission
        else:
            # Successfully uploaded a document
            submission_error_message = ''
            submission = submit_inst
            gitem.value = 3.0
            gitem.save(push=True)
            schedule_review(learner, submission)
            summary_line = ['You uploaded on ...', 'LINK'] # what if there's an error?
    else:
        submission = prior_submission

    # Store some fields on the ``trigger`` for rendering in the template
    trigger.submission = submission
    trigger.submission_error_message = submission_error_message
    trigger.file_upload_form = ctx_objects['file_upload_form'] = \
        file_upload_form

    html_text = trigger.template

    trigger.allow_submit = True  # False, if no more submissions allowed

    return html_text, summary_line


def submitted_already(trigger, learner, *args, entry_point=None, gitem=None,
                    request=None, ctx_objects=dict(), **kwargs):

    """
    Simply displays the prior submission, if any.
    """
    # Get the (prior) submission
    trigger.submission = get_submission(learner, entry_point)

    summary_line = ['You uploaded on ...', 'LINK'] # what if there's an error?
    return (trigger.template, summary_line)


def interactions_to_come(trigger, learner, *args, entry_point=None, gitem=None,
                         request=None, ctx_objects=dict(), **kwargs):
    """
    Does nothing of note, other than display the remaining steps for the user.
    """
    summary_line = ''
    return (trigger.template, summary_line)


def schedule_review(learner, submission):
    """
    Pushes a schedule: the learner submission will be queued for processing.
    """
    pass