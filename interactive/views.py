# Verbs: Submit, Review, Evaluate, Rebut, Assess

from django.http import HttpResponse
from django.template.context_processors import csrf
from django.template import Context, Template, loader
from django.core.files import File
from django.conf import settings
from django.utils import timezone

# Python and 3rd party imports
import os
import sys
import json
import time
import random
import datetime
import tempfile
from random import shuffle
from collections import namedtuple, OrderedDict

import networkx as nx
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.colors import black
from reportlab.platypus import Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from PyPDF2 import PdfFileReader, PdfFileMerger

# This app
from .models import Trigger, GroupConfig, Membership, ReviewReport
from .models import AchieveConfig, Achievement
from .models import EvaluationReport

# Our other apps
from basic.models import EntryPoint
from rubric.views import (handle_review, get_create_actual_rubric,
                          get_learner_details)
from rubric.models import RubricTemplate, RubricActual
from grades.models import GradeItem, LearnerGrade
from grades.views import push_grade
from submissions.views import get_submission, upload_submission
from submissions.models import Submission
from submissions.forms import (UploadFileForm_one_file,
                               UploadFileForm_multiple_file)

from utils import send_email, insert_evaluate_variables, generate_random_token

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

assert(GLOBAL.min_extras_before_more_groups_added >= (GLOBAL.num_peers+1))

def starting_point(request, course=None, learner=None, entry_point=None):
    """
    Start the interactive tool here:
    1. push a grade of zero to their gradebook, if the first time visiting.
    2. Call the triggers to process sequentially.
    3. Render the page.
    """
    # Step 1:
    if not push_grade(learner, 0.0, entry_point, testing=True):
        return HttpResponse('Please create a GradeItem attached to this Entry')

    # Step 2: Call all triggers:
    triggers = Trigger.objects.filter(entry_point=entry_point,
                                      is_active=True).order_by('order')
    module = sys.modules[__name__]
    now_time = datetime.datetime.now(datetime.timezone.utc)

    ctx_objects = {'now_time': now_time,
                   'learner': learner,
                   'course': course,
                   'entry_point': entry_point,

                   # Used for pushing grades to the platform
                   'sourcedid': \
                             request.POST.get('lis_result_sourcedid', ''),
                }
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
        if not(run_trigger):
            continue

        func = getattr(module, trigger.function)
        if trigger.kwargs:
            kwargs = json.loads(trigger.kwargs.replace('\r','')\
                                .replace('\n',''))
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
    return insert_evaluate_variables(trigger.template, ctx_objects)




# ------------------------------
# The various trigger functions
# ------------------------------
def kick_off_email(trigger, learner, entry_point=None, **kwargs):
    """
    Initiates the kick-off email to the student, to encourage an upload.
    """

    if has(learner, 'kick_off_email'):
        return None

    """
    The user is visiting the page for the first time.
    * send email to tell them about the process.
    """
    ctx = {'LTI_title': entry_point.LTI_title}
    subject = insert_evaluate_variables(trigger.subject, ctx)
    message = insert_evaluate_variables(trigger.message, ctx)
    #send_email(learner.email, subject, messages=message, delay_secs=10)
    #
    # This step has been removed to reduce the amount of emails sent.
    completed(learner, 'kick_off_email')


def get_submission_form(trigger, learner, entry_point=None, summaries=list(),
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
       "send_email_on_success": "false"
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
        trigger.send_email_on_success = False

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


            push_grade(learner, 10, entry_point)


            # Send an email
            """
            The user has submitted their document:
            * send email to thank them
            * indicate that they can upload a new version
            * however, we wait until a pool of reviewers are available.
            """
            if trigger.subject and trigger.message and \
                                                 trigger.send_email_on_success:
                ctx = {'LTI_title': entry_point.LTI_title,
                       'filename': submission.submitted_file_name}

                subject = insert_evaluate_variables(trigger.subject, ctx)
                message = insert_evaluate_variables(trigger.message, ctx)
                send_email(learner.email,
                           subject,
                           messages=message,
                           delay_secs=5)

            # else: don't send a message by email.

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


            # Learner has completed this step:
            completed(learner, achievement='submitted')

            # Finished creating a new group. Now check if we have enough
            # reviewers to invite.
            invite_reviewers(learner, trigger)


    else:
        submission = prior_submission

    # Store some fields on the ``trigger`` for rendering in the template
    trigger.submission = submission
    trigger.submission_error_message = submission_error_message
    trigger.file_upload_form = ctx_objects['file_upload_form'] = \
        file_upload_form

    # Note: this is triggered in 2 places: the learner cannot resubmit if
    #       they themselves have started a review of their peer (this is to
    #       prevent learners from seeing the rubric via a peer's work).
    #       Note: a learner is only invited to review once they themselves
    #             have submitted something already.
    #       Also, if the learner's work is started to being reviewed by a peer
    #       then the original submitter cannot resubmit.
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
                          catg='')
        summaries.append(summary)

    ctx_objects['submission'] = render_template(trigger, ctx_objects)


def your_reviews_create_evaluations(trigger, learner, entry_point=None,
                         summaries=list(), ctx_objects=dict(), **kwargs):
    """
    TODO: at this point load all the reviews of the learner that are completed
    which are attached to the prior trigger.


    Create (asybc) a PDF of these. And create a submission.
    Copy the code currently in rubric/views.py here.


    """
    return


def your_reviews_of_your_peers(trigger, learner, entry_point=None,
                         summaries=list(), ctx_objects=dict(), **kwargs):
    """
    We are filling in this template multiple times; once per GLOBAL.num_peers:

    <span class="you-peer">
        <b>Your review of peer {0}</b>:
        <ul>
            <li class="{1}">{2}</li>
            <li class="{3}">{4}</li>
            <li class="{5}">{6}</li>
            <li class="{7}">{8}</li>
        </ul>
    </span>
    """
    review_to_peers = ''
    peer = {}
    peer['line1'] = get_line1(learner, trigger, summaries)
    peer['line2'] = get_line2(learner, trigger, summaries)
    peer['line3'] = get_line3(learner, trigger, summaries)
    peer['line4'] = get_line4(learner, trigger, summaries)

    for idx in range(GLOBAL.num_peers):
        review_to_peers += """
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
                   peer['line1'][idx][0],
                   peer['line1'][idx][1],
                   peer['line2'][idx][0],
                   peer['line2'][idx][1],
                   peer['line3'][idx][0],
                   peer['line3'][idx][1],
                   peer['line4'][idx][0],
                   peer['line4'][idx][1],
                )

    trigger.template = review_to_peers
    ctx_objects['review_to_peers'] = render_template(trigger, ctx_objects)


def get_line1(learner, trigger, summaries):
    """
    Fills in line 1 of the template:
        > Waiting for a peer to submit their work ...
        > You must submit before you can review others
        > Start your review
        > Continue your review
        > Completed

    """
    out = []

    # All valid submissions for this EntryPoint
    valid_subs = Submission.objects.filter(entry_point=trigger.entry_point,
                            is_valid=True).exclude(status='A')

    # All ReviewReport that have been Allocated for Review to this learner
    allocated_reviews = ReviewReport.objects.filter(reviewer=learner)\
                                 .order_by('-created') # for consistency

    graph = group_graph(trigger.entry_point)
    if graph.graph.has_node(learner):
        in_degree = graph.graph.in_degree(learner)
    else:
        allocated_reviews = []

    reviews_completed = [False, ] * GLOBAL.num_peers
    for idx, review in enumerate(allocated_reviews):

        if not(review.order):
            review.order = idx+1
            review.save()

        if in_degree == 0 and idx == 0:
            status = 'Start your review'
        elif in_degree == 0 and idx == 1:
            status = out.append(('future-text',
                                 'Waiting for a peer to submit their work ...'))
            continue
        elif in_degree >= 1:
            status = 'Start your review'


        # What is the status of this review. Cross check with RubricActual
        prior = RubricActual.objects.filter(rubric_code=review.unique_code)
        if prior.count():
            if prior[0].status in ('C', 'L'):
                status = 'Completed'
                reviews_completed[idx] = True
                summary = Summary(date=prior[0].completed,
                   action='You completed review number {0}; thank you!'\
                              .format(review.order, GLOBAL.num_peers),
                   link='<a href="/interactive/review/{0}">View</a>'.format(\
                                                       review.unique_code),
                   catg='rev')
                summaries.append(summary)

            elif prior[0].status in ('P', 'V'):
                status = 'Continue your review'

        out.append(('',
                '<a href="/interactive/review/{1}">{0}</a>'.format(status,
                                                       review.unique_code)))

    if sum(reviews_completed) == GLOBAL.num_peers:
        completed(learner, 'completed_all_reviews')
        push_grade(learner, 30.0, trigger.entry_point)

    for idx in range(GLOBAL.num_peers-len(out)):

        if not(has(learner, 'submitted')):
            out.append(('', 'You must submit before you can review others.'))
            continue

        if not(valid_subs.count() >= GLOBAL.min_in_pool_before_grouping_starts):
            # Simplest case: no reviews are allocated to learner yet
            out.append(('', 'Waiting for a peer to submit their work ...'))
            continue

    return out

def get_line2(learner, trigger, summaries):
    """
    Get the Summary and text display related to the evaluation being read.
    """
    out = []
    allocated_reviews = ReviewReport.objects.filter(reviewer=learner)\
        .order_by('-created') # for consistency

    for idx in range(GLOBAL.num_peers):
        out.append(('future-text', 'Waiting for peer to read your review'))


    # We use ``allocated_reviews`` to ensure consistency of order,
    # but we jump from that, using .next_code, to EvaluationReport. There
    # we pick up the r_actual, and look at the dates and times on it.
    for idx, review in enumerate(allocated_reviews):
        rubrics = RubricActual.objects.filter(rubric_code=review.unique_code)
        if rubrics:
            rubric = rubrics[0]
        else:
            break
        evalrep = EvaluationReport.objects.filter(unique_code=rubric.next_code)
        for report in evalrep:
            if report.r_actual:
                out[idx] = ('', 'Peer has read your review')

                summaries.append(Summary(date=report.r_actual.created,
                               action='Peer {0} read your review'.format(idx+1),
                               link='', catg='rev')
                            )

    return out

def get_line3(learner, trigger, summaries):
    """
    Get the Summary and text display related to the evaluation being evaluated.
    """
    out = []
    allocated_reviews = ReviewReport.objects.filter(reviewer=learner)\
        .order_by('-created') # for consistency

    for idx in range(GLOBAL.num_peers):
        out.append(('future-text', 'Waiting for peer to evaluate your review'))

    # We use ``allocated_reviews`` to ensure consistency of order,
    # but we jump from that, using .next_code, to EvaluationReport. There
    # we pick up the r_actual, and look at the dates and times on it.
    for idx, review in enumerate(allocated_reviews):
        rubrics = RubricActual.objects.filter(rubric_code=review.unique_code)
        if rubrics:
            rubric = rubrics[0]
        else:
            break
        evalrep = EvaluationReport.objects.filter(unique_code=rubric.next_code)
        for report in evalrep:
            if not report.r_actual:
                continue
            if  getattr(report.r_actual, 'next_code', ''):
                eval_code = report.r_actual.next_code
            else:
                # Generate the ``next_code`` as needed, to allow the
                # reviewer to see the evaluation (read-only) of the original
                # submitter.
                report.r_actual.next_code = eval_code = generate_random_token()
                report.r_actual.save()

            if getattr(report.r_actual, 'evaluated', ''):

                link = '<a href="/interactive/see-evaluation/{0}">{1}</a>'
                out[idx] = ('',
                            'Peer evaluated your review: {0}'.format(link.\
                            format(eval_code, 'see evaluation')) )


                summary = Summary(action='Peer {0} evaluated your review'.\
                                                      format(idx+1),
                                  date=report.r_actual.evaluated,
                                  link=link.format(eval_code, 'View'),
                                  catg='rev')
                summaries.append(summary)


    return out

def get_line4(learner, trigger, summaries):
    out = []
    for idx in range(GLOBAL.num_peers):
        out.append(('future-text',
                    "Waiting for peer's rebuttal of your review"))
    return out


def peers_read_evaluate_feedback(trigger, learner, entry_point=None,
                         summaries=list(), ctx_objects=dict(), **kwargs):
    """
    We are filling in this part of the template:

    <span class="indent">
    <ul>
        <li class="peers_to_you {0}" type="a">(a) {1}</li>  <--- this line
        <li class="peers_to_you {2}" type="a">(b) {3}</li>
        <li class="peers_to_you {4}" type="a">(c) {5}</li>
    </ul>
    """
    ctx_objects['peers_to_submitter_header'] = ('You must first submit some '
                                            'work for your peers to review.')
    ctx_objects['lineA'] = ('future-text',
                            "Read and evaluate reviewers' feedback")


    my_submission = Submission.objects.filter(entry_point=trigger.entry_point,
                                              is_valid=True,
                                              submitted_by=learner)\
                                      .exclude(status='A')

    if my_submission.count() > 1:
        logger.warn('More than one submission encountered')

    if not(has(learner, 'submitted')) or my_submission.count()==0:
        return


    submission = my_submission[0]
    reports = [False, ] * GLOBAL.num_peers
    reviews = [False,] * GLOBAL.num_peers
    idx = 0
    my_reviews = []


    my_reviews = ReviewReport.objects.filter(submission=submission).\
        order_by('created') # to ensure consistency in display
    for report in my_reviews:
        # There should be at most "GLOBAL.num_peers" reviews.

        # An error occurs here where a review is allocated beyond the number of
        # intended reviews.
        reports[idx] = report
        try:
            rubric = RubricActual.objects.get(\
                rubric_code=reports[idx].unique_code)
        except RubricActual.DoesNotExist:
            continue
        if rubric.submitted:
            reviews[idx] = True


        # Bump the counter and get the rest of the reviews.
        idx += 1

    # This message is overridden later for the case when everyone is completed.
    template = """{{n_reviewed}} peer{{ n_reviewed|pluralize:" has,s have" }}
     completely reviewed your work. Waiting for {{n_more}} more
        peer{{n_more|pluralize}} to start and complete their review."""

    header = insert_evaluate_variables(template, {'n_reviewed': sum(reviews),
                                              'n_more': GLOBAL.num_peers - \
                                              sum(reviews)}
                                     )

    if sum(reviews) == GLOBAL.num_peers:
        completed(learner, 'all_reviews_from_peers_completed')
        header = "All peers have completely reviewed your work."

    ctx_objects['peers_to_submitter_header'] = header

    # From the perspective of the learner, we should always order the peers
    # is the same way. Use the ``created`` field for that.
    rubrics = RubricActual.objects.filter(submission=my_submission)\
                                                            .order_by('created')
    for idx, ractual in enumerate(rubrics):
        summary = Summary(date=ractual.created, link='', catg='sub',
          action='Peer {} started a review of your work'.format(idx+1))
        summaries.append(summary)

        if ractual.status in ('C', 'L') and ractual.submitted:
            summary = Summary(date=ractual.completed, link='', catg='sub',
                 action='Peer {} completed a review of your work'.format(idx+1))
            summaries.append(summary)

    if sum(reviews) == 0:
        # There is no point to go further if there are no reviews completed
        # of the learner's work.
        return

    if not(has(learner, 'started_a_review')):
        # The learner hasn't reviewed other's work; so they are not in state
        # to evaluate others yet either.
        ctx_objects['lineA'] = ('', ('Please complete a review first, before '
                                     'evaluating the reviews received back.'))

        return


    # We cannot go further, unless all the reviews by the learner's peers are
    # completed.
    if not(has(learner, 'all_reviews_from_peers_completed')):
        return


    # Slow-down throttle here: we don't want to allow the submitter to start
    # evaluation unless they have finished their reviews.

    #if not(has(learner, 'completed_all_reviews')):
    #    return


    # If we have reached this point it is because the submitter can now
    # view their feedback. Therefore we only iterate over the COMPLETED rubrics.
    #
    # 1/ Set the r_actual review to be locked (read-only)
    # 2/ Create a rubric for evaluation of the review

    text = 'Read and evaluate their feedback: '
    for idx, ractual in enumerate(rubrics):
        ractual.status = 'L'
        ractual.save()
        try:
            report = EvaluationReport.objects.get(unique_code=ractual.next_code)
        except EvaluationReport.DoesNotExist:
            logger.error('EvaluationReport not found. Please correct.')
            ctx_objects['lineA'] = ('',
                                    ("The links to read and evaluate reviewers'"
                                     " feedback are still being generated. "
                                     "Please wait."))
            return

        extra = ' (still to do)'
        if hasattr(report.r_actual, 'status'):
            if report.r_actual.status in ('C', 'L'):
                extra = ' (completed)'

        if (idx > 0) and (idx < GLOBAL.num_peers):
            text += ';&nbsp;'

        text += 'evaluate <a href="/interactive/evaluate/{0}/">peer {1}</a>{2}'\
                 .format(report.unique_code, idx+1, extra)

    text += '.'
    ctx_objects['lineA'] = ('', text)

    #rubrics = RubricActual.objects.filter(submission=submission).order_by('evaluated')
    #if not(has(learner, 'read_and_evaluated_all_reviews')):
        #n_evaluations = 0
        #for rubric in rubrics:
            #if rubric.evaluated:
                #n_evaluations += 1
        #if n_evaluations >= GLOBAL.num_peers:
            #completed(learner, 'read_and_evaluated_all_reviews')

    if has(learner, 'completed_rebuttal'):
        pass


def peers_provide_rebuttal(trigger, learner, entry_point=None,
                         summaries=list(), ctx_objects=dict(), **kwargs):
    """
    We are filling in this part of the template:

    <span class="indent">
    <ul>
        <li class="peers_to_you {0}" type="a">(a) {1}</li>
        <li class="peers_to_you {2}" type="a">(b) {3}</li>   <--- this line
        <li class="peers_to_you {4}" type="a">(c) {5}</li>
    </ul>
    """
    ctx_objects['lineB'] = ('future-text',
                            'Provide a rebuttal back to peers')
    my_submissions = Submission.objects.filter(entry_point=trigger.entry_point,
                                              is_valid=True,
                                              submitted_by=learner)\
                                     .exclude(status='A')
    if my_submissions.count():
        submission = my_submissions[0]
    else:
        return


    if has(learner, 'read_and_evaluated_all_reviews'):
        evaluations = EvaluationReport.objects.filter(trigger=trigger,
                                                      sort_report='R',
                                                    evaluator=learner)
        evaluation = evaluations[0]
        summary = Summary(date=evaluation.created,
                          action=('You evaluated all reviews. Now '
                                  'complete the rebuttal.'),
                          link='LINK HERE', catg='sub')
        summaries.append(summary)
        ctx_objects['lineB'] = ('',
                                '"Provide a rebuttal"(link) back to your peers')



    # 4/ Indicate  submitter has read the reviews: so the reviewers see that
    #    pass



def peers_rebuttal_status(trigger, learner, entry_point=None,
                         summaries=list(), ctx_objects=dict(), **kwargs):
    """
    We are filling in this part of the template:

    <span class="indent">
    <ul>
        <li class="peers_to_you {0}" type="a">(a) {1}</li>
        <li class="peers_to_you {2}" type="a">(b) {3}</li>
        <li class="peers_to_you {4}" type="a">(c) {5}</li>    <--- this line
    </ul>
    """
    ctx_objects['lineC'] = ('future-text',
                            'Waiting for rebuttal to be read and assessed')

def peers_summarize(trigger, learner, entry_point=None,
                         summaries=list(), ctx_objects=dict(), **kwargs):
    """
    We are filling in this template:

    {{peers_to_submitter_header}}
    <span class="indent">
    <ul>
        <li class="peers_to_you {0}" type="a">(a) {1}</li>
        <li class="peers_to_you {2}" type="a">(b) {3}</li>
        <li class="peers_to_you {4}" type="a">(c) {5}</li>
    </ul>
    """
    peers_back_to_submitter  = """
    <style>.peers_to_you{{list-style-type:None}}</style>

    {{{{peers_to_submitter_header}}}}
    <span class="indent">
    <ul>
        <li class="peers_to_you {0}" type="a">(a) {1}</li>
        <li class="peers_to_you {2}" type="a">(b) {3}</li>
        <li class="peers_to_you {4}" type="a">(c) {5}</li>
    </ul>
    </span>
    """.format(ctx_objects['lineA'][0], ctx_objects['lineA'][1],
               ctx_objects['lineB'][0], ctx_objects['lineB'][1],
               ctx_objects['lineC'][0], ctx_objects['lineC'][1],)

    trigger.template = peers_back_to_submitter
    ctx_objects['peers_back_to_submitter'] = render_template(trigger,
                                                             ctx_objects)


def invite_reviewers(learner, trigger):
    """
    Invites reviewers to start the review process
    """
    valid_subs = Submission.objects.filter(trigger=trigger, is_valid=True).\
                                                            exclude(status='A')
    if not(valid_subs.count() >= GLOBAL.min_in_pool_before_grouping_starts):
        return

    # We have enough Submissions instances for the current trigger to send
    # emails to all potential reviewers: it is time to start reviewing
    #
    # The number of Submissions should be equal to the nubmer of nodes in graph:
    graph = group_graph(trigger.entry_point)
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
                       settings.BASE_URL + '/interactive/review/' + review.unique_code)
            subject = '[{0}]: start your peer review'.format(\
                                                trigger.entry_point.course)

            if not(review.have_emailed):
                send_email(learner.email, subject, messages=message,
                           delay_secs=5)

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
    def __init__(self, entry_point):

        groups = GroupConfig.objects.filter(entry_point=entry_point)

        # Added these two lines, so the graphs are always created randomly
        groups = list(groups)
        shuffle(groups)

        self.graph = nx.DiGraph()
        self.entry_point = entry_point
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


    #def get_next_review(self, exclude=None):
        #"""
        #Given the graph, get the next reviewer.
        #"""
        #potential = self.graph.nodes()
        #if exclude:
            #index = potential.index(exclude)
            #potential.pop(index)

        #shuffle(potential)
        #in_degree = []
        #for idx, node in enumerate(potential):
            #in_degree.append((self.graph.in_degree(node), idx))

        #in_degree.sort()
        #next_one = in_degree.pop(0)

        #if next_one[0] <= GLOBAL.num_peers:
            #return potential[next_one[1]]
        #else:
            #return None


    def get_submitter_to_review(self, exclude_reviewer):
        """
        Get the next submitter's work to review. You must specify the
        reviewer's Person instance (``exclude_reviewer``), to ensure they are
        excluded as a potential submission to evaluate.


        Rules:
        1. Arrows go FROM the submitter, and TO the reviewer.
        2. Avoid an arrow back to the submitter
        3. If unavoidable, go to the person with the least number of allocated
           reviews (incoming arrows)
        4. After that, assign randomly.

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



        Revised version:

        1. Arrows go FROM the submitter, and TO the reviewer.
        2. Exclude/prevent the review from possibly happening a second time!!
        2. Exclude nodes which are saturated: in = out = Nmax
        2. Score the nodes as: deg(in) - deg(out). Therefore 0 is a balanced
           node, and negative means that the node's work has gone out more
           times than the person self has reviewed others.
        3. Add small (+/- 0.1 amounts of random (normal distributed) noise to
           the score.
        4. Subtract (Nmax-0.5) from the score if the the current
           ``exclude_reviewer`` already has their work reviewed by the person.
           This avoids a back-arrow, but doesn't make it impossible.
        """



        potential = self.graph.nodes()
        if exclude_reviewer:
            index = potential.index(exclude_reviewer)
            potential.pop(index)

        # Important to shuffle here, so the indices are randomized
        shuffle(potential)

        scores = []  # of tuples: (score, node_index)
        for idx, node in enumerate(potential):
            # The learner (``exclude_reviewer``) has already reviewed ``node``
            if self.graph.has_edge(node, exclude_reviewer):
                continue

            bias = random.normalvariate(mu=0, sigma=0.1)
            if self.graph.has_edge(exclude_reviewer, node):
                bias = bias - (GLOBAL.num_peers-0.5)

            score = self.graph.in_degree(node) - self.graph.out_degree(node) + bias

            scores.append((score, idx))

        # Sort from low to high, and next we pop off the last value (highest)
        scores.sort()
        try:
            next_one = scores.pop()
        except IndexError:
            logger.error(('No more nodes to pop out for next reviewer. '
                          'learner={}\n----{}\n----{}').format(exclude_reviewer,
                                                             self.graph.nodes(),
                                                             self.graph.edges()
                                                            ))
            # Only to prevent failure, but this is serious.
            return None

        if self.graph.out_degree(potential[next_one[1]]) > GLOBAL.num_peers:
            # TODO: ensure the submitter's work is not reviewed too many times
            logger.error('Too many reviewers of {}'.format(potential[next_one[1]]))
            assert(False)
            return None

        return potential[next_one[1]]





def review(request, unique_code=None):
    """
    A review link (with ``unique_code``) is created the moment we have enough
    submitters to pool up. The link is created, and shown in the user-interface
    and (perhaps) they are emailed. When they visit that link, the review
    process starts:
    1/ Select a submission to attach this to, if not already attached.
    2/ prevent the document from being re-uploaded by submitter
    3/ prevent the document from being re-uploaded by submitter - another time
    4/ create rubric / Get the rubric (with prior filled in answers)
    5/ Return the rendered HTML to the reviewer.
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
            return r_actual
        else:
            return handle_review(request, unique_code)


    graph = group_graph(report.trigger.entry_point)
    submitter = graph.get_submitter_to_review(exclude_reviewer=\
                                                         report.reviewer)

    valid_subs = Submission.objects.filter(is_valid=True,
                                    entry_point=report.trigger.entry_point,
                                    trigger=report.trigger,
                                    submitted_by=submitter).exclude(status='A')
    if valid_subs.count() != 1:
        logger.error(('Found more than 1 valid Submission for {} in entry '
                      'point "{}"'.format(valid_subs,
                                        report.trigger.entry_point)))
        return HttpResponse(("You've used an incorrect link; or a problem with "
                             'the peer review system has occurred. Please '
                             'content k.g.dunn@tudelft.nl with the approximate '
                             'date and time that this occurred, and he can '
                             'try to assist you further.'))

    submission = valid_subs[0]
    report.submission = submission
    report.save()

    # 2. Prevent the document from being re-uploaded by submitter
    completed(report.submission.submitted_by, 'work_has_started_to_be_reviewed')


    # 3. Prevent the learner also from resubmitting
    completed(report.reviewer, 'started_a_review')
    completed(report.reviewer, 'work_has_started_to_be_reviewed')

    # Update the Membership, which will update the graph.

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


    # 4/ Create a RubricActual instance

    # Creates a new actual rubric for a given ``learner`` (the person
    # doing the) evaluation. It will be based on the parent template
    # defined in ``template``, and for the given ``submission`` (either
    # their own submission if it is a self-review, or another person's
    # submission for peer-review).

    get_create_actual_rubric(graded_by=report.reviewer,
                             trigger=report.trigger,
                             submission=submission,
                             rubric_code=unique_code)


    # 5/ Finally, return to the same point as if we were at the top of this func
    return handle_review(request, unique_code)


def evaluate(request, unique_code=None):
    """
    Generate the RubricActual from the template.

    """
    reports = EvaluationReport.objects.filter(unique_code=unique_code)
    if reports.count() != 1:
        logger.error('Incorrect Evaluation requested: {}'.format(unique_code))
        return HttpResponse(("You've used an incorrect link. Please check the "
                             'web address to ensure there was not a typing '
                             'error.<p>No evaluation found with that link.'))

    report = reports[0]


    # We have a report to be evaluated, now generate the links.
    if report.r_actual is None:
        # Generate the actual rubric here for it.
        eval_actual, _ = get_create_actual_rubric(graded_by=report.evaluator,
                                                trigger=report.trigger,
                                                submission=report.submission,
                                                rubric_code=report.unique_code)
        report.r_actual = eval_actual
        report.save()

    return handle_review(request, unique_code)


def see_evaluation(request, unique_code=None):
    """
    Shows the read-only evaluation to the peer reviewer (who originally
    reviewed the report, and has been evaluated by the original submitter).

    Set the r_actual to locked (to prevent the evaluator, i.e. the original
    submitter from changing anything further to the report)
    """

    # Note: we use the ``next_code`` field here, not the actual ``unique_code``
    #       field, since we want to first set the rubric to locked, so it
    #       shows as read-only.
    rubrics = RubricActual.objects.filter(next_code=unique_code)
    if rubrics.count() != 1:
        logger.error('Incorrect R/O eval requested: {}'.format(unique_code))
        return HttpResponse(("You've used an incorrect link. Please check the "
                             'web address to ensure there was not a typing '
                             'error.<p>No evaluation to see with that link.'))

    rubric = rubrics[0]
    rubric.status = 'L'
    rubric.save()

    # Now pass the rubric.rubric_code through, not the acquired unique_code.
    return handle_review(request, rubric.rubric_code)





# Utility function: to handle the generation of a ``Submission`` for a
# report evaluation.
# -------------------------------------------

def reportlab_styles():
    """
    Format the review with these styles.
    """
    styles= {
        'default': ParagraphStyle('default',
            fontName='Helvetica',
            fontSize=9,
            leading=12,
            leftIndent=0,
            rightIndent=0,
            firstLineIndent=0,
            alignment=TA_LEFT,
            spaceBefore=0,
            spaceAfter=0,
            bulletFontName='Arial',
            bulletFontSize=10,
            bulletIndent=0,
            textColor= black,
            backColor=None,
            wordWrap=None,
            borderWidth= 0,
            borderPadding= 0,
            borderColor= None,
            borderRadius= None,
            allowWidows= 1,
            allowOrphans= 0,
            textTransform=None,  # 'uppercase' | 'lowercase' | None
            endDots=None,
            splitLongWords=1,
        )
    }
    styles['title'] = ParagraphStyle('title',
        parent=styles['default'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=42,
        alignment=TA_CENTER,
        textColor=black,
    )
    styles['header'] = ParagraphStyle('header',
        parent=styles['default'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=24,
        alignment=TA_LEFT,
        textColor=black,
    )
    return styles

styles = reportlab_styles()
default = styles['default']

def report_render_rubric(r_actual, flowables):
    """
    Continues the rendering of the body of the report, using the rubric
    ``r_actual``, and the supplied list of flowables which are appended to.
    """
    def formatted_options(options):
        out = []
        for idx, option in enumerate(options):

            if option.rubric_item.option_type in ('DropD', 'Chcks', 'Radio'):
                if hasattr(option, 'selected'):
                    out.append(Paragraph(('<strong>{0}</strong>'
                            '').format(option.criterion), default))
                else:
                    out.append(Paragraph('<font color="lightgrey">{0}</font>'.\
                                            format(option.criterion), default))
            elif option.rubric_item.option_type == 'LText':
                out.append(Paragraph(option.prior_text.replace('\n','<br />\n'),
                                     default))

        return out


    styles = reportlab_styles()
    review_items, _ = r_actual.report()
    for item in review_items:

        flowables.append(Paragraph(item.ritem_template.criterion,
                                   styles['header']))
        flowables.append(Spacer(1, 6))


        flowables.append(ListFlowable(formatted_options(item.options),
                                      bulletType='bullet',
                                      bulletFontSize=8,
                                      bulletOffsetY=0,
                                      start='circle'))
        flowables.append(Spacer(1, 12))



def create_evaluation_PDF(r_actual):
    """
    Take an original submission (PDF), and combines an extra page or two,
    that contains a SINGLE review (``r_actual``).
    """
    report = ReviewReport.objects.get(unique_code=r_actual.rubric_code)
    # From the perspective of the submitter, which peer am I?
    rubrics = RubricActual.objects.filter(submission=report.submission).order_by('created')
    peer_number = 0
    for idx, rubric in enumerate(rubrics):
        if report.reviewer == rubric.graded_by:
            peer_number = idx + 1
            break

    base_dir_for_file_uploads = settings.MEDIA_ROOT
    token = generate_random_token(token_length=16)
    src = r_actual.submission.file_upload.file.name
    filename = 'uploads/{0}/{1}'.format(
                            r_actual.rubric_template.entry_point.id,
                            token + '.pdf')
    dst = base_dir_for_file_uploads + filename



    flowables = []
    flowables.append(Paragraph("Review from peer number {}".format(peer_number),
                  styles['title']))
    flowables.append(Spacer(1, 12))
    flowables.append(Paragraph(("The option in bold represents the one selected"
                                " by your reviewer."), default))
    flowables.append(Spacer(1, 12))

    report_render_rubric(r_actual, flowables)

    fd, temp_file = tempfile.mkstemp(suffix='.pdf')
    doc = BaseDocTemplate(temp_file)
    doc.addPageTemplates(
        [   PageTemplate(
                frames=[
                    Frame(doc.leftMargin, doc.bottomMargin, doc.width,
                          doc.height,id=None),]
            ),
        ]
    )
    doc.build(flowables)
    os.close(fd)

    # Append the extra PDF page:
    pdf1 = PdfFileReader(src)
    pdf2 = PdfFileReader(temp_file)
    merger = PdfFileMerger(strict=False, )

    merger.append(pdf1, import_bookmarks=False)
    merger.append(pdf2, import_bookmarks=False)
    merger.write(dst)
    merger.close()

    # Cleaning up ``pdf2``
    os.remove(temp_file)

    with open(dst, "rb") as out_file:
        django_file = File(out_file)

        # Key point: use the ``submitted_file_name`` field to check if
        # this is a re-review (i.e. then we reuse the Submission instance).
        new_sub, was_new = Submission.objects.get_or_create(status='A',
                            entry_point=r_actual.rubric_template.entry_point,
                            trigger=r_actual.rubric_template.next_trigger,
                            is_valid=True,
                            submitted_by=r_actual.graded_by,
                            submitted_file_name = r_actual.rubric_code
                        )

        new_sub.file_upload = django_file
        new_sub.save()

    # The ``dst`` is not needed once we have saved the instance.
    os.unlink(dst)

    # DELETE ANY PRIOR ATTEMPTS FOR THIS trigger/submitted_by combination.
    prior_evals = EvaluationReport.objects.filter(
                            trigger=r_actual.rubric_template.next_trigger,
                            peer_reviewer=r_actual.graded_by,
                            sort_report='E',
                            evaluator=r_actual.submission.submitted_by
                        )
    prior_evals.delete()

    # Now we create here the link between the EvaluationReport
    # and the original submission's review (r_actual.next_code).
    # They both use the same token.
    # Note: the token is only seen by the submitter (the person whose work
    #       was reviewed.)
    r_actual.next_code = token
    r_actual.save()

    review_back_to_submitter = EvaluationReport(
                                submission=new_sub,
                                trigger=r_actual.rubric_template.next_trigger,
                                unique_code=token,
                                sort_report='E',
                                peer_reviewer=r_actual.graded_by,
                                evaluator=r_actual.submission.submitted_by,
                            )
    review_back_to_submitter.save()




def create_rebuttal_PDF(r_actual):
    """
    Take an original submission (PDF), and combines an extra page or two,
    that contains the N review (``r_actual``) from the N peers. Not just 1 peer.


    """
    learner = r_actual.graded_by
    report = EvaluationReport.objects.get(unique_code=r_actual.rubric_code)

    submission = Submission.objects.filter(submitted_by=report.evaluator,
                                    entry_point=report.submission.entry_point,
                                    is_valid=True).exclude(status='A')
    submission = submission[0]

    rubrics = RubricActual.objects.filter(submission=submission).order_by('created')

    src = submission.file_upload.file.name

    flowables = []
    n_evaluations = 0

    for idx, rubric in enumerate(rubrics):
        review_items, _ = rubric.report()
        flowables.append(Paragraph("Review from peer number {}".format(idx+1),
                                   styles['title']))
        flowables.append(Spacer(1, 12))
        flowables.append(Paragraph(("The option in bold represents the one "
                                    "selected by the reviewer."), default))
        flowables.append(Spacer(1, 12))

        report_render_rubric(rubric, flowables)

        flowables.append(PageBreak())

        # While we are here, also set the ``evaluated`` date/time on the rubric
        # but only on the rubric that we are currently evaluating
        if rubric.graded_by == report.peer_reviewer:
            #rubric.evaluated = timezone.now()
            #rubric.save()
            # The evaluation date/time belongs with the rubric attached to
            # the EvaluationReport (when was the evaluation completed by the
            # submitter; not the rubric.evaluated, since that was submitted
            # by the reviewer)
            report.r_actual.evaluated = timezone.now()
            report.r_actual.save()

    n_evaluations = RubricActual.objects.filter(graded_by=r_actual.graded_by,
                            rubric_template=r_actual.rubric_template).count()


    if n_evaluations < GLOBAL.num_peers:
        return

    # Only continue to generate this report if it is the last review
    completed(learner, 'read_and_evaluated_all_reviews')

    fd, temp_file = tempfile.mkstemp(suffix='.pdf')
    doc = BaseDocTemplate(temp_file)
    doc.addPageTemplates(
        [   PageTemplate(
            frames=[
                    Frame(doc.leftMargin, doc.bottomMargin, doc.width,
                          doc.height,id=None),]
                ),
            ]
    )
    doc.build(flowables)
    os.close(fd)


    # Append the extra PDF page:
    pdf1 = PdfFileReader(src)
    pdf2 = PdfFileReader(temp_file)
    merger = PdfFileMerger(strict=False, )

    merger.append(pdf1, import_bookmarks=False)
    merger.append(pdf2, import_bookmarks=False)

    fd, dst_file = tempfile.mkstemp(suffix='.pdf')

    merger.write(dst_file)
    merger.close()

    # Cleaning up ``pdf2``
    os.remove(temp_file)

    with open(dst_file, "rb") as out_file:
        django_file = File(out_file)

        # Key point: use the ``submitted_file_name`` field to check if
        # this is a re-review (i.e. then we reuse the Submission instance).
        new_sub, was_new = Submission.objects.get_or_create(\
                            status='A',
                            entry_point=r_actual.rubric_template.entry_point,
                            trigger=r_actual.rubric_template.next_trigger,
                            is_valid=True,
                            submitted_by=learner,

                            # This fields can be left out, but we add something
                            # here for display, to emphasize it is a merger
                            # of reviews from N different peers.
                            submitted_file_name = 'Merged reviews from eval'
                        )

        new_sub.file_upload = django_file
        new_sub.save()

    # The ``dst_file`` is not needed once we have saved the instance.
    os.unlink(dst_file)

    # UPDATE any prior EvaluationReport
    prior_eval, _ = EvaluationReport.objects.get_or_create(
                            trigger=r_actual.rubric_template.next_trigger,
                            sort_report='R',
                            evaluator=learner
                        )

    token = new_sub.file_upload.name.split('/')[2].strip('.pdf')
    prior_eval.unique_code = token
    prior_eval.submission = new_sub
    prior_eval.save()

#---------
# Functions related to the learner's progress
#---------

def has(learner, achievement, detailed=False):
    """
    See if a user has completed a certain achievement.
    """
    possible = Achievement.objects.filter(learner=learner,
                                          achieved__name=achievement)
    if possible.count() == 0:
        return False
    else:
        if detailed:
            return possible[0]
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


def reportcard(learner, entry_point, detailed=False):
    """
    Get the "reportcard" (a dictionary) of the learner's achievements
    """

    report = OrderedDict()
    for item in AchieveConfig.objects.filter(entry_point=entry_point)\
                                                      .order_by('order'):
        report[item.name] = has(learner, item.name, detailed)
    return report


def overview(request, course=None, learner=None, entry_point=None):
    """
    Student gets an overview of their grade here.
    We use all ``entry_points`` related to a course, except this entry point.
    """
    entries = EntryPoint.objects.filter(course=course).order_by('order')

    achieved = {}

    # achieved[entry_point][achievement_config]

    entry_display = []
    for entry in entries:
        if entry == entry_point:
            continue
        achieved[entry] = reportcard(learner, entry, detailed=True)
        entry_display.append(entry)

    ctx = {'learner': learner,
           'course': course,
           'achieved': achieved,
           'entries': entry_display}

    html = loader.render_to_string('interactive/display_progress.html', ctx)
    return HttpResponse(html)
