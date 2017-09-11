from django.http import HttpResponse
from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.template.context_processors import csrf
from django.template import loader
from django.views.decorators.clickjacking import xframe_options_exempt
from django.conf import settings as DJANGO_SETTINGS



# Our imports
from .models import Person, Course, EntryPoint, Token
from utils import generate_random_token, send_email

# Logging
import logging
logger = logging.getLogger(__name__)

# Debugging
import wingdbstub


@csrf_exempt
@xframe_options_exempt
def entry_point_discovery(request, course_code=None, entry_code=None):
    """
    All entries from the 3rd party LTI page start here. Bootstrap code to run
    on every request.

    Finds the ``Person`` (creates them if necessary), the ``Course`` and the
    ``EntryPoint``.

    """
    message = ''
    course_ID = request.POST.get('context_id', '') or (settings.DEBUG and \
                                    request.GET.get('context_id', ''))
    entry_ID = request.POST.get('resource_link_id', None)or(settings.DEBUG and \
                                    request.GET.get('resource_link_id', None))

    if course_ID or entry_ID:
        logger.debug('POST entry: {0} || {1}'.format(course_ID, entry_ID))
    else:
        logger.debug('GET  entry: {0} || {1}'.format(course_code, entry_code))

    # Required for web-based access
    course_ID = course_ID or course_code
    entry_ID = entry_ID or entry_code

    if not(course_ID) or not(entry_ID):
        return HttpResponse(("Homepage of the interactive peer review tool."))

    course = None
    try:
        if ' ' in course_ID:
            course_ID = course_ID.replace(' ', '+') # For edX course ID's

        course = Course.objects.get(label=course_ID)
    except Course.DoesNotExist:
        return HttpResponse('Configuration error. Try context_id={}\n'.format(\
                            course_ID))


    # Create the person only if they are visiting from a valid ``course``
    person, message = get_create_student(request, course)
    entry_point = None
    try:
        entry_point = EntryPoint.objects.get(LTI_id=entry_ID,
                                             course=course)
    except (EntryPoint.DoesNotExist, EntryPoint.MultipleObjectsReturned):
        message = ('No entry point; or duplicate entry points. "Live mode"?'
          ' resource_link_id={} or context_id={}').format(entry_ID, course_ID)

    if not(person):
        #message = "You are not registered in this course."
        ctx = {'course': course,
               'entry_point': entry_point}
        ctx.update(csrf(request))
        return render(request, 'basic/sign-in.html')

    if (message):
        return HttpResponse(message)

    if request.POST.get('lis_result_sourcedid', ''):
        # Update only if needed.
        person.last_lis = request.POST.get('lis_result_sourcedid', '')
        person.save()


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
    elif request.POST.get('emailaddress', ''):
        return 'website'
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
    message = False

    if LTI_consumer in ('brightspace', 'edx', 'coursera', 'profed', 'website'):
        # We can successfully determine the platform.

        email = request.POST.get('lis_person_contact_email_primary', '')
        email = email or request.POST.get('emailaddress', '') # for 'website'
        display_name = request.POST.get('lis_person_name_full', '')
        if LTI_consumer in ('edx', 'profed'):
            display_name = display_name or \
                                 request.POST.get('lis_person_sourcedid', '')

        user_ID = request.POST.get('user_id', '')
        role = request.POST.get('roles', 'Learn') # Default: as student
        # You can also use: request.POST['ext_d2l_role'] in Brightspace
        if 'Instructor' in role:
            role = 'Admin'
        elif 'Student' in role:
            role = 'Learn'

        # Branch here for exceptional case of edX
        if LTI_consumer == 'edx' and 'Administrator' in role:
            role = 'Admin'

        user_ID = '{}-{}'.format(user_ID, role.lower())

        existing_learner = Person.objects.filter(user_ID=user_ID, role=role)
        if existing_learner:
            newbie = False
            learner = existing_learner[0]
        else:
            learner, newbie = Person.objects.get_or_create(email=email,
                                                           user_ID=user_ID,
                                                           role=role,
                                                           course=course)

        if LTI_consumer in ('website',):
            learner.user_ID = 'Stu-{}'.format(learner.pk)
            learner.save()
            message = handle_website_sign_in(learner, newbie)


    elif request.POST.get('learner_ID', '') or (settings.DEBUG and \
                                            request.GET.get('learner_ID','')):

        # Used to get the user when they are redirected outside the LMS.
        # and most often, if a form is being filled in, and returned via POST.
        learner_ID = request.POST.get('learner_ID', '') or \
                     request.GET.get('learner_ID','')

        learner = Person.objects.filter(user_ID=learner_ID,
                                        course=course)
        if learner.count() == 1:
            learner = learner[0]
        elif learner.count() > 1:
            logger.error('Multiple enrollments [{0}]. This should not occur.'\
                         .format(learner))
            # Find the learner in this course
            # TODO still. This is the case where the same email address is used
            #             in more than 1 platform (e.g. Brightspace and edX)
            return learner[0], message
        else:
            learner = None
    else:
        return None, message

    if newbie:
        learner.display_name = display_name
        learner.save()
        logger.info('Created/saved new learner: %s' % learner.display_name)

    if learner:
        # Augments the learner with extra fields that might not have been there
        if learner.user_ID == '':
            #logger.info('Augumented user_ID on %s' % learner.email)
            learner.user_ID = user_ID
            learner.display_name = display_name
            learner.save()

        if learner.course is None:
            learner.course = course
            learner.save()

    return learner, message


def handle_website_sign_in(learner, is_newbie):

    if is_newbie:

        # Create totally new user. At this point we are sure the user
        #          has never been validated on our site before.
        #          But the email address they provided might still be faulty.

        token = create_token_send_email_check_success(learner)
        token.save()
        return ("An account has been created for you, but must "
                "be actived. Please check your email and "
                "click on the link that we emailed you.")

    else:
        # Not a newbie
        token = create_token_send_email_check_success(learner)
        token.save()
        return ("<i>Welcome back!</i> Please check your email, "
                "and click on the link that we emailed you."))


def create_token_send_email_check_success(person):
    """ Used during signing in a new user, or an existing user. A token to
    is created, and an email is sent.
    If the email succeeds, then we return with success, else, we indicate
    failure to the calling function.
    """
    TOKEN_LENGTH = 9

    # Create a token for the new user
    hash_value = generate_random_token(TOKEN_LENGTH)

    # Send them an email
    send_suitable_email(person, hash_value)
    token = Token(person=person, hash_value=hash_value)

    # All finished; return what we have (unsaved ``token`` instance)
    return token

def send_suitable_email(person, hash_val):
    """ Sends a validation email, and logs the email message. """

    if person.is_validated:
        sign_in_URI = '{0}/sign-in/{1}'.format(DJANGO_SETTINGS.BASE_URL,
                                        hash_val)
        ctx_dict = {'sign_in_URI': sign_in_URI}
        message = loader.render_to_string('basic/email_sign_in_code.txt',
                                           ctx_dict)
        subject = "Unique code to sign into the Interactive Peer Review"
        to_address_list = [person.email.strip('\n'), ]

    else:
        # New users / unvalidated user
        check_URI = '{0}/validate/{1}'.format(DJANGO_SETTINGS.BASE_URL,
                                             hash_val)
        ctx_dict = {'validation_URI': check_URI}
        message = loader.render_to_string('basic/email_new_user_to_validate.txt',
                                          ctx_dict)

        subject = "Confirm your email address for the Interactive Peer Review"
        to_address_list = [person.email.strip('\n'), ]


    # Use regular Python code to send the email in HTML format.
    message = message.replace('\n','\n<br>')
    logger.debug('EMAIL {}:: {} :: {}'.format(to_address_list,
                                              subject,
                                              message))
    return send_email(to_address_list, subject, message)

