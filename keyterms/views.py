from django.http import HttpResponse
from django.shortcuts import render
from basic.views import entry_point_discovery
#from django.views.decorators.csrf import csrf_exempt#
#from django.views.decorators.clickjacking import xframe_options_exempt


# Logging
import logging
logger = logging.getLogger(__name__)

#@csrf_exempt
#@xframe_options_exempt
#def starting_point(request):
    #return entry_point_discovery(request)

def start_keyterm(request, course=None, learner=None, entry_point=None):
    """
    """
    logger.debug(request.POST)

    keyterm = request.POST.get('custom_keyterm', '')
    keyterm_finalized = False

    # TODO: Code here to determine if the user has finalized their keyterm

    if request.POST.get('preview-keyterm', ''):
        return preview_keyterm(request, course, learner, entry_point, keyterm)

    if request.POST.get('draft-keyterm', ''):
        return draft_keyterm(request, course, learner, entry_point, keyterm)

    if request.POST.get('submit-keyterm', ''):
        return submit_keyterm(request, course, learner, entry_point, keyterm)

    if request.POST.get('finalize-keyterm', '') or keyterm_finalized:
        return finalize_keyterm(request, course, learner, entry_point, keyterm)

    # If nothing else (usually the first time we start, we start with drafting)
    return draft_keyterm(request, course, learner, entry_point, keyterm)


def draft_keyterm(request, course=None, learner=None, entry_point=None,
                  keyterm=None):
    """
    """
    ctx = {'keyterm': keyterm,
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           }
    return render(request, 'keyterms/draft.html', ctx)


def preview_keyterm(request, course=None, learner=None, entry_point=None,
                    keyterm=None):
    """
    """

    ctx = {'keyterm': keyterm,
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           }
    return render(request, 'keyterms/preview.html', ctx)


def submit_keyterm(request, course=None, learner=None, entry_point=None,
                   keyterm=None):
    """
    """
    ctx = {'keyterm': keyterm,
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           }
    return render(request, 'keyterms/submit.html', ctx)

def finalize_keyterm(request, course=None, learner=None, entry_point=None,
                     keyterm=None):
    """
    """
    ctx = {'keyterm': keyterm,
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           }
    return render(request, 'keyterms/finalize.html', ctx)

