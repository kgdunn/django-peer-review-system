from django.http import HttpResponse
from django.shortcuts import render

# This app's imports
from .models import KeyTermSetting, KeyTermTask
from .forms import UploadFileForm_one_file

# Imports from other apps

#from submissions.models import Submission
from submissions.views import upload_submission
from basic.views import entry_point_discovery
from grades.views import push_grade


# Logging
import logging
logger = logging.getLogger(__name__)

def start_keyterm(request, course=None, learner=None, entry_point=None):
    """
    """
    #logger.debug(request.POST)

    keyterm_finalized = False

    # TODO: Code here to determine if the user has finalized their keyterm
    # TODO: make the user resume from the last point they were at, if reloading

    if request.POST.get('preview-keyterm', ''):
        return preview_keyterm(request, course, learner, entry_point)

    if request.POST.get('draft-keyterm', ''):
        return draft_keyterm(request, course, learner, entry_point)

    if request.POST.get('submit-keyterm', ''):
        return submit_keyterm(request, course, learner, entry_point)

    if request.POST.get('finalize-keyterm', '') or keyterm_finalized:
        return finalize_keyterm(request, course, learner, entry_point)

    # If nothing else (usually the first time we start, we start with drafting)
    return draft_keyterm(request, course, learner, entry_point)


def draft_keyterm(request, course=None, learner=None, entry_point=None,
                  error_message=''):
    """
    The user is in Draft mode: adding the text
    """
    prior = learner.keytermtask_set.filter(keyterm__entry_point=entry_point)
    if prior.count():
        keytermtask = prior[0]
        keyterm = keytermtask.keyterm
    else:
        # Create the new KeyTermTask for this learner
        try:
            keyterm = KeyTermSetting.objects.get(entry_point=entry_point)
        except KeyTermSetting.DoesNotExist:
            return HttpResponse(('Please add KeyTerm to database first; and '
                                 "don't forget to add the GradeItem too."))
        keytermtask = KeyTermTask(keyterm=keyterm,
                                  learner=learner,
                                  definition_text='',
                                  explainer_text='',
                                  reference_text='',
                                  is_in_draft=True
                                  )
        keytermtask.save()

    # We have 4 states: set the correct settings (in case page is reloaded here)
    keytermtask.is_in_draft = True
    keytermtask.is_in_preview = False
    keytermtask.is_submitted = False
    keytermtask.is_finalized = False
    keytermtask.save()

    # Checkbox shown if image was uploaded already (date and time also; size)
    # Reference should also be shown

    entry_point.file_upload_form = UploadFileForm_one_file()


    # TODO: real-time saving of the text as it is typed
    ctx = {'error_message': error_message,
           'keytermtask': keytermtask,
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           'grade_push_url': request.POST.get('lis_outcome_service_url', '')
           }
    logger.debug(ctx)
    return render(request, 'keyterms/draft.html', ctx)


def preview_keyterm(request, course=None, learner=None, entry_point=None):
    """
    """

    prior = learner.keytermtask_set.filter(keyterm__entry_point=entry_point)
    if prior.count():
        keytermtask = prior[0]
        keyterm = keytermtask.keyterm
    else:
        try:
            keyterm = KeyTermSetting.objects.get(entry_point=entry_point)
        except KeyTermSetting.DoesNotExist:
            logger.error('Preview: An error occurred. [{0}]'.format(learner))
            return HttpResponse('An error occurred.')

    # 1. Now you have the task ``keytermtask``: set state
    # 2. Store new values in the task
    # 3. Process the image (store it too, but only in staging area)
    # 4. Render the template image  (store it too, but only in staging area)
    # 5. Float the submit buttons left and right of each other

    # We have 4 states: set the correct settings (in case page is reloaded here)
    keytermtask.is_in_draft = True   # intentional
    keytermtask.is_in_preview = True
    keytermtask.is_submitted = False
    keytermtask.is_finalized = False


    # For the ``Submission`` app we need a Trigger. We don't have that, or
    # need it. So abuse ``entry_point`` as the trigger instead.
    # A ``trigger`` needs an entry_point field, so just refer back to itself.
    entry_point.entry_point = entry_point
    entry_point.accepted_file_types_comma_separated = 'JPEG, PNG, JPG'
    entry_point.max_file_upload_size_MB = 5
    entry_point.send_email_on_success = False

    # Get the (prior) image submission
    submission = prior_submission = None
    subs = learner.submission_set.filter(is_valid=True, entry_point=entry_point)
    subs = subs.order_by('-datetime_submitted')
    if subs.count():
        submission = prior_submission = subs[0]


    error_message = ''
    if request.FILES:

        submit_inst = upload_submission(request, learner, trigger=entry_point,
                                        no_thumbnail=False)

        if isinstance(submit_inst, tuple):
            # Problem with the upload
            error_message = submit_inst[1]
            submission = prior_submission
        else:
            # Successfully uploaded a document
            error_message = ''
            submission = submit_inst

        # Now that the image is processed:
        keytermtask.image_raw = submission


    definition_text = request.POST.get('keyterm-definition', '')
    keytermtask.definition_text = definition_text
    if len(definition_text) > 500:
        keytermtask.definition_text = definition_text[0:500] + ' ...'

    explainer_text = request.POST.get('keyterm-explanation', '')
    keytermtask.explainer_text = explainer_text
    if len(explainer_text) > 1000:
            keytermtask.explainer_text = explainer_text[0:1000] + ' ...'

    keytermtask.reference_text = 'STILL TO COME'
    keytermtask.save()

    # We have saved, but if there was an error message: go back to DRAFT
    if error_message:
        return draft_keyterm(request, course=course, learner=learner,
                        entry_point=entry_point, error_message=error_message)


    ctx = {'keytermtask': keytermtask,
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           'grade_push_url': request.POST.get('lis_outcome_service_url', '')
           }
    return render(request, 'keyterms/preview.html', ctx)


def submit_keyterm(request, course=None, learner=None, entry_point=None):
    """
    """
    prior = learner.keytermtask_set.filter(keyterm__entry_point=entry_point)
    if prior.count():
        keytermtask = prior[0]
        keyterm = keytermtask.keyterm
    else:
        try:
            keyterm = KeyTermSetting.objects.get(entry_point=entry_point)
        except KeyTermSetting.DoesNotExist:
            logger.error('Submit: An error occurred. [{0}]'.format(learner))
            return HttpResponse('An error occurred.')

    # 1. Now you have the task ``keytermtask``: set state
    # 2. Store new values in the task
    # 3. Process the image (store it too, but only in staging area)
    # 4. Render the template image  (store it too, but only in staging area)
    # 5. Float the submit buttons left and right of each other

    # We have 4 states: set the correct settings (in case page is reloaded here)
    keytermtask.is_in_draft = False
    keytermtask.is_in_preview = False
    keytermtask.is_submitted = True
    keytermtask.is_finalized = False


    # Get all other user's keyterms: how many other keyterms are uploaded already?
    # Float the submit buttons left and right of each other

    ctx = {'keytermtask': keytermtask,
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           'grade_push_url': request.POST.get('lis_outcome_service_url', '')
           }
    return render(request, 'keyterms/submit.html', ctx)

def finalize_keyterm(request, course=None, learner=None, entry_point=None):
    """
    """
    prior = learner.keytermtask_set.filter(keyterm__entry_point=entry_point)
    if prior.count():
        keytermtask = prior[0]
        keyterm = keytermtask.keyterm
    else:
        try:
            keyterm = KeyTermSetting.objects.get(entry_point=entry_point)
        except KeyTermSetting.DoesNotExist:
            logger.error('Finalize: An error occurred. [{0}]'.format(learner))
            return HttpResponse('An error occurred.')

    # We have 4 states: set the correct settings (in case page is reloaded here)
    keytermtask.is_in_draft = False
    keytermtask.is_in_preview = False
    keytermtask.is_submitted = False
    keytermtask.is_finalized = True
    keytermtask.save()

    # Get all prior keyterms: and show their thumbnails in random order
    # Show how many votes the user has left?
    # Show



    # TODO: push the grade async
    grade_push_url=request.POST.get('lis_outcome_service_url', '')
    response = push_grade(learner=learner,
                          grade_value=100,
                          entry_point=entry_point,
                          grade_push_url=grade_push_url,
                          testing=False)

    logger.debug('Grade for {0} at [{1}]; response: {2}'.format(learner,
                                                                grade_push_url,
                                                                response))

    ctx = {'keytermtask': keytermtask,
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           }
    return render(request, 'keyterms/finalize.html', ctx)

