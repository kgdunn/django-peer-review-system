from django.http import HttpResponse, HttpResponseRedirect
from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.template.context_processors import csrf
from django.template import loader
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_exempt
from django.conf import settings as DJANGO_SETTINGS


# Our imports
from .models import Person, Course, EntryPoint, Token
from utils import generate_random_token, send_email

# Logging
import logging
logger = logging.getLogger(__name__)

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


    info = get_course_ep_info(request)
    logger.debug('INFO: {}'.format(info))
    if not(course_code) and isinstance(info['course'], Course) and\
       not(course_ID) and isinstance(info['course'], Course):
        course_ID = info['course'].label

    if not(entry_code) and isinstance(info['entry_point'], EntryPoint) and\
        not(entry_ID) and isinstance(info['entry_point'], EntryPoint):

        if info['entry_point']:
            entry_ID = info['entry_point'].LTI_id

    if course_ID or entry_ID:
        logger.debug('POST entry: {0} || {1}'.format(course_ID, entry_ID))
    else:
        logger.debug('GET  entry: {0} || {1}'.format(course_code, entry_code))


    # Required for web-based access
    course_ID = course_ID or course_code
    entry_ID = entry_ID or entry_code

    if not(course_ID) or not(entry_ID):
        return HttpResponse(("Homepage of the peer interaction tool. "
                             "Please access this site from your learning "
                             "platform, for example: Brightspace."))

    course = None
    try:
        if ' ' in course_ID:
            course_ID = course_ID.replace(' ', '+') # For edX course ID's

        course = Course.objects.get(label=course_ID)
        request.session['course'] = course.id
    except Course.DoesNotExist:
        return HttpResponse('Configuration error. Try context_id={}\n'.format(\
                            course_ID))

    entry_point = None
    try:
        entry_point = EntryPoint.objects.get(LTI_id=entry_ID, course=course)
        request.session['entry_point'] = entry_point.id
    except (EntryPoint.DoesNotExist, EntryPoint.MultipleObjectsReturned):
        message = ('No entry point; or duplicate entry points. "Live mode"?'
          ' resource_link_id={} or context_id={}').format(entry_ID, course_ID)

    # Create the person only if they are visiting from a valid ``course`` and
    # valid ``entry_point``
    person, message = get_create_student(request, course, entry_point)

    if not(person):
        #message = "You are not registered in this course."
        ctx = {'course': course,
               'entry_point': entry_point}
        ctx.update(csrf(request))
        return render(request, 'basic/sign-in.html', ctx)

    if (message):
        return HttpResponse(message)

    # Finally, send the user back for another round, now that we have
    # used the session to store the information.
    if  (course_code is not None) or (entry_code is not None) or \
                                                         (entry_point is None):
        return HttpResponseRedirect('/')

    logger.debug('Person is {}, with id={}'.format(person, person.id))

    if request.POST.get('lis_result_sourcedid', ''):
        # Update only if needed.
        person.last_lis = request.POST.get('lis_result_sourcedid', '')
        person.last_grade_push_url = request.POST.get('lis_outcome_service_url',
                                                      '')
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
        # You can put all sorts of filters on the email addresses here
        try:
            validate_email(request.POST.get('emailaddress', ''))
        except ValidationError:
            return None

        if request.POST.get('emailaddress', '').endswith('tudelft.nl'):
            return 'website'
        else:
            return None
    else:
        return None


def get_create_student(request, course, entry_point):
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

        # Force it to lower case, since we store and use this almost as a
        # primary key
        email = email.lower()
        display_name = request.POST.get('lis_person_name_full', '')
        if LTI_consumer in ('edx', 'profed'):
            display_name = display_name or \
                                 request.POST.get('lis_person_sourcedid', '')


        user_ID = request.POST.get('user_id', '')
        role = request.POST.get('roles', 'Learn') # Default: as student
        # You can also use: request.POST['ext_d2l_role'] in Brightspace
        if 'Instructor' in role:
            role = 'Admin'
        elif 'Administrator' in role:
            role = 'Admin'
        elif 'Student' in role:
            role = 'Learn'

        # Branch here for exceptional case of edX
        if LTI_consumer in ('edx', 'profed') and 'Administrator' in role:
            role = 'Admin'

        user_ID = '{}-{}'.format(user_ID, role.lower())

        # Previously got learners by their user_ID (that works well for LTI),
        # but not on a website. So now we have filtered here on email instead.
        # Use the ``display_name`` as a way to detect LTI
        if display_name == '':
            existing_learner = Person.objects.filter(email=email)
                            #, role=role) <-- keep for LTI, but not for web
        else:
            existing_learner = Person.objects.filter(email=email, role=role)

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
            message = handle_website_sign_in(learner, newbie, request)


    elif request.POST.get('learner_ID', '') or (settings.DEBUG and \
                                            request.GET.get('learner_ID','')):

        # Used to get the user when they are redirected outside the LMS.
        # and most often, if a form is being filled in, and returned via POST.
        learner_ID = request.POST.get('learner_ID', '') or \
                     request.GET.get('learner_ID','')

        learner = Person.objects.filter(user_ID=learner_ID,)
                                        #course=course) <-- not needed if using user_ID
        if learner.count() == 1:
            learner = learner[0]
        elif learner.count() > 1:
            logger.error('Multiple enrollments [{0}]. This should not occur.'\
                         .format(learner))
            # Find the learner in this course
            # TODO still. This is the case where the same email address is used
            #             in more than 1 platform (e.g. Brightspace and edX)
            learner = learner[0]
        else:
            learner = None
        #end

    elif request.session.get('person_id', ''):
        learners = Person.objects.filter(id=request.session.get('person_id'),)
                                        #course=course) <- is this needed?
        learner = None
        if learners.count() == 1:
            learner = learners[0]
        elif learners.count() > 1:
            logger.error(('Website version: multiple enrollments [{0}]. '
                          'This should not occur.').format(learner))
            # TODO still. This is the case where the same email address is used
            #             in more than 1 platform (e.g. Brightspace and edX)
            learner = learners[0]

        if learner and not(learner.is_validated):
            # Even if we have a learner, return None if they are not validated
            learner = None

    else:
        return None, message

    if newbie:
        learner.display_name = display_name
        learner.save()
        logger.info('Created/saved new learner: {}'.format(learner.email))

    if learner:
        # Augments the learner with extra fields that might not have been there
        if learner.user_ID == '':
            logger.info('Augumented user_ID on {}'.format(learner.email))
            learner.user_ID = user_ID
            learner.display_name = display_name
            learner.save()

        if learner.course is None:
            learner.course = course
            learner.save()

    return learner, message


def handle_website_sign_in(learner, is_newbie, request):
    now_time = timezone.now().strftime("%Y-%m-%d at %H:%M:%S")
    if is_newbie or not(learner.is_validated):

        # Create totally new user. At this point we are sure the user
        #          has never been validated on our site before.
        #          But the email address they provided might still be faulty.

        token = create_token_send_email_check_success(learner, request)
        token.save()
        return ("<div style='max-width: 200px; padding:40px'>"
                "An account has been created for you, but must still "
                "be activated. Please check your email and click on the link "
                "that was emailed you. <b>Also check your spam folder</b>."
                "<br></div>".format(now_time))
    else:
        # Not a newbie
        token = create_token_send_email_check_success(learner, request)
        token.save()
        return ("<i>Welcome back!</i> Please check your email, and click on "
                "the link that we emailed you. <b>Also check your spam folder"
                "</b> as sometimes emails don't go where we expect.<br>{}"\
                .format(now_time))


def create_token_send_email_check_success(person, request):
    """ Used during signing in a new user, or an existing user. A token to
    is created, and an email is sent.
    If the email succeeds, then we return with success, else, we indicate
    failure to the calling function.
    """
    TOKEN_LENGTH = 9

    # Create a token for the new user
    hash_value = generate_random_token(TOKEN_LENGTH)

    # Send them a validation email
    send_send_validation_email_email(person, hash_value)
    info = get_course_ep_info(request)
    token = Token(person=person,
                  hash_value=hash_value,
                  next_uri = '{}/course/{}/{}/'.format(DJANGO_SETTINGS.BASE_URL,
                                                info['course'].label,
                                                info['entry_point'].LTI_id)
                )

    # All finished; return what we have (unsaved ``token`` instance)
    return token

def send_validation_email(person, hash_val):
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
    #message = message.replace('\n','\n<br>')
    logger.debug('EMAIL {}:: {} :: {}'.format(to_address_list,
                                              subject,
                                              message))
    return send_email(to_address_list, subject, message, delay_secs=1)



def validate_user(request, hashvalue):
    """ The new/returning user has been sent an email to sign in.
    Recall their token, mark them as validated, sign them in, run the experiment
    they had intended, and redirect them to the next URL associated with their
    token.

    If it is a new user, make them select a Leaderboard name first.
    """
    logger.info('Locating validation token {0}'.format(hashvalue))
    token = get_object_or_404(Token, hash_value=hashvalue)
    if token.was_used:
        # Prevents a token from being re-used.
        message = ('That validation key has been already used. Please request '
                   'another .')
        logger.warn('REUSE of token: {}'.format(hashvalue))
    token.person.is_validated = True
    token.person.save()

    return sign_in_user(request, hashvalue)


def sign_in_user(request, hashvalue):
    """ User is sign-in with the unique hashcode sent to them,
        These steps are used once the user has successfully been validated,
        or if sign-in is successful.

        A user is considered signed-in if "request.session['person_id']" returns
        a valid ``person.id`` (used to look up their object in the DB)
        """

    logger.debug('Attempting sign-in with token {0}'.format(hashvalue))
    token = get_object_or_404(Token, hash_value=hashvalue)
    token.was_used = True
    token.save()

    # The key technology that enables website-based operation of the Peer
    # Review system; set the person id in the session (stored on the server DB)
    request.session['person_id'] = token.person.id
    logger.info('RETURNING USER: {0}'.format(token.person))
    return HttpResponseRedirect(token.next_uri)


def get_course_ep_info(request):
    """
    Returns a dictionary of information about the current person.
    """
    person = None
    if request.session.get('person_id', False):
        try:
            person = Person.objects.get(id=request.session['person_id'])
            if not(person.is_validated == True):
                person = None
        except Person.DoesNotExist:
            pass

    courses = Course.objects.filter(id=request.session.get('course', 0))
    if courses.count() == 1:
        course = courses[0]
    else:
        course = None

    entry_points = EntryPoint.objects.filter(\
                                       id=request.session.get('entry_point', 0))
    if entry_points.count() == 1:
        entry_point = entry_points[0]
    else:
        entry_point = None

    return {'learner': person,
            'course': course,
            'entry_point': entry_point,
            }


def import_groups(request):
    """Imports the exported CSV file"""

    from basic.models import (Person, Course, Group_Formation_Process,
                              GroupEnrolled)
    course = Course.objects.get(name='Preparation MSc thesis for students studying abroad')

    gfp = Group_Formation_Process.objects.get(course=course)
    all_groups = gfp.group_set.all()

    mapper = {'CoSEM/SEPAM': all_groups.get(name='SEPAM'),
              'Management of Technology (MOT)': all_groups.get(name='MOT'),
              'EPA': all_groups.get(name='EPA'),
             }

    import csv
    filename = '/tmp/group-information.csv'
    with open(filename, 'rt', encoding="utf-8") as csvfile:
        reader = csv.reader(csvfile, delimiter=',')
        for row in reader:
            if reader.line_num == 1:
                continue

            # else ...
            _, _, last, first, email, _, group = row
            display_name = '{} {}'.format(first, last)
            email = email.lower()
            role = 'Learn'
            print(display_name)
            learner, newbie = Person.objects.get_or_create(email=email,
                                                           role=role)

            if newbie:
                learner.course = course
                learner.is_validated = False
                learner.display_name = display_name
                logger.debug('Created student: {}'.format(learner))

            # Save the learner, even if already there; will add initials.
            learner.save()
            enrol, _ = GroupEnrolled.objects.get_or_create(person=learner,
                                                           group=mapper[group],
                                                           is_enrolled=True)
            enrol.save()
            logger.debug('Enrolled student [{}] in {}'.format(learner,
                                                            mapper[group]))

        # End of a row
    # End of processing
    return HttpResponse('Imported.')





