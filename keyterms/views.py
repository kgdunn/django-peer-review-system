from django.http import HttpResponse
from django.shortcuts import render
from basic.views import entry_point_discovery
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt


# Logging
import logging
logger = logging.getLogger(__name__)

@csrf_exempt
@xframe_options_exempt
def starting_point(request):
    return entry_point_discovery(request)

def draft_keyterm(request, course=None, learner=None, entry_point=None):
    """
    """

    logger.debug(request.POST)
    logger.debug('Draft keyterm [{}] for {}'.format(entry_point, learner))

    keyterm = request.POST.get('custom_keyterm', '')
    keyterm_finalized = False

    # Code here to determine if the user has finalized their keyterm


    if request.POST.get('preview-keyterm', ''):
        return preview_keyterm(request,
                               course=None,
                               learner=None,
                               entry_point=None)

    if request.POST.get('draft-keyterm', ''):
        return draft_keyterm(request,
                             course=None,
                             learner=None,
                             entry_point=None)

    if request.POST.get('submit-keyterm', ''):
        return submit_keyterm(request,
                             course=None,
                             learner=None,
                             entry_point=None)

    if request.POST.get('finalize-keyterm', '') or keyterm_finalized:
        return finalize_keyterm(request,
                             course=None,
                             learner=None,
                             entry_point=None)


    ctx = {'keyterm': 'TCK',
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
          }
    return render(request, 'keyterms/draft.html', ctx)


def preview_keyterm(request, course=None, learner=None, entry_point=None):
    """
    """
    ctx = {'keyterm': 'TCK',
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           }
    return render(request, 'keyterms/preview.html', ctx)


def submit_keyterm(request, course=None, learner=None, entry_point=None):
    """
    """
    ctx = {'keyterm': 'TCK',
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           }
    return render(request, 'keyterms/submit.html', ctx)

def final_keyterms(request, course=None, learner=None, entry_point=None):
    """
    """
    ctx = {'keyterm': 'TCK',
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           }
    return render(request, 'keyterms/finalize.html', ctx)

