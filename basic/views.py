from django.http import HttpResponse
from django.conf import settings

# Our imports
from .models import Person, Course, EntryPoint

# Logging
import logging
logger = logging.getLogger(__name__)

def entry_point_discovery(request):
    """
    All entries from the 3rd party LTI page start here. Bootstrap code to run
    on every request.

    Finds the ``Person`` (creates them if necessary), the ``Course`` and the
    ``EntryPoint``.

    """
    message = ''
    course_ID = request.POST.get('context_id', None) or (settings.DEBUG and \
                                    request.GET.get('context_id', None))
    entry_ID = request.POST.get('resource_link_id', None)or(settings.DEBUG and \
                                    request.GET.get('resource_link_id', None))
    logger.debug('Entering: {0} || {1}'.format(course_ID, entry_ID))

    if (course_ID is None) or (entry_ID is None):
        return HttpResponse(("No course, or entry point were specified. "
                             "Cannot continue. Sorry."))

    try:
        if ' ' in course_ID:
            course_ID = course_ID.replace(' ', '+') # For edX course ID's

        course = Course.objects.get(label=course_ID)
    except Course.DoesNotExist:
        return HttpResponse('Configuration error. Try context_id={}\n'.format(\
                            course_ID))


    # Create the person only if they are visiting from a valid ``course``
    person = get_create_student(request, course)
    try:
        entry_point = EntryPoint.objects.get(LTI_id=entry_ID)
    except EntryPoint.DoesNotExist:
        message = ('Configuration error. Try viewing this page in "Live mode" '
          '; resource_link_id={} or context_id={}').format(entry_ID, course_ID)

    if not(person):
        message = "You are not registered in this course."

    if (message):
        return HttpResponse(message)


    # So, if we get to this point we guarantee a valid ``course``, ``learner``,
    # ``entry_point``. Now we just have to pass off to the entry point function.
    module_name, _, function_name = entry_point.entry_function.split('.')
    module = __import__(module_name + '.views',
                        globals(),
                        locals(),
                        [function_name,],
                        0)
    func = getattr(module, function_name)
    return func(request, course=course, learner=person, entry_point=entry_point)


def recognise_LTI_LMS(request):
    """
    Trys to recognize the LMS from the LTI post.

    Returns one of ('edx', 'brightspace', 'coursera', None). The last option
    is if nothing can be determined.
    """
    if settings.DEBUG:
        try:
            request.POST.update(request.GET) # only on the development server
        except AttributeError:
            request.POST = request.GET

    if request.POST.get('learner_ID', ''):
        return None   # Used for form submissions internally.
    if request.POST.get('resource_link_id', '').find('edx.org')>0:
        return 'edx'
    elif request.POST.get('resource_link_id', '').find('.tudelft.nl') > 0:
        return 'profed'
    elif request.POST.get('ext_d2l_token_digest', None):
        return 'brightspace'
    elif request.POST.get('tool_consumer_instance_guid', '').find('coursera')>1:
        return 'coursera'
    else:
        return None


def get_create_student(request, course):
    """
    Gets or creates the learner from the POST request.
    Also send the ``course``, for the case where the same user email is enrolled
    in two different systems (e.g. Brightspace and edX).

    Must always return something, even if it is ``None``.
    """
    newbie = False
    display_name = user_ID = ''
    LTI_consumer = recognise_LTI_LMS(request)


    if LTI_consumer in ('brightspace', 'edx', 'coursera', 'profed'):
        # We can successfully determine the platform.
        email = request.POST.get('lis_person_contact_email_primary', '')
        display_name = request.POST.get('lis_person_name_full', '')
        if LTI_consumer in ('edx', 'profed'):
            display_name = display_name or \
                                 request.POST.get('lis_person_sourcedid', '')

        user_ID = request.POST.get('user_id', '')
        role = request.POST.get('roles', '')
        # You can also use: request.POST['ext_d2l_role'] in Brightspace
        if 'Instructor' in role:
            role = 'Admin'
        elif 'Student' in role:
            role = 'Learn'

        # Branch here for exceptional case of edX
        if LTI_consumer == 'edx' and 'Administrator' in role:
            role = 'Admin'

        learner_preenrolled = Person.objects.filter(email=email,
                                                    role=role)
        if learner_preenrolled:
            newbie = False
            learner = learner_preenrolled[0]
        else:
            learner, newbie = Person.objects.get_or_create(email=email,
                                                           user_ID=user_ID,
                                                           role=role,
                                                           course=course)



    elif request.POST.get('learner_ID', '') or (settings.DEBUG and \
                                            request.GET.get('learner_ID','')):

        # Used to get the user when they are redirected outside the LMS.
        # and most often, if a form is being filled in, and returned via POST.
        logger.debug('Getting user from POST field.')

        learner_ID = request.POST.get('learner_ID', '') or \
                     request.GET.get('learner_ID','')

        learner = Person.objects.filter(user_ID=learner_ID,
                                        course=course)
        if learner.count() == 1:
            learner = learner[0]
        elif learner.count() > 1:
            logger.error('Multiple enrollments. This should not occur.')
            # Find the learner in this course
            # TODO still. This is the case where the same email address is used
            #             in more than 1 platform (e.g. Brightspace and edX)
            return learner[0]
        else:
            learner = None
    else:
        return None

    if newbie:
        learner.display_name = display_name
        learner.save()
        logger.info('Created/saved new learner: %s' % learner.display_name)

    if learner:
        # Augments the learner with extra fields that might not have been there
        if learner.user_ID == '':
            logger.info('Augumented user_ID on %s' % learner.email)
            learner.user_ID = user_ID
            learner.display_name = display_name
            learner.save()

        if learner.course is None:
            learner.course = course
            learner.save()

    return learner