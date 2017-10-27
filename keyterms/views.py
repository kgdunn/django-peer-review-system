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
    logger.debug(request.POST)

    keyterm_finalized = False

    # TODO: Code here to determine if the user has finalized their keyterm

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
    """
    keyterm = entry_point.full_URL



    #prior_tasks = learner.keytermtask.filter(entry_point=entry_point)
    #if prior_tasks.count():
        #keytermtask = prior_tasks[0]
    #else:
        #settings = KeyTermSettings()
        #settings.save()



    #KeyTermTask.objects.get_or_create(learner=learner, entry_point=entry_point,
                                      #keyterm=keyterm)

    #KeyTermTask.objects.get_or_create(learner=learner, entry_point=entry_point,
                                      #keyterm=keyterm)



    #settings = models.ForeignKey(KeyTermSettings)



    ctx = {'keyterm': keyterm,
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
    definition = request.POST.get('keyterm-definition', '')
    explanation = request.POST.get('keyterm-explanation', '')

    ctx = {'keyterm': entry_point.full_URL,
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           'grade_push_url': request.POST.get('lis_outcome_service_url', '')
           }
    return render(request, 'keyterms/preview.html', ctx)


def submit_keyterm(request, course=None, learner=None, entry_point=None):
    """
    """
    ctx = {'keyterm': entry_point.full_URL,
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           'grade_push_url': request.POST.get('lis_outcome_service_url', '')
           }
    return render(request, 'keyterms/submit.html', ctx)

def finalize_keyterm(request, course=None, learner=None, entry_point=None):
    """
    """
    grade_push_url=request.POST.get('lis_outcome_service_url', '')
    response = push_grade(learner=learner,
                          grade_value=100,
                          entry_point=entry_point,
                          grade_push_url=grade_push_url,
                          testing=False)
    logger.debug('Grade for {0} at [{1}]; response: {2}'.format(learner,
                                                                grade_push_url,
                                                                response))

    ctx = {'keyterm': entry_point.full_URL,
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           }
    return render(request, 'keyterms/finalize.html', ctx)

