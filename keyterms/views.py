from django.http import HttpResponse
from django.shortcuts import render
from basic.views import entry_point_discovery

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
    ctx = {'keyterm': entry_point.full_URL,
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           }
    return render(request, 'keyterms/draft.html', ctx)


def preview_keyterm(request, course=None, learner=None, entry_point=None):
    """
    """

    ctx = {'keyterm': entry_point.full_URL,
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           }
    return render(request, 'keyterms/preview.html', ctx)


def submit_keyterm(request, course=None, learner=None, entry_point=None):
    """
    """
    ctx = {'keyterm': entry_point.full_URL,
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           }
    return render(request, 'keyterms/submit.html', ctx)

def finalize_keyterm(request, course=None, learner=None, entry_point=None):
    """
    """
    ctx = {'keyterm': entry_point.full_URL,
           'course': course,
           'entry_point': entry_point,
           'learner': learner,
           }
    return render(request, 'keyterms/finalize.html', ctx)

