from django.http import HttpResponse
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

