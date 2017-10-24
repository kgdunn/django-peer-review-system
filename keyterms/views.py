from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt

# Logging
import logging
logger = logging.getLogger(__name__)

# Debugging
import wingdbstub

#@csrf_exempt
#@xframe_options_exempt
def test(request, course=None, learner=None, entry_point=None):
    """
    Start the interactive tool here:
    0. Can we even run this entry_point?
    """
    return HttpResponse(content='Hi there')

