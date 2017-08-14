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
from collections import namedtuple

import networkx as nx

# This app
from .models import Trigger, GroupConfig, Membership, ReviewReport
from .models import AchieveConfig, Achievement


# Our other apps
from rubric.views import (handle_review, get_create_actual_rubric,
                          get_learner_details)
from rubric.models import RubricTemplate, RubricActual
from grades.models import GradeItem, LearnerGrade
from submissions.views import get_submission, upload_submission
from submissions.models import Submission
from submissions.forms import (UploadFileForm_one_file,
                               UploadFileForm_multiple_file)

from utils import send_email, insert_evaluate_variables

# Logging
import logging
logger = logging.getLogger(__name__)

# Summary structure
class Summary(object):
    def __init__(self, date=None, action='', link='', catg=''):
        if date is None:
            self.date = datetime.datetime.now()
        else:
            self.date = date
        self.action = action
        self.link = link
        self.catg = catg

    def __str__(self):
        return '[{0}] {1}'.format(self.date.strftime('%d %B %Y at %H:%M'),
                                  self.action)

    __repr__ = __str__


# SHOULD THIS GO TO entry_point instances?
class GLOBAL_Class(object):
    pass
GLOBAL = GLOBAL_Class()
GLOBAL.num_peers = 2
GLOBAL.min_in_pool_before_grouping_starts = 3
GLOBAL.min_extras_before_more_groups_added = 3
GLOBAL.SUBMISSION_FIXED = 10
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

    grade, first_time = LearnerGrade.objects.get_or_create(gitem=gitem,
                                                           learner=learner)
    if first_time:
        grade.value = 0.0
        grade.save()


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



    summaries = []
    for trigger in triggers:
        # Then actually run each trigger, but only if the requirements are
        # met, and we are within the time range for it.

        run_trigger = True
        if (trigger.start_dt > now_time) and (trigger.end_dt <= now_time):
            run_trigger = False
        #if grade.value > trigger.upper:
        #    run_trigger = False
        #if grade.value < trigger.lower:
        #    run_trigger = False
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
        func(trigger,
             learner=learner,
             ctx_objects=ctx_objects,
             entry_point=entry_point,
             summaries=summaries,
             request=request
           )

    ctx_objects['summary_list'] = summaries
    if settings.DEBUG:
        ctx_objects['header'] = '<h2>{}</h2>'.format(learner.email)

    html = loader.render_to_string('interactive/landing_page.html',
                                    ctx_objects)
    return HttpResponse(html)


def render_template(trigger, ctx_objects):
    """
    Renders the templated text in ``trigger`` using variables in ``ctx_objects``

    """
    ctx_objects['self'] = trigger
    return Template(trigger.template).render(Context(ctx_objects))


def has(learner, achievement):
    """
    See's if a user has completed a certain achievement.
    """
    possible = Achievement.objects.filter(learner=learner,
                                          achieved__name=achievement)
    if possible.count() == 0:
        return False
    else:
        return possible[0].done


def completed(learner, achievement):
    """
    Complete this item for the learner's achievement
    """
    possible = Achievement.objects.filter(learner=learner,
                                          achieved__name=achievement)
    if possible.count() == 0:
        completed = Achievement(learner=learner,
                        achieved=AchieveConfig.objects.get(name=achievement))
    else:
        completed = possible[0]

    completed.done = True
    completed.save()


def kick_off_email(trigger, learner, entry_point=None, **kwargs):
    """
    Initiates the kick-off email to the student, to encourage an upload.
    """

    if has(learner, 'kick_off_email'):
        return None

    subject = 'Upload document for: {}'.format(entry_point.LTI_title)
    template = """Please upload a PDF with N words. Tkank you."""
    template += '<br>kick_off_email'
    send_email(learner.email, subject, messages=template, delay_secs=0)

    completed(learner, 'kick_off_email')


def submitted_doc(trigger, learner, ctx_objects=None, entry_point=None,
                  request=None, **kwargs):
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
    send_email(learner.email, subject, messages=template, delay_secs=0)

    # Email is successfully sent. Adjust the ``grade`` to avoid spamming.
    #grade.value +1.0
    #grade.save(push=True)


def submission_form(trigger, learner, entry_point=None, summaries=list(),
                   ctx_objects=dict(), **kwargs):
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
    html_text = ''

    # Remove the prior submission from the dict, so that PRs that use
    # multiple submission steps get the correct phase's submission
    #ctx_objects.pop('submission', None)

    # Get the (prior) submission
    submission = prior_submission = get_submission(learner, trigger)

    # What the admin's see
    if learner.role != 'Learn':
        ctx_objects['self'].admin_overview = 'ADMIN TEXT GOES HERE STILL.'


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
    if kwargs['request'].FILES:
        submit_inst = upload_submission(kwargs['request'],
                                        learner,
                                        entry_point,
                                        trigger)

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

                #grade.value = 10.0
                #grade.save(push=True)
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

            completed(learner, achievement='submitted')
            #grade.value += 1
            #grade.value = min(max(grade.value, 3.0), 9.0)
            #grade.save(push=True)

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

            # what if there's an error?
            #summary_line.action = ['You uploaded on ...', 'LINK']

    else:
        submission = prior_submission

    # Store some fields on the ``trigger`` for rendering in the template
    trigger.submission = submission
    trigger.submission_error_message = submission_error_message
    trigger.file_upload_form = ctx_objects['file_upload_form'] = \
        file_upload_form


    if has(learner, 'work_has_started_to_be_reviewed'):
        trigger.allow_submit = False  # False, if no more submissions allowed
    else:
        trigger.allow_submit = True

    ctx_objects['submission'] = trigger.template

    if trigger.submission:
        summary = Summary(date=trigger.submission.datetime_submitted,
                          action='You successfully submitted your document',
                          link='<a href="{0}" target="_blank">{1}</a>'.format(\
                              trigger.submission.file_upload.url, "View"),
                          catg='sub')
        summaries.append(summary)

    ctx_objects['submission'] = render_template(trigger, ctx_objects)





    # Get the (prior) submission
    #trigger.submission = get_submission(learner, trigger)

    # If we didn't get a submission, search in the prior trigger
    #if not(trigger.submission) and has(learner, 'submitted'):
    #    prior_triggers = Trigger.objects.filter(entry_point=entry_point,
    #                                            order__lte=trigger.order,
    #                                        is_active=True).order_by('-order')
    #    if prior_triggers.count() >= 2:
    #        # The first trigger will be our current trigger, so take [1]
    #        prior_trigger = prior_triggers[1]
    #    trigger.submission = get_submission(learner, prior_trigger)#



    #ctx_objects['submission'] = trigger.template


    #return (trigger.template, [summary, ])



def get_learners_reviews(trigger, learner, ctx_objects, entry_point,
                         summaries, **kwargs):

    """
    Returns a list. Each item contains a tuple. The first entry is the CSS
    class, for formatting. The second entry is the actual text, link, HTML, etc.
    """

    valid_subs = Submission.objects.filter(entry_point=trigger.entry_point,
                                           is_valid=True)

    # Get this learner's submission, if it exists:
    this_learner = valid_subs.filter(submitted_by=learner)
    if this_learner:
        summary = Summary(date=this_learner[0].datetime_submitted,
                          action='You successfully submitted your document',
                link='<a href="{0}" target="_blank">{1}</a>'.format(\
                    this_learner[0].file_upload.url, "View"),
                catg='sub')
        summaries.append(summary)




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

    if len(allocated_reviews):
        summary = Summary(date=allocated_reviews[0].created,
                          action='Peer reviews were allocated to you',
                          catg='rev')
        summaries.append(summary)


    for idx in range(GLOBAL.num_peers):
        try:
            review = allocated_reviews.pop()
            if not(review.order):
                review.order = idx+1
                review.save()

            # What is the status of this review. Cross check with RubricActual
            prior = RubricActual.objects.filter(rubric_code=review.unique_code)
            status = 'Start your review'
            if prior.count():
                if prior[0].status == 'C':
                    status = 'Completed'
                    summary = Summary(date=prior[0].completed,
                       action='Review number {0} completed; thank you!'\
                                  .format(review.order, GLOBAL.num_peers),
                       link='<a href="/interactive/{0}">View</a>'.format(\
                                                           review.unique_code),
                       catg='rev')
                    summaries.append(summary)

                elif prior[0].status in ('P', 'V'):
                    status = 'Continue your review'

            out.append(('',
                    '<a href="/interactive/{1}">{0}</a>'.format(status,
                                                           review.unique_code)))
        except IndexError:
            out.append(('', 'You must submit before you can review others.'))
    return out


def get_if_peer_has_read(learner, grade, trigger, summaries):
    out = []
    for idx in range(GLOBAL.num_peers):
        out.append(('future-text',
                    'Waiting for peer to read your review'))

    return out


def get_peers_evaluation_of_review(learner, grade, trigger, summaries):
    out = []
    for idx in range(GLOBAL.num_peers):
        if grade.value <= 60:
            out.append(('future-text',
                        "Waiting for peer's evaluation of your review"))

    return out


def get_assess_rebuttal(learner, grade, trigger, summaries):
    out = []
    for idx in range(GLOBAL.num_peers):
        if grade.value <= 80:
            out.append(('future-text',
                        "Waiting for peer's rebuttal of your review"))

    return out


def get_read_evaluate_feedback(learner, grade, trigger, my_submission,
                               summaries):
    """
    Allow the submitter (learner) to read the reviews.
    """
    rubrics = RubricActual.objects.filter(submission=my_submission)

    for idx, ractual in enumerate(rubrics):
        summary = Summary(date=ractual.created, link='', catg='sub',
                          action='Peer {} opened your review'.format(idx+1))
        summaries.append(summary)
        if ractual.status == 'C' and ractual.submitted:
            summary = Summary(date=ractual.completed, link='', catg='sub',
                action='Peer {} completed a review of your work'.format(idx+1))
            summaries.append(summary)


    if (rubrics.filter(status='C').count() + rubrics.filter(status='L').count())\
                                                          < GLOBAL.num_peers:
        return ('future-text', 'Read and evaluate their feedback')

    # If we have reached this point it is because the submitter can now
    # view their feedback. Therefore we only iterate over the COMPLETED rubrics.

    # 2/ Set the r_actual review to be locked (read-only)
    # 3/ NOT: Assign a submitter code (``submitted)
    # 4/ Indicate the submitter has read the reviews: so the reviewers see that
    # 5/ Create a rubric for evaluation of the review (submitter prompted to fill)



    #rubrics = rubrics.filter(status='C')

    #text = 'Read and evaluate their feedback: '
    #for idx, ractual in enumerate(rubrics):
        #ractual.status = 'L'
        #ractual.save()


        #sub_eval = ReviewReport.objects.get(submitter_code=ractual.rubric_code)

        #text += 'evaluate <a href="/evaluate/{0}/">peer {1}</a>'.format(sub_eval.unique_code,
                                                                       #idx+1)




    return ('',  '')


def get_provide_rebuttal(learner, grade, trigger, summaries):
    """
    Get, or provide the rebuttal form to the submitter to respond back to the
    reviewers.
    """
    out = ('future-text', 'Provide a rebuttal back to peers')
    return out

def get_rebuttal_status(learner, grade, trigger, summaries):
    """
    Displays the rebuttal status.
    """
    out = ('future-text', 'Rebuttal was read and assessed')
    return out


def interactions_to_come(trigger, learner, entry_point=None, grade=None,
                         request=None, ctx_objects=dict(), **kwargs):
    """
    Fields that can be used in the template:
        {{review_to_peers|safe}}
        {{peers_back_to_submitter|safe}}

    Settings possible in the kwargs, with the defaults are shown.
        {{}}
    """

    summaries = []
    template = trigger.template
    trigger.review_to_peers = ''
    trigger.peers_back_to_submitter = '0 peers have reviewed your work.'

    peer = {}  # Reviewer's evaluation of their peers' work stored in here.

    peer['start_or_completed_review'] = get_learners_reviews(learner,
                                                             grade,
                                                             trigger,
                                                             summaries)
    peer['peer_has_read'] = get_if_peer_has_read(learner,
                                                 grade,
                                                 trigger,
                                                 summaries)
    peer['evaluation_of'] = get_peers_evaluation_of_review(learner,
                                                           grade,
                                                           trigger,
                                                           summaries)
    peer['assess_rebut'] = get_assess_rebuttal(learner,
                                               grade,
                                               trigger,
                                               summaries)

    for idx in range(GLOBAL.num_peers):
        trigger.review_to_peers += """
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


    trigger.peers_back_to_submitter
    my_submission = Submission.objects.filter(entry_point=entry_point,
                                              is_valid=True,
                                              submitted_by=learner)
    reports = [False, ] * GLOBAL.num_peers
    completed = [False,] * GLOBAL.num_peers
    #in_progress = [False,] * GLOBAL.num_peers
    idx = 0
    my_reviews = []
    for submission in my_submission:
        my_reviews = ReviewReport.objects.filter(submission=submission).\
                        order_by('created') # to ensure consistency in display
        for report in my_reviews:
            # There should be at most "GLOBAL.num_peers" reviews
            reports[idx] = report
            try:
                rubric = RubricActual.objects.get(\
                                           rubric_code=reports[idx].unique_code)
            except RubricActual.DoesNotExist:
                continue
            if rubric.submitted:
                completed[idx] = True


            # Bump the counter and get the rest of the reviews.
            idx += 1


    # This message is overridden later for the case when everyone is completed.
    header = """{{n_reviewed}} peer{{ n_reviewed|pluralize:" has,s have" }}
     completely reviewed your work. Waiting for {{n_more}} more
        peer{{n_more|pluralize}} to start (or complete) their review."""

    head = insert_evaluate_variables(header, {'n_reviewed': sum(completed),
                                              'n_more': GLOBAL.num_peers - \
                                                               sum(completed)}
                                     )


    trigger.peers_back_to_submitter = head


    peer['read_evaluate_feedback'] = get_read_evaluate_feedback(learner,
                                                                grade,
                                                                trigger,
                                                                my_submission,
                                                                summaries)
    peer['provide_rebuttal'] = get_provide_rebuttal(learner,
                                                    grade,
                                                    trigger,
                                                    summaries)
    peer['rebuttal_status'] = get_rebuttal_status(learner,
                                                  grade,
                                                  trigger,
                                                  summaries)

    if sum(completed) == GLOBAL.num_peers:
        trigger.peers_back_to_submitter = "All peers have reviewed your work."

    trigger.peers_back_to_submitter  += """
    <style>.peers_to_you{{list-style-type:None}}</style>

    <span class="indent">
    <ul>
        <li class="peers_to_you {0}" type="a">(a) {1}</li>
        <li class="peers_to_you {2}" type="a">(b) {3}</li>
        <li class="peers_to_you {4}" type="a">(c) {5}</li>
    </ul>
    </span>
    """.format(peer['read_evaluate_feedback'][0],
               peer['read_evaluate_feedback'][1],
               peer['provide_rebuttal'][0],
               peer['provide_rebuttal'][1],
               peer['rebuttal_status'][0],
               peer['rebuttal_status'][1])


    return (trigger.template, summaries)


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
    if len(valid_subs) != graph.graph.order():
        logger.warn(('Number of valid subs [{0}]is not equal to graph '
                'order [{1}]'.format(len(valid_subs), graph.graph.order())))

    for learner in graph.graph.nodes():
        # These ``Persons`` have a valid submission. Invite them to review.
        # Has a reviewer been allocated this submission yet?
        allocated = ReviewReport.objects.filter(trigger=trigger,
                                                reviewer=learner,
                                                have_emailed=True)
        while allocated.count() < GLOBAL.num_peers:

            review, _ = ReviewReport.objects.get_or_create(trigger=trigger,
                                                           reviewer=learner,
                                                           have_emailed=False)

            # Then send them an email, but only once
            message = """
            Reviewing and interacting with the work of other students helps
            stimulate learning and insight you might not have developed
            otherwise.

            So for the course {1} you are required to completed {0} reviews of
            work from your peers. This is for the component of the course: {2}.

            Please complete the reviews as soon as possible to progress to the
            next stages: evaluation, assessment and rebuttal.

            You can start the review with <a href="{3}">this link</a>.

            You will receive an email for every review you are to complete.

            Good luck!
            """.format(GLOBAL.num_peers,
                       trigger.entry_point.course,
                       trigger.entry_point.LTI_title,
                       settings.BASE_URL + '/interactive/' + review.unique_code)
            subject = '[{0}]: start your peer review'.format(\
                                                trigger.entry_point.course)

            if not(review.have_emailed):
                send_email(learner.email, subject, messages=message,
                           delay_secs=0)

                # Ideally this is in the return hook, but for now leave it here.
                review.have_emailed = True
                review.save()

            # Update the allocation list
            allocated = ReviewReport.objects.filter(trigger=trigger,
                                                    reviewer=learner,
                                                    have_emailed=True)

            completed(learner, achievement='email_to_start_reviewing')


# Functions related to the graph and grouping
# -------------------------------------------
class group_graph(object):
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
    def __init__(self, trigger):

        groups = GroupConfig.objects.filter(entry_point=trigger.entry_point)

        # Added these two lines, so the graphs are always created randomly
        groups = list(groups)
        shuffle(groups)

        self.graph = nx.DiGraph()
        self.trigger = trigger
        submitters = []
        for group in groups:

            submitter = group.membership_set.filter(role='Submit')
            if submitter.count() == 0:
                continue
            submitters.append(submitter[0])
            self.graph.add_node(submitter[0].learner)

            reviewers = group.membership_set.filter(role='Review', fixed=True)
            for reviewer in reviewers:
                self.graph.add_node(reviewer.learner)
                self.graph.add_edge(submitter[0].learner,
                                    reviewer.learner,
                                    weight=1)


    def get_next_review(self, exclude=None):
        """
        Given the graph, get the next reviewer.

        You can optionally specify the ``
        """
        potential = self.graph.nodes()
        if exclude:
            index = potential.index(exclude)
            potential.pop(index)

        shuffle(potential)
        in_degree = []
        for idx, node in enumerate(potential):
            in_degree.append((self.graph.in_degree(node), idx))

        in_degree.sort()
        next_one = in_degree.pop(0)

        if next_one[0] <= GLOBAL.num_peers:
            return potential[next_one[1]]
        else:
            return None


    def get_submitter_to_review(self, exclude_reviewer):
        """
        Get the next submitter's work to review. You must specify the
        reviewer's Person instance, to ensure they are excluded as a
        potential submission to evaluate.


        Rules:
        1. Arrows go FROM the submitter, and TO the reviewer.
        2. Avoid an arrow back to the submitter
        3. If unavoidable, go to the person with the least number of allocated
           reviews (incoming arrows)
        4. After that, assign randomly.
        """

        # TODO: ensure the submitter's work is not reviewed too many times

        potential = self.graph.nodes()
        if exclude_reviewer:
            index = potential.index(exclude_reviewer)
            potential.pop(index)

        # Important to shuffle here, so the indices are randomized
        shuffle(potential)

        # tuple-order: (outdegree, indegree, node_index)
        allocate = []
        for idx, node in enumerate(potential):
            allocate.append((self.graph.out_degree(node),
                             self.graph.in_degree(node),
                             idx))

        # Even now when we sort, we are sorting on indices that have been
        # randomly allocated
        allocate.sort()

        next_one = allocate.pop(0)
        while (next_one[0] <= GLOBAL.num_peers) and (self.graph.has_edge(\
                potential[next_one[2]], exclude_reviewer)):
            next_one = allocate.pop(0)

        return potential[next_one[2]]





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





def review(request, unique_code=None):
    """
    A review link (with ``unique_code``) is created the moment we have enough
    submitters to pool up. The link is created, and shown in the user-interface
    and (perhaps) they are emailed. When they visit that link, the review
    process starts:
    1/ Select a submission to attach this to, if not already attached.
    2/ prevent the document from being re-uploaded by submitter (fixed=True)
    3/ create rubric / Get the rubric (with prior filled in answers)
    4/ Return the rendered HTML to the reviewer.
    """
    reports = ReviewReport.objects.filter(unique_code=unique_code)
    if reports.count() != 1:
        logger.error('Incorrect review requested: {}'.format(unique_code))
        return HttpResponse(("You've used an incorrect link. Please check the "
                             'web address to ensure there was not a typing '
                             'error.<p>No peer review found with that link.'))

    report = reports[0]


    # 1. Select a submission to attach this to, if not already attached.
    if report.submission:
        # This is going to be called later by the handle_review function. Might
        # as well check that the user's rubric etc is correctly created.
        r_actual, reviewer = get_learner_details(report.unique_code)
        if reviewer is None:
            # This branch only happens with error conditions. Maybe the
            # RubricActual has been deleted from the DB manually, etc.
            pass
        else:
            return handle_review(request, unique_code)


    graph = group_graph(report.trigger)
    submitter = graph.get_submitter_to_review(exclude_reviewer=\
                                                         report.reviewer)

    valid_subs = Submission.objects.filter(is_valid=True,
                                    entry_point=report.trigger.entry_point,
                                    submitted_by=submitter)
    if valid_subs.count() != 1:
        logger.error(('Found more than 1 valid Submission for {} in entry '
                      'point {}'.format(valid_subs,
                                        report.trigger.entry_point)))
    submission = valid_subs[0]
    report.submission = submission
    report.save()

    # 2. Prevent the document from being re-uploaded by submitter
    #    Do this by altering the grade of the submitter to have a minimum
    #    value of 10.
    gitem = GradeItem.objects.get(entry=report.trigger.entry_point)
    grade = LearnerGrade.objects.get(gitem=gitem, learner=submitter)
    grade.value = max(GLOBAL.SUBMISSION_FIXED, grade.value)
    grade.save()



    if report.grpconf is None: # which it also should be ...
        submitter_member = Membership.objects.get(learner=submitter,
                                                  role='Submit',
                                                  fixed=True,
                            group__entry_point=report.trigger.entry_point)

        new_membership, _ = Membership.objects.get_or_create(role='Review',
                                                             fixed=True,
                                            learner=report.reviewer,
                                            group=submitter_member.group)


        report.grpconf = new_membership.group
        report.save()


    # Lastly, also create a RubricActual instance

    # Creates a new actual rubric for a given ``learner`` (the person
    # doing the) evaluation. It will be based on the parent template
    # defined in ``template``, and for the given ``submission`` (either
    # their own submission if it is a self-review, or another person's
    # submission for peer-review).

    get_create_actual_rubric(learner=report.reviewer,
                             trigger=report.trigger,
                             submission=submission,
                             rubric_code=unique_code)


    # Finally, return to the same point as if we were at the top of this func.
    return handle_review(request, unique_code)





def reviews_to_submitter(trigger, learner, entry_point=None, grade=None,
                         request=None, ctx_objects=dict(), **kwargs):
    """
    """
    a = 'asd'
    return ('', '')