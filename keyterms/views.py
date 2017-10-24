from django.http import HttpResponse
from grades.views import push_grade as push_to_gradebook


# Logging
import logging
logger = logging.getLogger(__name__)


def test(request, course=None, learner=None, entry_point=None):
    """
    Start the interactive tool here:
    0. Can we even run this entry_point?
    """
    # Step 1:
    if not push_to_gradebook(learner, .77, entry_point, testing=False):
        return HttpResponse('Please create a GradeItem attached to this Entry')
    else:
        return HttpResponse(content='Grade pushed')

