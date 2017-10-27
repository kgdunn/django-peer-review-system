from django.http import HttpResponse
from django.shortcuts import render
from basic.views import entry_point_discovery

from grades.views import push_grade

from .models import KeyTerm, KeyTermTask

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


def draft_keyterm(request, course=None, learner=None, entry_point=None):
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
            keyterm = KeyTerm.objects.get(entry_point=entry_point)
        except KeyTerm.DoesNotExist:
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

    # Get prior values in the task, to render here
    # Checkbox shown if image was uploaded already (date and time also; size)
    # Reference should also be shown

    # TODO: real-time saving of the text as it is typed
    ctx = {'keytermtask': keytermtask,
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
            keyterm = KeyTerm.objects.get(entry_point=entry_point)
        except KeyTerm.DoesNotExist:
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

    # TODO: keytermtask.image_raw = ...

    definition = request.POST.get('keyterm-definition', '')
    if len(definition) > 500:
        keytermtask.definition_text = definition[0:500] + ' ...'

    explanation = request.POST.get('keyterm-explanation', '')
    if len(explainer_text) > 1000:
            keytermtask.explainer_text = definition[0:1000] + ' ...'

    keytermtask.reference_text = 'STILL TO COME'
    keytermtask.save()


    ctx = {'keyterm': entry_point,
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
            keyterm = KeyTerm.objects.get(entry_point=entry_point)
        except KeyTerm.DoesNotExist:
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

    ctx = {'keyterm': entry_point,
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
            keyterm = KeyTerm.objects.get(entry_point=entry_point)
        except KeyTerm.DoesNotExist:
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

    ctx = {'keyterm': entry_point,
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           }
    return render(request, 'keyterms/finalize.html', ctx)

