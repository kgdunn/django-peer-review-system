"""
To push grades to Brightspace:

* need the ``push_grades.php`` function
* set up Brightspace with a key and secret, and set these also in ``settings.py``
  or in ``local_settings.py`` as

  LTI_KEY = 'key'
  LTI_SECRET = 'secret'

"""
from django.shortcuts import render
from django.http import HttpResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt


# Our imports
from .models import GradeBook, GradeCategory, GradeItem, LearnerGrade
from basic.models import Person, Course

# Python imports
import io
import os
import csv
import six
import decimal
import datetime
import subprocess
from collections import defaultdict, namedtuple

# Logging
import logging
logger = logging.getLogger(__name__)

@csrf_exempt
@xframe_options_exempt
def display_grade(request, user_ID, course):
    """
    Shows the grades for a student
    """
    course = Course.objects.get(label=course)
    gradebook = course.gradebook_set.all()[0]
    learner = Person.objects.filter(user_ID=user_ID)[0]
    logger.debug('Displaying grade for {0}'.format(learner))
    grades, total_grade = get_grade_summary(learner, gradebook)
    ctx = {'course': course,
           'gradebook': gradebook,
           'grades': grades,
           'total_grade': total_grade,
           'learner': learner,
           }
    return render(request, 'grades/learner_grades.html', ctx)


def get_grade_summary(learner, gradebook):
    """
    Get the complete grade breakdown summary for a learner in a given
    ``gradebook``.

    We also return, as a second output, the grade average (total grade obtained
    so far in the course)
    """
    categories = GradeCategory.objects.filter(gradebook=gradebook)\
        .order_by('order')

    """
    How will we represent gradebook to a student? Data structure:

    [(string,decimal,{}), (string,decimal,{}), (string,decimal,{})]

    1. Outer list: holds, in order, the categories

    2. The innner tuple: holds 3 disparate elements: string, decimal, dictionary
       2a. The catogory name
       2b. The category weights (the sum of all weights should be 100%)
       2c. The dictionary* of item(s) within that category.

    3. The inner dictionaries*:
       3a. Key ('5.02', for example): indicates category 5, item 2
       3b. Value: Will be an instance of "LearnerGrade" for that item.

    * The dictionaries are sorted, just before returning and returned with:
        sorted(dict.items())  if PY3,    or    sorted(dict.iteritems()) if PY2


    To calculate the student average:
    * iterate over all the items in dictionary to calculate the score for category
    * iterate over all categories in  list, with the weight, to get overall average
    """
    grades = []
    total_grade = decimal.Decimal(0.0)
    for gcat in categories:
        items = gcat.gradeitem_set.all().order_by('order')
        if items.count() == 0:
            # No items?
            continue
        elif items.count() == 1:
            weight = max(gcat.weight, items[0].weight)
            grade = LearnerGrade.objects.filter(learner=learner, gitem=items[0])
            if grade.count() == 0:
                print('How now?')
                pass
            else:
                grades.append((gcat.display_name,
                                weight*100,
                                [('0', grade[0])]
                             ))
                if grade[0].value:
                    total_grade += weight * grade[0].value
            continue

        items_dict = {}
        item_grades = []
        item_weights = []
        category_score = decimal.Decimal(0.0)
        if gcat.spread_evenly:
            weight = decimal.Decimal(1/(items.count()+0.0))
            item_weights = [weight]*items.count()

        for idx, item in enumerate(items):
            grade = LearnerGrade.objects.filter(learner=learner, gitem=item)
            if grade.count() == 0:
                # How do we get to this point?
                item_grades.append(0.0)
                pass
            else:
                key = gcat.order + item.order/1000.0
                items_dict[key] = grade[0]
                item_weights[idx] = max(item_weights[idx], item.weight)
                if grade[0].value:
                    category_score += item_weights[idx] * grade[0].value

        # After processing all items
        total_grade += gcat.weight * category_score
        LearnerGrade_nt = namedtuple('gradeitem', ['value', 'max_score',
                                                   'not_graded_yet' ])
        items_dict[-10000] = LearnerGrade_nt(value=category_score,
                                             max_score=100,
                                             not_graded_yet=False)
        if six.PY2:
            items_dict = sorted(items_dict.iteritems())

        elif six.PY3:
            items_dict = sorted(items_dict.items())

        grades.append((gcat.display_name, gcat.weight*100, items_dict))

    return grades, total_grade

def grade_landing_page(request, course=None, learner=None, entry_point=None):
    """
    Displays the grades to the student here.
    """
    gradebook = GradeBook.objects.get(course=course)
    if learner.role == 'Admin':
        all_lgrades = LearnerGrade.objects.filter(\
                                          gitem__category__gradebook=gradebook)
        students = list(set([lgrade.learner for lgrade in all_lgrades]))

        ctx = {'learner': learner,
               'course': course,
               'entry_point': entry_point,
               'all_learners': students
               }

        return render(request, 'grades/admin_grades.html', ctx)

    else:
        return display_grade(request, learner.user_ID, course.label)



#@csrf_exempt
#@xframe_options_exempt
#def import_edx_gradebook(request):
    #"""
    #Allows the instructor to import a grades list from edX.

    #Improvements:
    #* create a "Person" profile for students that in the CSV file, but not yet
      #in the DB.
    #"""

    #logger.debug("Importing grades:")
    #SKIP_FIELDS = [
        #"Student ID",
        #"Email",
        #"Username",
        #"Grade",
        #"Enrollment Track",
        #"Verification Status",
        #"Certificate Eligible",
        #"Certificate Delivered",
        #"Certificate Type",
        #"(Avg)",   # <--- special case: skip calculated columns
    #]

    #if request.method != 'POST':
        #return HttpResponse(('Grades cannot be uploaded directly. Please upload'
                             #' the grades via edX.'))

    #if request.method == 'POST' and request.FILES.get('file_upload', None):
        #pass
    #else:
        #return HttpResponse('A file was not uploaded, or a problem occurred.')

    #from review.views import starting_point
    #person_or_error, course, pr = starting_point(request)

    #if not(isinstance(person_or_error, Person)):
        #return person_or_error      # Error path if student does not exist

    #learner = person_or_error
    #gradebook = GradeBook.objects.get(course=course)
    #if six.PY2:
        #uploaded_file = request.FILES.get('file_upload').readlines()
        #io_string = uploaded_file
    #if six.PY3:
        #uploaded_file = request.FILES.get('file_upload').read().decode('utf-8')
        #io_string = io.StringIO(uploaded_file)
    #logger.debug(io_string)

    #out = ''
    #reader = csv.reader(io_string, delimiter=',')
    #columns = defaultdict(int)
    #for row in reader:
        #if reader.line_num == 1:
            #order = 0
            #for idx, col in enumerate(row):
                #invalid = False
                #for skip in SKIP_FIELDS:
                    #if col.endswith(skip):
                        #invalid = True
                #if invalid:
                    #order += 1
                    #continue
                #else:
                    #columns[order] = col
                    #order += 1


                #cat, created_cat = GradeCategory.objects.get_or_create(
                                                    #gradebook=gradebook,
                                                    #display_name=col,
                                                    #defaults={'order': order,
                                                              #'max_score': 1,
                                                              #'weight':0.0,}
                                                    #)

                #item, created_item = GradeItem.objects.get_or_create(
                                                #display_name=col,
                                                #category__gradebook=gradebook,
                                                #defaults={'order': order,
                                                          #'max_score': 1,
                                                          #'weight':0.0,}
                                                #)
                #if created_cat and created_item:
                    #item.category = cat
                    #item.save()

            ## After processing the first row
            #continue

        #for idx, col in enumerate(row):
            #edX_id = row[0]
            #email = row[1]
            #display_name = row[2]
            #if Person.objects.filter(email=email, role='Learn').count():
                #learner = Person.objects.filter(email=email, role='Learn')[0]
            #else:
                #continue
                ##new_student, _ = Person.objects.get_or_create(email=email,
                                                           ##role='Learn',
                                                           ##display_name=row[2])

            #if idx not in columns.keys():
                #continue

            #item_name = columns[idx]
            #gitem = GradeItem.objects.get(display_name=item_name,
                                          #category__gradebook=gradebook)
            #prior = LearnerGrade.objects.filter(gitem=gitem, learner=learner)
            #if prior.count():
                #item = prior[0]
            #else:
                #item = LearnerGrade(gitem=gitem, learner=learner)


            #if col in ('Not Attempted', 'Not Available'):
                #item.not_graded_yet = True
                #item.value = None
            #else:
                #item.not_graded_yet = False
                #item.value = float(col)*100

            #item.save()

    #gradebook.last_updated = datetime.datetime.utcnow()
    #gradebook.save()


    #return HttpResponse('out:' + out)

def push_grades_to_platform(sourcedid, grade_push_url, grade_value):
    """
    Based on: https://community.brightspace.com/devcop/blog/ ...
                             so_you_want_to_extend_your_lms__part_1_lti_primer

    1. Requires the ``lis_result_sourcedid`` from request.POST, as input
       variable ``sourcedid``.
       sourcedid = request.POST.get('lis_result_sourcedid', '')

    2. Requires the ``lis_outcome_service_url`` from request.POST, as input
       variable ``grade_push_url``.
       grade_push_url = request.POST.get('lis_outcome_service_url', '')

    3. The ``grade``: a value between 0.0 and 1.0

    Will return "True" if the grade was successfully set; else it returns None.
    """
    try:
        grade = float(grade_value)
    except ValueError:
        logger.debug('Could not create a floating point grade: ' + grade)
        return None

    # Call the PHP to do the work. Supply the required command line arguments
    calling_args = ("--sourcedid {0} --grade {1} --oauth_consumer_key={2} "
                    "--oauth_consumer_secret={3} " # space is important here
                    "--grade_push_url={4}").format(sourcedid,
                                                   grade,
                                                   settings.LTI_KEY,
                                                   settings.LTI_SECRET,
                                                   grade_push_url)
    php_script = settings.BASE_DIR_LOCAL + os.sep + 'grades/push_grades.php'
    proc = subprocess.Popen("php {0} {1}".format(php_script, calling_args),
                            shell=True,
                            stdout=subprocess.PIPE)
    script_response = proc.stdout.read()
    logger.debug('Grade pushed [{0}]{{{1}}}: {2}'.format(sourcedid,
                                                         grade,
                                                         script_response))

    if script_response.decode('utf-8').find('Grade was set') >= 0:
        return True
    else:
        return False


def push_grade(grade_push_url, learner, grade_value, entry_point, testing=False):
    """
    Pushes the ``grade_value`` (a number between 0 and 100) for ``learner``
    at the given ``entry_point`` to the platform.

    This is the wrapper function, and should be the way to get the work done.

    The function we call internally needs a dictionary, ``ctx`` with a key
    ``sourcedid`` which you get from Django/POST request:

    >>> sourcedid = request.POST.get('lis_result_sourcedid', '')
    """
    gradeitem = GradeItem.objects.filter(entry_point=entry_point)
    if gradeitem.count():
        gitem = gradeitem[0]
    else:
        gitem = GradeItem(category=None,
                          entry_point=entry_point,
                          display_name='Please update: ' + str(entry_point))
        gitem.save()

    grade, _ = LearnerGrade.objects.get_or_create(gitem=gitem,
                                                  learner=learner)

    grade.value = grade_value
    grade.save()

    grade_to_push = grade_value / 100.0

    if not(testing):
        return push_grades_to_platform(learner.last_lis,
                                       grade_push_url,
                                       grade_to_push)
    else:
        return True



