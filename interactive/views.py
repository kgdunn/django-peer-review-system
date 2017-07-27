#from django.shortcuts import render
#from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse

def starting_point(request, course=None, learner=None, entry_point=None):
    """
    Start the interactive tool here.
    """
    return HttpResponse('Welcome {0}'.format(learner))