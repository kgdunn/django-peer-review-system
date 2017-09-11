from django.http import HttpResponse
from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.template.context_processors import csrf
from django.views.decorators.clickjacking import xframe_options_exempt
from django.conf import settings as DJANGO_SETTINGS

# Our imports
from .models import Person, Course, EntryPoint
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
        entry_point = EntryPoint.objects.get(LTI_id=entry_ID,
                                             course=course)
    except (EntryPoint.DoesNotExist, EntryPoint.MultipleObjectsReturned):
        message = ('No entry point; or duplicate entry points. "Live mode"?'
          ' resource_link_id={} or context_id={}').format(entry_ID, course_ID)

    if not(person):
        #message = "You are not registered in this course."
        ctx = {'enabled': False}
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

def popup_sign_in(request):
    """POST-only sign-in via the website. """

    # NOTE: this uses the fact that the URLs are /system/abc
    # We aim to find the system so we can redirect the person clicking on
    # an email.
    #referrer = request.META.get('HTTP_REFERER', '/').split('/')
    #try:
    #    system_slug = referrer[referrer.index('system')+1]
    #    system = models.System.objects.get(is_active=True, slug=system_slug)
    #except (ValueError, IndexError, models.System.DoesNotExist):
    #    system_slug=''
    #    system = None

    if 'emailaddress' not in request.POST:
        return HttpResponse("Unauthorized access", status=401)

    # Process the sign-in
    # 1. Check if email address is valid based on a regular expression check.
    try:
        email = request.POST.get('emailaddress', '').strip()
        validate_email(email)
    except ValidationError:
        return HttpResponse("Invalid email address. Try again please.",
                            status=406)

    # 2. Is the user signed in already? Return back (essentially do nothing).
    # TODO: handle this case still. For now, just go through with the email
    #       again (but this is prone to abuse). Why go through? For the case
    #       when a user signs in, now the token is used. But if they reuse that
    #       token to sign in, but the session here is still active, they can
    #       potentially not sign in, until they clear their cookies.
    #if request.session.get('person_id', False):
    #    return HttpResponse("You are already signed in.", status=200)

    # 3A: a brand new user, or
    # 3B: a returning user that has cleared cookies/not been present for a while
    try:
        # Testing for 3A or 3B
        person = Person.objects.get(email=email)

        # Must be case 3B. If prior failure, then it is case 3A (see below).
        token = create_token_send_email_check_success(person)
        if token:
            token.save()
            return HttpResponse(("<i>Welcome back!</i> Please check your email,"
                                 " and click on the link that we emailed you."),
                                status=200)
        else:
            return HttpResponse(("An email could not be sent to you. Please "
                                 "ensure your email address is correct."),
                                status=404)

    except Person.DoesNotExist:
        # Case 3A: Create totally new user. At this point we are sure the user
        #          has never been validated on our site before.
        #          But the email address they provided might still be faulty.
        person = models.Person(is_validated=False,
                               display_name='Anonymous',
                               email=email)
        person.save()
        person.display_name = person.display_name + str(person.id)

        token = create_token_send_email_check_success(person)
        if token:
            person.save()
            token.person = person  # must overwrite the prior "unsaved" person
            token.save()
            return HttpResponse(("An account has been created for you, but must"
                                 " be actived. Please check your email and "
                                 "click on the link that we emailed you."),
                                status=200)
        else:
            # ``token`` will automatically be forgotten when this function
            # returns here. Perfect!
            person.delete()
            return HttpResponse(("An email could NOT be sent to you. Please "
                                 "ensure your email address is valid."), status=404)

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
    failed = send_suitable_email(person, hash_value)

    token = False # SMTPlib cannot send an email
    if not(failed):
        token = models.Token(person=person,
                             hash_value=hash_value,
                             experiment=None,
                             next_URI=strip(DJANGO_SETTINGS.WEBSITE_BASE_URI))

    # All finished; return what we have
    return token

def send_suitable_email(person, hash_val):
    """ Sends a validation email, and logs the email message. """

    if person.is_validated:
        sign_in_URI = '{0}/sign-in/{1}'.format(DJANGO_SETTINGS.WEBSITE_BASE_URI,
                                        hash_val)
        ctx_dict = {'sign_in_URI': sign_in_URI}
        message = render_to_string('rsm/email_sign_in_code.txt',
                                   ctx_dict)
        subject = "Unique code to sign into the Interactive Peer Review"
        to_address_list = [person.email.strip('\n'), ]

    else:
        # New users / unvalidated user
        check_URI = '{0}/validate/{1}'.format(DJANGO_SETTINGS.WEBSITE_BASE_URI,
                                             hash_val)
        ctx_dict = {'validation_URI': check_URI}
        message = render_to_string('rsm/email_new_user_to_validate.txt',
                                   ctx_dict)

        subject = "Confirm your email address for the Interactive Peer Review"
        to_address_list = [person.email.strip('\n'), ]


    # Use regular Python code to send the email in HTML format.
    message = message.replace('\n','\n<br>')
    return send_email(to_address_list, subject, message)



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
        #email = request.POST.get('lis_person_contact_email_primary', '')
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

        user_ID = '{}-{}'.format(user_ID, role.lower())

        existing_learner = Person.objects.filter(user_ID=user_ID, role=role)
        if existing_learner:
            newbie = False
            learner = existing_learner[0]
        else:
            # Don't store user's email address: we don't need it
            learner, newbie = Person.objects.get_or_create(#email=email,
                                                           user_ID=user_ID,
                                                           role=role,
                                                           course=course)


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
            #logger.info('Augumented user_ID on %s' % learner.email)
            learner.user_ID = user_ID
            learner.display_name = display_name
            learner.save()

        if learner.course is None:
            learner.course = course
            learner.save()

    return learner
