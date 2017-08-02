# Verbs: Submit, Review, Evaluate, Rebut, Assess

from django.http import HttpResponse
from django.template.context_processors import csrf
from django.template import Context, Template, loader
from django.conf import settings

# Python and 3rd party imports
import sys
import json
import time
import datetime
from random import shuffle

import networkx as nx

# This app
from .models import Trigger, GroupConfig, Membership, ReviewReport


# Our other apps
from grades.models import GradeItem, LearnerGrade
from submissions.views import get_submission, upload_submission
from submissions.models import Submission
from submissions.forms import (UploadFileForm_one_file,
                               UploadFileForm_multiple_file)
from utils import send_email

# Logging
import logging
logger = logging.getLogger(__name__)


# SHOULD THIS GO TO entry_point instances?
class GLOBAL_Class(object):
    pass
GLOBAL = GLOBAL_Class()
GLOBAL.num_peers = 2
GLOBAL.min_in_pool_before_grouping_starts = 3
GLOBAL.min_extras_before_more_groups_added = 3
assert(GLOBAL.min_extras_before_more_groups_added >= (GLOBAL.num_peers+1))

def starting_point(request, course=None, learner=None, entry_point=None):
    """
    Start the interactive tool here:
    1. push a grade of zero to their gradebook, if the first time visiting.
    2. Call the triggers to process sequentially.
    3. Render the page.
    """

    # Step 1:
    gradeitem = GradeItem.objects.filter(entry=entry_point)
    if gradeitem:
        gitem = gradeitem[0]
    else:
        return HttpResponse('Please create a GradeItem attached to this Entry')

    gitem, first_time = LearnerGrade.objects.get_or_create(gitem=gitem,
                                                           learner=learner)
    if first_time:
        gitem.value = 0.0
        gitem.save()


    # Step 2: Call all triggers:
    triggers = Trigger.objects.filter(entry_point=entry_point,
                                      is_active=True).order_by('order')
    module = sys.modules[__name__]
    now_time = datetime.datetime.now(datetime.timezone.utc)

    ctx_objects = {'now_time': now_time,
                   'learner': learner,
                   'course': course,
                   'entry_point': entry_point,}
    ctx_objects.update(csrf(request)) # add the csrf; used in forms



    # First run through to ensure all triggers exist
    for trigger in triggers:
        try:
            func = getattr(module, trigger.function)
        except AttributeError:
            return HttpResponse('Please create function {0}'.format(\
                                                             trigger.function))

        kwargs = trigger.kwargs.replace('\r','').replace('\n','').replace(' ', '')
        if kwargs:
            try:
                _ = json.loads(kwargs)
            except json.decoder.JSONDecodeError as err:
                return HttpResponse(('Error parsing the kwargs: {0} [{1}]'
                                     .format(err, kwargs)))



    html = []
    html.append('<h2>{}</h2>'.format(learner.email))
    overall_summary = ''

    global_page = """{% extends "basic/base.html" %}{% block content %}<hr>
    <!--SPLIT HERE-->\n{% endblock %}"""
    template_page = Template(global_page)
    context = Context(ctx_objects)
    page_header_footer = template_page.render(context)
    page_header, page_footer = page_header_footer.split('<!--SPLIT HERE-->')
    html.append(page_header)


    for trigger in triggers:
        # Then actually run each trigger, but only if the requirements are
        # met, and we are within the time range for it.

        run_trigger = True
        if (trigger.start_dt > now_time) and (trigger.end_dt <= now_time):
            run_trigger = False
        if gitem.value > trigger.upper:
            run_trigger = False
        if gitem.value < trigger.lower:
            run_trigger = False
        if not(run_trigger):
            continue

        func = getattr(module, trigger.function)
        if trigger.kwargs:
            kwargs = json.loads(trigger.kwargs.replace('\r','')\
                                .replace('\n','')\
                                .replace(' ', ''))
        else:
            kwargs = {}

        # Push these ``kwargs`` into trigger (getattr, settattr)
        for key, value in kwargs.items():
            if not(getattr(trigger, key, False)):
                setattr(trigger, key, value)

        # Add self to ctx_objects
        ctx_objects['self'] = trigger

        # Call the function, finally.
        html_template, summary_template = func(trigger,
                                                learner,
                                                ctx_objects=ctx_objects,
                                                entry_point=entry_point,
                                                gitem=gitem,
                                                request=request
                                               )
        html_trigger = Template(html_template).render(Context(ctx_objects))
        html.append(html_trigger)


    return HttpResponse(html)




def kick_off_email(trigger, learner, entry_point=None, gitem=None,
                   request=None, **kwargs):
    """
    Initiates the kick-off email to the student, to encourage an upload.
    """
    subject = 'Upload document for: {}'.format(entry_point.LTI_title)
    template = """Please upload a PDF with N words. Tkank you."""
    template += '<br>kick_off_email'
    send_email(learner.email, subject, messages=template, delay_secs=0)

    # Assume the email is successfully sent. Adjust the ``gitem``:
    gitem.value = 1.0
    gitem.save(push=True)

    return ('', '')

def submitted_doc(trigger, learner, ctx_objects=None, entry_point=None,
                  gitem=None, **kwargs):
    """
    The user has submitted their document:
    * send email to thank them
    * indicate that they can upload a new version
    * however, we wait until a pool of reviewers are available.
    """
    subject = '[{}] Your PDF upload has been received: '.format(\
        entry_point.LTI_title)
    template = """Thank you for your upload. Please wait for N submissions."""
    template += '<br>submitted_doc'
    #send_email(learner.email, subject, messages=template, delay_secs=0)

    # Email is successfully sent. Adjust the ``gitem`` to avoid spamming.
    #gitem.value +1.0
    #gitem.save(push=True)




def submission_form(trigger, learner, entry_point=None, gitem=None,
                   request=None, ctx_objects=dict(), **kwargs):
    """
    Displays the submission form, and handles the upload of it.

    Fields that can be used in the template:
        {{submission}}                The ``Submission`` model instance
        {{submission_error_message}}  Any error message
        {{file_upload_form}}          The HTML for the upload form
        {{allow_submit}}              If submissions are allowed

    Settings possible in the kwargs, with the defaults are shown.
    {  "accepted_file_types_comma_separated": "PDF",
       "max_file_upload_size_MB": <unlimited>,  [specify as 10 (not a string)]
       "allow_multiple_files": "false",
       "send_email_on_success": "true"
    }

    """
    html_text = summary_line = ''

    # Remove the prior submission from the dict, so that PRs that use
    # multiple submission steps get the correct phase's submission
    #ctx_objects.pop('submission', None)

    # Get the (prior) submission
    submission = prior_submission = get_submission(learner, entry_point)

    # What the admin's see
    if learner.role != 'Learn':
        ctx_objects['self'].admin_overview = 'ADMIN TEXT GOES HERE STILL.'

        #no_submit = dict()
        #all_groups = dict()
        #all_subs = Submission.objects.filter(pr_process=self.pr,
                                             #phase=self, is_valid=True).\
            #order_by('datetime_submitted')
        #if self.pr.uses_groups:
            #all_groups = self.pr.gf_process.group_set.filter()
            #no_submit = all_groups
            #for item in all_subs:
                #no_submit = no_submit.exclude(id=item.group_submitted_id)

        #ctx_objects['no_submit'] = no_submit
        #ctx_objects['all_groups'] = all_groups
        #ctx_objects['all_subs'] = all_subs
        #content = loader.render_to_string('review/admin-submissions.html',
                                          #context=ctx_objects,
                                          #request=request,
                                          #using=None)
        #ctx_objects['self'].admin_overview = content
    if not(getattr(trigger, 'accepted_file_types_comma_separated', False)):
        trigger.accepted_file_types_comma_separated = 'PDF'

    if not(getattr(trigger, 'max_file_upload_size_MB', False)):
        trigger.max_file_upload_size_MB = 10

    if not(hasattr(trigger, 'send_email_on_success')):
        trigger.send_email_on_success = True

    if getattr(trigger, 'allow_multiple_files', False):
        file_upload_form = UploadFileForm_multiple_file()
    else:
        file_upload_form = UploadFileForm_one_file()

    submission_error_message = ''
    if request.FILES:
        submit_inst = upload_submission(request, learner, entry_point, trigger)

        # One final check: has a reviewer been allocated to this review yet?
        sub = Membership.objects.filter(role='Submit', learner=learner)
        if sub.count():
            group = sub[0].group
            reviewers = Membership.objects.filter(role='Review',
                                                  group=group,
                                                  fixed=True)

            if reviewers.count():
                logger.debug(('New submission set to False: {0} as item has '
                          'just started review.'.format(submit_inst)))
                submit_inst.is_valid = False
                submit_inst.save()

                prior_submission.is_valid = True
                prior_submission.save()

                gitem.value = 10.0
                gitem.save(push=True)
                submit_inst = (submit_inst, ('Your submission has been refused;'
                               ' a peer has just started reviewing your work.'))


        if isinstance(submit_inst, tuple):
            # Problem with the upload
            submission_error_message = submit_inst[1]
            submission = prior_submission
        else:
            # Successfully uploaded a document
            submission_error_message = ''
            submission = submit_inst
            gitem.value += 1
            gitem.value = min(max(gitem.value, 3.0), 9.0)
            gitem.save(push=True)

            # Create a group with this learner as the submitter
            already_exists = Membership.objects.filter(learner=learner,
                                                       role='Submit',
                                                       fixed=True).count()
            if not(already_exists):
                new_group = GroupConfig(entry_point=trigger.entry_point)
                new_group.save()
                member = Membership(learner=learner,
                                    group=new_group,
                                    role='Submit',
                                    fixed=True)
                member.save()


            # Finished creating a new group. Now check if we have enough
            # reviewers to invite.
            invite_reviewers(learner, trigger)
            summary_line = ['You uploaded on ...', 'LINK'] # what if there's an error?
    else:
        submission = prior_submission

    # Store some fields on the ``trigger`` for rendering in the template
    trigger.submission = submission
    trigger.submission_error_message = submission_error_message
    trigger.file_upload_form = ctx_objects['file_upload_form'] = \
        file_upload_form

    html_text = trigger.template

    if gitem.value  < 10.0:
        trigger.allow_submit = True  # False, if no more submissions allowed
    else:
        trigger.allow_submit = False

    return html_text, summary_line


def submitted_already(trigger, learner, entry_point=None, gitem=None,
                    request=None, ctx_objects=dict(), **kwargs):

    """
    Simply displays the prior submission, if any.

    Fields that can be used in the template:
        ??{{submission}}                The ``Submission`` model instance
        ??{{submission_error_message}}  Any error message

    Settings possible in the kwargs, with the defaults are shown.
        None

    """
    # Get the (prior) submission
    trigger.submission = get_submission(learner, entry_point)

    summary_line = ['You uploaded on ...', 'LINK'] # what if there's an error?
    return (trigger.template, summary_line)



def get_learners_reviews(learner, gitem, trigger):
    """
    Returns a list. Each item contains a tuple. The first entry is the CSS
    class, for formatting. The second entry is the actual text, link, HTML, etc.
    """
    valid_subs = Submission.objects.filter(entry_point=trigger.entry_point,
                                           is_valid=True)
    if not(valid_subs.count() >= GLOBAL.min_in_pool_before_grouping_starts):
        # Simplest case: no reviews are allocated to learner yet
        out = []
        for idx in range(GLOBAL.num_peers):
            out.append(('', 'Waiting for a peer to submit their work ...'))
        return out

    # Find which reviews are allocated, and provide links:
    out = []
    allocated_reviews = list(ReviewReport.objects.filter(reviewer=learner)\
                             .order_by('-created'))
    for idx in range(GLOBAL.num_peers):
        try:
            review = allocated_reviews.pop()

            out.append(('',
                        '<a href="/review/{0}">Start your review</a>'.format(\
                                                        review.unique_code)))
        except IndexError:
            out.append(('', 'Waiting for a peer to submit their work ...'))
    return out


def get_if_peer_has_read(learner, gitem, trigger):
    out = []
    for idx in range(GLOBAL.num_peers):
        out.append(('future-text', 'text here'))

    return out


def get_peers_evaluation_of_review(learner, gitem, trigger):
    out = []
    for idx in range(GLOBAL.num_peers):
        if gitem.value <= 60:
            out.append(('future-text','peers evaluation of your review link'))

    return out


def get_assess_rebuttal(learner, gitem, trigger):
    out = []
    for idx in range(GLOBAL.num_peers):
        if gitem.value <= 80:
            out.append(('future-text', 'assess their rebuttal of your review link'))

    return out


def interactions_to_come(trigger, learner, entry_point=None, gitem=None,
                         request=None, ctx_objects=dict(), **kwargs):
    """
    WRONG: Does nothing of note, other than display the remaining steps for
    the user.

    Fields that can be used in the template:
        {{future_reviews|safe}}

    Settings possible in the kwargs, with the defaults are shown.
        {{}}
    """
    template = trigger.template
    trigger.future_reviews = ''

    peer = {}  # Reviewer's evaluation of their peers' work stored in here.

    peer['start_or_completed_review'] = get_learners_reviews(learner,
                                                             gitem,
                                                             trigger)
    peer['peer_has_read'] = get_if_peer_has_read(learner,
                                                 gitem,
                                                 trigger)
    peer['evaluation_of'] = get_peers_evaluation_of_review(learner,
                                                           gitem,
                                                           trigger)
    peer['assess_rebut'] = get_assess_rebuttal(learner,
                                               gitem,
                                               trigger)

    for idx in range(GLOBAL.num_peers):
        trigger.future_reviews += """
        <span class="you-peer">
        <b>Your review of peer {0}</b>:
        <ul>
            <li class="{1}">{2}</li>
            <li class="{3}">{4}</li>
            <li class="{5}">{6}</li>
            <li class="{7}">{8}</li>
        </ul>
        </span>
        """.format(idx+1,
                   peer['start_or_completed_review'][idx][0],
                   peer['start_or_completed_review'][idx][1],
                   peer['peer_has_read'][idx][0],
                   peer['peer_has_read'][idx][1],
                   peer['evaluation_of'][idx][0],
                   peer['evaluation_of'][idx][1],
                   peer['assess_rebut'][idx][0],
                   peer['assess_rebut'][idx][1],
                )

    summary_line = ''
    return (trigger.template, summary_line)


def invite_reviewers(learner, trigger):
    """
    Invites reviewers to start the review process
    """
    valid_subs = Submission.objects.filter(trigger=trigger, is_valid=True)
    if not(valid_subs.count() >= GLOBAL.min_in_pool_before_grouping_starts):
        return

    # We have enough Submissions instances for the current trigger to send
    # emails to all potential reviewers: it is time to start reviewing
    #
    # The number of Submissions should be equal to the nubmer of nodes in graph:
    graph = group_graph(trigger)
    if len(valid_subs) != graph.order():
        logger.warn(('Number of valid subs [{0}]is not equal to graph '
                     'order [{1}]'.format(len(valid_subs), graph.order())))

    for learner in graph.nodes():
        # These ``Persons`` have a valid submission. Invite them to review.
        # Has a reviewer been allocated this submission yet?
        allocated = ReviewReport.objects.filter(trigger=trigger,
                                                reviewer=learner,
                                                have_emailed=True)
        if allocated.count() >= GLOBAL.num_peers:
            return

        review, _ = ReviewReport.objects.get_or_create(trigger=trigger,
                                                       reviewer=learner,
                                                       have_emailed=False)

        # Then send them an email, but only once
        message = """
        Reviewing and interacting with the work of other students helps
        stimulate learning and insight you might not have developed otherwise.

        So for the course {1} you are required to completed {0} reviews of work
        from your peers. This is for the component of the course: {2}.

        Please complete the reviews as soon as possible to progress to the next
        stages: evaluation, assessment and rebuttal.

        You can start the review with <a href="{3}">this link</a>.

        You will receive an email for every review you are to complete.

        Good luck!
        """.format(GLOBAL.num_peers,
                   trigger.entry_point.course,
                   trigger.entry_point.LTI_title,
                   settings.BASE_URL + '/review/' + review.unique_code)
        subject = '[{0}]: start your peer review'.format(trigger.entry_point.course)

        if not(review.have_emailed):
            send_email(learner.email, subject, messages=message, delay_secs=0)

            # Ideally this is in the return hook, but for now leave it here.
            review.have_emailed = True
            review.save()


# Functions related to the graph and grouping
# -------------------------------------------
def group_graph(trigger):
    """
    Creates the group graph.

    Rules:
    1. Nodes are ``Person`` instances. We get the email address from the node.
    2. A node is added to the graph if, and only if, the person has submitted.
    3. Edges are directed. From a submitter, to a reviewer.
    4. An edge is only created if the reviewer has opened (therefore seen) the
       allocated review.
       A review is allocated in real time, when the reviewer wants to start.o
    5. The edge contains a ``Submission`` instance.

    ## How many Submissions are currently in groups?
    ## Is it below the minimum to start?
    ## Do we have extra that have come by?
    #max_iter = 20
    #itern = 0
    #while (GroupConfig.Lock.locked) and (itern < max_iter):
        #logger.debug('GroupConfig locked: sleeping {0}'.format(itern))
        #itern += 1
        #time.sleep(0.25)
    #if itern == max_iter:
        #logger.error(('Maximum sleep experienced; something hanging? [{0}] '
                      #'[{1}] [{2}]'.format(learner, trigger, submission)))


    ## Do the group formation / regrouping here
    #GroupConfig.Lock.locked = True
    """
    groups = GroupConfig.objects.filter(entry_point=trigger.entry_point)
    graph = nx.DiGraph()
    submitters = []
    for group in groups:

        submitter = group.membership_set.filter(role='Submit')[0]
        submitters.append(submitter)
        graph.add_node(submitter.learner)

        reviewers = group.membership_set.filter(role='Review', fixed=True)
        for reviewer in reviewers:
            graph.add_node(reviewer.learner)
            graph.add_edge(submitter.learner, reviewer.learner, weight=1)




    return graph

def get_next_reviewer(graph, exclude=None):
    """
    Given the graph, get the next available reviewer.

    You can optionally specify the ``
    """
    potential = graph.nodes()
    if exclude:
        index = potential.index(exclude)
        potential.pop(index)

    shuffle(potential)
    in_degree = []
    for idx, node in enumerate(potential):
        in_degree.append((graph.in_degree(node), idx))

    in_degree.sort()
    next_one = in_degree.pop(0)

    if next_one[0] <= GLOBAL.num_peers:
        return potential[next_one[1]]
    else:
        return None

def get_learner_grouping(learner, entry_point):
    """
    Returns a dictionary where:
        out['submitter'] = Membership instance
        out['reviewer] = [Membership instance, Membership instance, ...]
    """
    out = {}
    submit = Membership.objects.filter(learner=learner,
                                       group__entry_point=entry_point,
                                       fixed=True,
                                       role='Submit')
    if submit.count() == 0:
        out['submitter'] = None
    else:
        if submit.count() > 1:
            logger.error(('Learner {0} is submitter in more than 1 group. Not '
                          'possible. Investigate.'.format(learner)))
        out['submitter'] = submit[0]


    review = Membership.objects.filter(learner=learner,
                                       group__entry_point=entry_point,
                                       role='Review')
    if review.count() > GLOBAL.num_peers:
        logger.error(('Learner {0} is reviewer in too many grades. Not '
                              'possible. Investigate.'.format(learner)))
    else:
        out['reviewer'] = list(review)

    return out