from django.http import HttpResponse

# Logging
import logging
logger = logging.getLogger(__name__)


def starting_point(request, course=None, learner=None, entry_point=None):
    """
    Start the interactive tool here:
    0. Can we even run this entry_point?
    """
    # Step 1:
    return HttpResponse(content='Start here')


def draft_keyterm(request, course=None, learner=None, entry_point=None):
    """
    """
    return HttpResponse(content='Draft')


def preview_keyterm(request, course=None, learner=None, entry_point=None):
    """
    """
    return HttpResponse(content='Preview')


def submit_keyterm(request, course=None, learner=None, entry_point=None):
    """
    """
    return HttpResponse(content='Submit')


def final_keyterms(request, course=None, learner=None, entry_point=None):
    """
    """
    return HttpResponse(content='View all')

